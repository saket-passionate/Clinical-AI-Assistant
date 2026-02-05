#!/usr/bin/env python3
import os
import aws_cdk as cdk

from clinical_ai_assistant_stack import ClinicalAiAssistantStack


app = cdk.App()

ClinicalAiAssistantStack(
    app,
    "ClinicalAiAssistantStack",
    env=cdk.Environment(
        account=os.getenv('CDK_DEFAULT_ACCOUNT'),
        region=os.getenv('CDK_DEFAULT_REGION')
    ),
    description="Clinical AI Assistant infrastructure stack"
)

app.synth()
