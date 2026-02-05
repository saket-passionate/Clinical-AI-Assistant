from aws_cdk import (
    Stack,
    aws_s3 as s3,
    RemovalPolicy,
)
from constructs import Construct


class ClinicalAiAssistantStack(Stack):
    """
    AWS CDK Stack for Clinical AI Assistant infrastructure.
    
    This stack sets up the basic infrastructure components needed for the
    Clinical AI Assistant application.
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # S3 bucket for storing clinical data with KMS encryption for HIPAA compliance
        # Uses AWS managed KMS keys for enhanced security of PHI/PII data
        clinical_data_bucket = s3.Bucket(
            self,
            "ClinicalDataBucket",
            encryption=s3.BucketEncryption.KMS_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            versioned=True,
            removal_policy=RemovalPolicy.RETAIN,
        )
