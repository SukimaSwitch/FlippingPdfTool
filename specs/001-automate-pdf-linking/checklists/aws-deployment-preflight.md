# AWS Deployment Preflight Checklist: Automated PDF Link Publishing

**Purpose**: Validate the manually provisioned AWS environment before the first live worker deployment and upload test
**Created**: 2026-04-29
**Feature**: [spec.md](../spec.md)
**Companion Docs**: [aws-beginner-setup.md](../aws-beginner-setup.md), [quickstart.md](../quickstart.md)

## Core Infrastructure

- [x] The source bucket exists and is the bucket the worker will read from.
- [x] The bucket contains these prefixes: `input/currentcatalog/`, `input/colorfulimages/`, `input/lillianvernon/`, `output/currentcatalog/`, `output/colorfulimages/`, `output/lillianvernon/`, and `artifacts/`.
- [x] The DynamoDB table `ProcessingJobs` exists with partition key `jobId`.
- [x] The ECR repository `flipping-pdf-worker` exists.
- [x] The ECS cluster, ECS task definition, Step Functions state machine, EventBridge rule, and IAM roles referenced in the AWS setup guide exist in the target region.
- [x] CloudWatch log groups for the ECS worker and Step Functions workflow are accessible to operators.

## Worker Image

- [x] The latest validated worker image has been built and pushed to ECR.
- [x] The ECS task definition points to the intended image tag rather than an older worker build.
- [x] The deployed image includes Magento admin-token authentication, XML token parsing, DynamoDB float normalization, and site-specific customer URL paths.

## Secrets And External Config

- [ ] `flipping-pdf/magento` exists and contains a Magento API host, not a public storefront domain.
- [ ] `flipping-pdf/magento` contains either `username` plus `password`, or `bearer_token`.
- [ ] `flipping-pdf/flipbook` exists, even if its live values are not ready yet.
- [ ] `flipping-pdf/notifications` exists, even if its live values are not ready yet.
- [ ] Operators understand that full publication and success-notification validation must wait until live flipbook and notification secret values are installed.

## ECS Runtime Wiring

- [ ] The ECS task definition or orchestration layer passes `AWS_REGION` and `DYNAMODB_TABLE_NAME=ProcessingJobs`.
- [x] The worker receives `JOB_ID`, `SOURCE_BUCKET`, and `SOURCE_KEY`.
- [ ] The worker receives or derives the routed values needed for accepted jobs: `OUTPUT_BUCKET`, `OUTPUT_KEY`, `SITE_PREFIX`, `PUBLIC_DOMAIN`, and `MAGENTO_STORE_CODE`.
- [ ] `MAGENTO_SECRET_NAME` is wired to the worker.
- [ ] `MAGENTO_SEARCH_BASE_URL` is unset unless it is intentionally overriding the Magento API host from the secret.
- [ ] If `MAGENTO_SEARCH_BASE_URL` is set, it points to the Magento API host rather than the storefront domain.

## IAM And Access

- [ ] The ECS worker task role can read source PDFs from S3.
- [ ] The ECS worker task role can write linked PDFs and artifact metadata to S3.
- [ ] The ECS worker task role can read the required Secrets Manager secrets.
- [ ] The ECS worker task role can call Amazon Textract.
- [ ] The ECS worker task role can read and write `ProcessingJobs` in DynamoDB.
- [ ] The ECS task execution role can pull from ECR and write logs.
- [ ] The Step Functions role can start and monitor ECS tasks and write workflow logs.

## Workflow And Triggering

- [x] The workflow input preserves bucket and object key as separate fields.
- [x] Routing is driven by `SOURCE_KEY` values shaped like `input/<site-prefix>/<file>.pdf`.
- [x] Unsupported prefixes are rejected before worker processing.
- [ ] The S3 or EventBridge trigger is active for uploads under `input/`.
- [ ] Trigger filters do not exclude supported PDF uploads by mistake.

## First Live AWS Test

- [ ] A known-good sample PDF is ready for `input/currentcatalog/sample-catalog.pdf`.
- [ ] Operators know the expected first-pass checks: Step Functions start, ECS task launch, DynamoDB job record creation, linked PDF written to `output/currentcatalog/sample-catalog.pdf`, and CloudWatch logs available.
- [ ] Operators do not treat missing flipbook publication or success notification as a worker-path failure while live secret values are still pending.

## Follow-Up Validation

- [ ] After the happy path, an unsupported-prefix upload test is planned.
- [ ] After the happy path, an invalid-PDF failure test is planned.
- [ ] After live flipbook and notification secret values are installed, a separate publication and notification success-path test is planned.

## Notes

- This checklist assumes AWS infrastructure was provisioned manually and is intended to reduce configuration drift before the first live upload test.
- The core worker path is considered deployable when this checklist is satisfied, even if publication and notification live values are staged later.
