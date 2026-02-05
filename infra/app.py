#!/usr/bin/env python3
import os
import aws_cdk as cdk

from clinical_ai_assistant_stack import ClinicalAIAssistantStack


app = cdk.App()

ClinicalAIAssistantStack(app, "ClinicalAIAssistantStack",
                         env=cdk.Environment(
                             account=os.getenv("CDK_DEFAULT_ACCOUNT"),
                             region='us-east-1'
                            )
                        )

app.synth()
