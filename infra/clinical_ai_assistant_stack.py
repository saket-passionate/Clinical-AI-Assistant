from aws_cdk import (
    Stack,
    aws_s3 as s3,
    aws_s3_notifications as s3n,
    aws_lambda as _lambda,
    aws_iam as iam,
    aws_events as events,
    aws_events_targets as targets,
    RemovalPolicy,
    Duration
)
from typing import List
from constructs import Construct

# Configuration Constants
EMAIL_ADDRESS = "saketthavananilindan@gmail.com"
LAMBDA_TIMEOUT_SECONDS = 300
LAMBDA_RUNTIME = _lambda.Runtime.PYTHON_3_10
AUDIO_INPUT_PREFIX = "input/"
HEALTHSCRIBE_SUMMARY_PREFIX = "hs-"
HEALTHSCRIBE_SUMMARY_SUFFIX = "summary.json"


class ClinicalAIAssistantStack(Stack):
    """
    CDK Stack for Clinical AI Assistant using AWS HealthScribe.
    
    This stack creates:
    - S3 bucket for audio file ingestion
    - EventBridge rule to trigger processing on audio upload
    - Lambda function to initiate HealthScribe transcription
    - Lambda function to generate patient reports from transcription
    """
    
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create S3 bucket for audio files
        audio_bucket = self._create_audio_bucket()
        
        # Create IAM role for HealthScribe
        healthscribe_role = self._create_healthscribe_role()
        
        # Create Lambda function for HealthScribe processing
        healthscribe_lambda = self._create_healthscribe_lambda(
            audio_bucket, 
            healthscribe_role
        )
        
        # Create EventBridge rule for audio upload notifications
        self._create_audio_upload_rule(audio_bucket, healthscribe_lambda)
        
        # Create Lambda function for patient report generation
        self._create_patient_report_lambda(audio_bucket)

    def _create_audio_bucket(self) -> s3.Bucket:
        """Create S3 bucket for audio file ingestion."""
        return s3.Bucket(
            self, 
            "AudioIngestionBucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            event_bridge_enabled=True
        )

    def _create_healthscribe_role(self) -> iam.Role:
        """Create IAM role for HealthScribe service."""
        return iam.Role(
            self,
            "HealthScribeDataAccessRole",
            assumed_by=iam.ServicePrincipal("transcribe.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonS3FullAccess")
            ]
        )

    def _create_lambda_base_policy(self, actions: List[str]) -> iam.PolicyStatement:
        """Create IAM policy statement with specified actions."""
        return iam.PolicyStatement(
            actions=actions,
            resources=["*"]
        )

    def _create_healthscribe_lambda(
        self, 
        audio_bucket: s3.Bucket, 
        healthscribe_role: iam.Role
    ) -> _lambda.Function:
        """Create Lambda function for HealthScribe transcription processing."""
        lambda_function = _lambda.Function(
            self,
            "HealthScribeLambda",
            runtime=LAMBDA_RUNTIME,
            handler="summarize_conversation.handler",                
            code=_lambda.Code.from_asset("../lambda/healthscribe"),
            timeout=Duration.seconds(LAMBDA_TIMEOUT_SECONDS),
            environment={
                "SOURCE_EMAIL": EMAIL_ADDRESS,
                "PATIENT_EMAIL": EMAIL_ADDRESS,
                "TRANSCRIBE_ROLE_ARN": healthscribe_role.role_arn,
            }
        )

        # Add permissions for HealthScribe operations
        lambda_function.add_to_role_policy(
            self._create_lambda_base_policy([
                "transcribe:StartMedicalScribeJob",
                "transcribe:GetMedicalScribeJob",
                "transcribe:TagResource",
                "s3:GetObject",
                "s3:PutObject",
                "s3:HeadObject",
                "ses:SendEmail",
                "ses:SendRawEmail",
            ])
        )

        # Add IAM PassRole permission
        lambda_function.add_to_role_policy(
            iam.PolicyStatement(
                actions=["iam:PassRole"],
                resources=[healthscribe_role.role_arn]
            )
        )

        # Grant S3 bucket access
        audio_bucket.grant_read_write(lambda_function)

        # Allow EventBridge to invoke Lambda
        lambda_function.add_permission(
            "AllowEventBridgeInvokeHealthScribe",
            principal=iam.ServicePrincipal("events.amazonaws.com"),
            action="lambda:InvokeFunction"
        )

        return lambda_function

    def _create_audio_upload_rule(
        self, 
        audio_bucket: s3.Bucket, 
        healthscribe_lambda: _lambda.Function
    ) -> None:
        """Create EventBridge rule to trigger Lambda on audio file upload."""
        audio_upload_rule = events.Rule(
            self,
            "AudioUploadRule",
            event_pattern=events.EventPattern(
                source=["aws.s3"],
                detail_type=["Object Created"],
                detail={
                    "bucket": {
                        "name": [audio_bucket.bucket_name]
                    },
                    "object": {
                        "key": [{
                            "prefix": AUDIO_INPUT_PREFIX
                        }]
                    }
                }
            )
        )
        audio_upload_rule.add_target(targets.LambdaFunction(healthscribe_lambda))

    def _create_patient_report_lambda(self, audio_bucket: s3.Bucket) -> _lambda.Function:
        """Create Lambda function for patient report generation."""
        lambda_function = _lambda.Function(
            self,
            "PatientReportLambda",
            runtime=LAMBDA_RUNTIME,
            handler="patient_reports.handler",
            code=_lambda.Code.from_asset("../lambda/reporting"),
            timeout=Duration.seconds(LAMBDA_TIMEOUT_SECONDS),
            environment={
                "SOURCE_EMAIL": EMAIL_ADDRESS,
            }
        )

        # Add S3 event notification
        audio_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(lambda_function),   
            s3.NotificationKeyFilter(
                prefix=HEALTHSCRIBE_SUMMARY_PREFIX,
                suffix=HEALTHSCRIBE_SUMMARY_SUFFIX
            )
        )

        # Add permissions for report generation
        lambda_function.add_to_role_policy(
            self._create_lambda_base_policy([
                "s3:GetObject",
                "s3:PutObject",
                "s3:HeadObject",
                "ses:SendEmail",
                "ses:SendRawEmail",
                "transcribe:GetMedicalScribeJob",
                "transcribe:ListMedicalScribeJobs",
            ])
        )

        # Grant S3 bucket access
        audio_bucket.grant_read_write(lambda_function)

        return lambda_function
