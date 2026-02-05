# AWS CDK Infrastructure

This directory contains the AWS CDK infrastructure code for the Clinical AI Assistant.

## Prerequisites

- Python 3.9 or later
- AWS CLI configured with appropriate credentials
- AWS CDK CLI installed (`npm install -g aws-cdk`)

## Setup

1. Install dependencies:
   ```bash
   pip install -r ../requirements.txt
   ```

2. Bootstrap your AWS environment (first time only):
   ```bash
   cdk bootstrap
   ```

## Usage

- **Synthesize CloudFormation template:**
  ```bash
  cdk synth
  ```

- **Deploy the stack:**
  ```bash
  cdk deploy
  ```

- **Destroy the stack:**
  ```bash
  cdk destroy
  ```

## Stack Components

The `ClinicalAiAssistantStack` currently includes:
- S3 bucket for storing clinical data (encrypted, versioned, with public access blocked)

Additional components can be added as the application requirements evolve.
