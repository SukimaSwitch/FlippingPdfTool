# Beginner AWS Setup Guide

This guide turns the planned AWS architecture for FlippingPdfTool into a beginner-friendly setup sequence. It is based on the workflow design in this feature branch, not on a fully deployed implementation. Some application pieces are still planned work, but this document shows how the AWS side is expected to fit together.

## What You Are Building

The planned flow is:

1. A catalog PDF is uploaded to Amazon S3.
2. AWS starts a workflow when the file appears under a supported input prefix.
3. The workflow validates the site prefix and records a job entry.
4. An ECS Fargate container runs the PDF-linking worker.
5. The worker reads the source PDF, calls Textract, and writes the linked PDF back to S3.
6. DynamoDB stores durable job state.
7. Later workflow stages can publish the finished PDF and notify stakeholders.

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

- Magento base URL, username, password, token, or API key
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

Planned environment variables for the worker include:

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

Do not hardcode secrets as plain environment variables if you can avoid it. Use ECS secret injection from Secrets Manager.

## Step 10: Create the Step Functions Workflow

Create a Step Functions state machine to orchestrate the flow.

The initial state machine should do this:

1. Accept the S3 event input.
2. Validate that the uploaded key is under a supported prefix.
3. Derive the site configuration from the prefix.
4. Create or update a DynamoDB job record.
5. Run the ECS Fargate worker.
6. Record success or failure.

Later, when the application code supports it, extend the workflow with:

1. Flipbook publication.
2. Success notification.
3. Failure notification.

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

This repository does not yet contain the full worker implementation or Dockerfile for the planned cloud worker. Once that exists, the build-and-push flow will look like this:

```bash
aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin <account-id>.dkr.ecr.<region>.amazonaws.com
docker build -t flipping-pdf-worker .
docker tag flipping-pdf-worker:latest <account-id>.dkr.ecr.<region>.amazonaws.com/flipping-pdf-worker:latest
docker push <account-id>.dkr.ecr.<region>.amazonaws.com/flipping-pdf-worker:latest
```

At the moment, treat this step as planned infrastructure wiring rather than something this branch can complete end to end.

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

Once the worker code and infrastructure are in place, test the smallest happy path first.

Upload a sample PDF to:

- `input/currentcatalog/sample-catalog.pdf`

Then verify:

1. The workflow starts.
2. A DynamoDB job record is created.
3. The worker runs on ECS Fargate.
4. The linked PDF appears under `output/currentcatalog/sample-catalog.pdf`.
5. Logs appear in CloudWatch.

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

This guide is aligned to the design, but the following implementation pieces are still planned work in this branch:

- worker package under `src/worker/`
- worker Dockerfile
- Step Functions orchestration code or infrastructure-as-code
- publication and notification clients
- durable job repository implementation

That means this document is a deployment roadmap and onboarding asset, not proof that the branch is already deployable.

## Recommended Next Steps

1. Finish the Phase 1 and Phase 2 implementation tasks in the feature spec.
2. Add infrastructure as code so the AWS setup is reproducible.
3. Start with one supported site prefix and one sample PDF before expanding the workflow.
