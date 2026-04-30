# Beginner AWS Setup Guide

This guide turns the planned AWS architecture for FlippingPdfTool into a beginner-friendly setup sequence. It is based on the workflow design in this feature branch, not on a fully deployed implementation. Some application pieces are still planned work, but this document shows how the AWS side is expected to fit together.

For a deployment-readiness gate before the first live upload test, use [checklists/aws-deployment-preflight.md](./checklists/aws-deployment-preflight.md).

## Provisioned AWS Baseline

The following AWS prerequisites were provisioned for this feature branch on 2026-04-27 and can be treated as the current environment baseline for implementation and validation.

### S3

- Bucket: `cmg-catalog-book`
- Object ownership: ACLs disabled
- Public access: block all public access
- Encryption: SSE-S3

Configured prefix layout:

- `artifacts/`
- `input/currentcatalog/`
- `input/colorfulimages/`
- `input/lillianvernon/`
- `output/currentcatalog/`
- `output/colorfulimages/`
- `output/lillianvernon/`

### DynamoDB

- Table: `ProcessingJobs`
- Partition key: `jobId` (string)
- Capacity mode: on-demand

### Secrets Manager

Configured secret names:

- `flipping-pdf/magento`
- `flipping-pdf/flipbook`
- `flipping-pdf/notifications`

Secret values are intentionally not stored in the repository. Only secret names and integration ownership are tracked here.

### Container and Workflow Infrastructure

- ECR repository: `flipping-pdf-worker`
- ECS cluster: `flipping-pdf-cluster`
- ECS task definition: `flipping-pdf-worker-task`
- Step Functions state machine: `flipping-pdf-workflow`
- EventBridge rule: `S3-to-FlippingPDF-Workflow`

### IAM Roles

- `StepFunctions-FlippingPdf-Role`
- `ECS-TaskExecution-Role`
- `ECS-Worker-Task-Role`

### CloudWatch Logs

- `/aws/ecs/flipping-pdf-worker` with 30-day retention
- `/aws/states/flipping-pdf-workflow` with 30-day retention

### Implementation Note

This baseline confirms the production routing model for one shared bucket with site-specific prefixes under `input/` and `output/`. Any worker contracts, routing helpers, or workflow payload examples should treat the bucket name and object key as separate fields.

## What You Are Building

The planned flow is:

1. A catalog PDF is uploaded to Amazon S3.
2. AWS starts a workflow when the file appears under a supported input prefix.
3. The workflow validates the site prefix and records a job entry.
4. An ECS Fargate container runs the PDF-linking worker.
5. The worker reads the source PDF, calls Textract, and writes the linked PDF back to S3.
6. DynamoDB stores durable job state.
7. The ECS worker can publish the finished PDF and notify stakeholders. If flipbook publication is not configured yet, the worker records that as an expected publication-stage partial success and can still send a failure notification.

## Before You Start

You should have:

1. An AWS account you can create resources in.
2. Access to IAM, S3, DynamoDB, ECS, ECR, Step Functions, EventBridge, CloudWatch, Secrets Manager, and Textract.
3. A local Docker installation.
4. The AWS CLI installed locally.
5. A sample PDF you can use for testing.

## Step 1: Choose an AWS Region

Pick one region and keep all resources in it unless you have a reason not to. For a first setup, keep everything in a single region such as `us-east-1`.

Write down:

- AWS region
- AWS account ID
- A short environment name such as `dev`

## Step 2: Create the S3 Bucket and Prefixes

Create one S3 bucket named `cmg-catalog-book` if the name is available in your account and region strategy. If not, choose a unique bucket name and keep the same prefix structure.

Create these prefixes inside the bucket:

- `input/currentcatalog/`
- `input/colorfulimages/`
- `input/lillianvernon/`
- `output/currentcatalog/`
- `output/colorfulimages/`
- `output/lillianvernon/`
- `artifacts/`

Purpose:

- `input/` receives uploaded source PDFs.
- `output/` stores linked PDFs.
- `artifacts/` stores diagnostic files and per-run outputs if you keep them.

## Step 3: Create the DynamoDB Table

Create a DynamoDB table to store processing-job state.

Suggested table settings:

- Table name: `ProcessingJobs`
- Partition key: `jobId` as a string
- Billing mode: On-demand for an initial setup

Suggested attributes to store in each item:

- `jobId`
- `status`
- `failureStage`
- `sourceBucket`
- `sourceKey`
- `outputBucket`
- `outputKey`
- `sitePrefix`
- `artifactPrefix`
- `createdAt`
- `updatedAt`
- `flipbookUrl`
- `errorMessage`

## Step 4: Create Secrets in Secrets Manager

Create secrets for external integrations so credentials are not stored in code or plain environment files.

Suggested secrets:

- `flipping-pdf/magento`
- `flipping-pdf/flipbook`
- `flipping-pdf/notifications`

Examples of what they may contain:

- Magento base URL plus either a preissued bearer token or a username/password pair that can exchange `POST /rest/V1/integration/admin/token` for an access token
- Flipbook API URL and credentials
- Notification configuration such as recipient group or service token

If you are only testing the current local CLI, you do not need all of these yet. The current CLI mainly needs AWS credentials that can call Textract.

## Step 5: Create an ECR Repository

Create an Amazon ECR repository to hold the worker container image.

Suggested repository name:

- `flipping-pdf-worker`

You will use this later when the worker Dockerfile and worker entrypoint exist in the repository.

## Step 6: Create an ECS Cluster

Create an ECS cluster for Fargate tasks.

Suggested settings:

- Cluster type: ECS with AWS Fargate
- Cluster name: `flipping-pdf-cluster`

You do not need EC2 instances for this design.

## Step 7: Create IAM Roles

You will usually need at least three IAM roles.

### 1. Step Functions execution role

This role needs permission to:

- start ECS tasks
- describe ECS tasks
- read and write DynamoDB job records
- write workflow logs
- pass the ECS task role to Fargate

### 2. ECS task execution role

This role needs permission to:

- pull container images from ECR
- write logs to CloudWatch Logs

### 3. ECS task role for the worker

This role needs permission to:

- read source PDFs from S3
- write linked PDFs and artifacts to S3
- call Amazon Textract
- read secrets from Secrets Manager
- read and update DynamoDB job records
- call SES or SNS if notifications are sent from the worker

If your secrets use a customer-managed KMS key, add `kms:Decrypt` permission for that key.

## Step 8: Create CloudWatch Log Groups

Create CloudWatch log groups for:

- ECS worker logs
- Step Functions execution logging

Suggested names:

- `/aws/ecs/flipping-pdf-worker`
- `/aws/states/flipping-pdf-workflow`

## Step 9: Create the ECS Task Definition

Create a Fargate task definition for the worker.

Suggested starting settings:

- Launch type: Fargate
- CPU: start with `1024` or higher
- Memory: start with `2048` or higher
- OS: Linux
- Container port mappings: none required unless you later expose an API

Required runtime variables for the worker include:

- `JOB_ID`
- `SOURCE_BUCKET`
- `SOURCE_KEY`
- `OUTPUT_BUCKET`
- `OUTPUT_KEY`
- `ARTIFACT_BUCKET`
- `ARTIFACT_PREFIX`
- `SITE_PREFIX`
- `PUBLIC_DOMAIN`
- `MAGENTO_STORE_CODE`
- `AWS_REGION`
- `DYNAMODB_TABLE_NAME`

Static environment variables or task-definition defaults should also include:

- `MAGENTO_SECRET_NAME=flipping-pdf/magento`
- `FLIPBOOK_SECRET_NAME=flipping-pdf/flipbook`
- `NOTIFICATION_MODE` such as `ses` or `sns`
- `NOTIFICATION_SECRET_NAME=flipping-pdf/notifications`

The repository now includes starter templates for the task definition, Step Functions state machine, and EventBridge rule under `aws/templates/`.

Do not hardcode secrets as plain environment variables if you can avoid it. Use ECS secret injection from Secrets Manager.

## Step 10: Create the Step Functions Workflow

Create a Step Functions state machine to orchestrate the flow.

The checked-in state machine template in `aws/templates/flipping-pdf-workflow.asl.json` does this:

1. Accept the S3 event input.
2. Validate that the uploaded key is under a supported prefix.
3. Derive the site configuration from the prefix.
4. Create or update a DynamoDB job record.
5. Run the ECS Fargate worker.
6. Record success or failure.

The ECS worker itself already handles these downstream stages:

1. Flipbook publication when `flipping-pdf/flipbook` contains a live URL and API key.
2. Success notification after publication succeeds.
3. Failure notification for rejected routing, processing failures, publication failures, notification failures, and the expected publication-not-configured case.

If the flipbook secret is blank or incomplete, the workflow still produces the linked PDF, records `partial-success` with `failureStage=publication`, and can notify operators about that expected exception.

Supported site prefixes in the current design are:

- `currentcatalog`
- `colorfulimages`
- `lillianvernon`

The routing rules are:

- `input/currentcatalog/<file>.pdf` -> `output/currentcatalog/<file>.pdf`
- `input/colorfulimages/<file>.pdf` -> `output/colorfulimages/<file>.pdf`
- `input/lillianvernon/<file>.pdf` -> `output/lillianvernon/<file>.pdf`

Any other prefix should be rejected before PDF processing starts.

## Step 11: Create the S3 Trigger

Configure S3 object-created events so uploads under `input/` start the workflow.

Two common approaches:

1. Use EventBridge and route matching S3 events to Step Functions.
2. Use an S3 event notification path that invokes a small starter component.

For a beginner setup, EventBridge is often easier to inspect and debug.

## Step 12: Build and Push the Worker Container

This repository now contains the worker implementation and Dockerfile needed for the ECS task image. If your AWS baseline is already provisioned manually, this step is the handoff from local validation to the deployed worker image:

```bash
aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin <account-id>.dkr.ecr.<region>.amazonaws.com
docker build -t flipping-pdf-worker .
docker tag flipping-pdf-worker:latest <account-id>.dkr.ecr.<region>.amazonaws.com/flipping-pdf-worker:latest
docker push <account-id>.dkr.ecr.<region>.amazonaws.com/flipping-pdf-worker:latest
```

Use the pushed image tag in the task-definition template under `aws/templates/flipping-pdf-worker-task-definition.json`, register that task definition, and then update the state machine definition from `aws/templates/flipping-pdf-workflow.asl.json`.

## Step 13: Configure Local AWS Credentials for Testing

For local testing, configure AWS credentials with the AWS CLI:

```bash
aws configure
```

Provide:

- AWS access key ID
- AWS secret access key
- default region
- output format such as `json`

For the current CLI in this repository, those credentials need Textract access.

## Step 14: Run a Local Baseline Test First

Before you deploy the full workflow, verify the existing local pipeline still works.

Run the tests:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Run the CLI locally against a sample PDF:

```bash
python src/main.py "/path/to/sample-catalog.pdf" --domain www.currentcatalog.com --skip-existing
```

Expected result:

- A linked PDF is created locally.
- Page summaries and Textract artifacts are created.
- Link annotations appear in the output PDF.

## Step 15: Test One Upload Path in AWS

Once the worker image is pushed and your existing AWS resources are wired to it, test the smallest happy path first.

Upload a sample PDF to:

- `input/currentcatalog/sample-catalog.pdf`

Then verify:

1. The workflow starts.
2. A DynamoDB job record is created.
3. The worker runs on ECS Fargate.
4. The linked PDF appears under `output/currentcatalog/sample-catalog.pdf`.
5. Logs appear in CloudWatch.

If the flipbook secret is not live yet, also verify:

1. The `ProcessingJobs` item ends in `partial-success` with `failureStage=publication`.
2. A failure notification is sent to the configured SES recipient or SNS topic describing the expected publication exception.

## Step 16: Validate Failure Handling

After the happy path works, test these failure cases:

1. Upload a file to `input/unknown/sample.pdf` and confirm the job is rejected during routing.
2. Upload an invalid PDF and confirm processing fails with a recorded error.
3. Force a downstream error such as publication failure and confirm previously created artifacts remain available.

## Suggested Naming Summary

These names are reasonable starting points:

- S3 bucket: `cmg-catalog-book`
- DynamoDB table: `ProcessingJobs`
- ECR repository: `flipping-pdf-worker`
- ECS cluster: `flipping-pdf-cluster`
- Log group: `/aws/ecs/flipping-pdf-worker`
- Log group: `/aws/states/flipping-pdf-workflow`
- Secrets: `flipping-pdf/magento`, `flipping-pdf/flipbook`, `flipping-pdf/notifications`

## What Is Not Finished Yet in This Branch

The worker implementation and starter AWS workflow templates are present in the repository, but these deployment-support pieces are still intentionally incomplete:

- fully parameterized infrastructure-as-code for every manually provisioned AWS resource
- automated placeholder substitution and deployment scripts for the checked-in AWS templates
- final live secret values for flipbook publication and notification delivery

That means this document can support deployment into the current manually provisioned AWS environment, but the repository is not yet a full infrastructure-from-source deployment package.

## Recommended Next Steps

1. Push the validated worker image to ECR and register the task definition from `aws/templates/flipping-pdf-worker-task-definition.json`.
2. Update the existing Step Functions state machine from `aws/templates/flipping-pdf-workflow.asl.json` and the EventBridge target from `aws/templates/flipping-pdf-eventbridge-rule.json`.
3. Test one supported site prefix and confirm the linked PDF, DynamoDB job record, and expected publication-stage failure notification path work in AWS.
4. Replace flipbook secret values with live publication credentials later, then validate the success-notification path separately from the expected publication exception.
