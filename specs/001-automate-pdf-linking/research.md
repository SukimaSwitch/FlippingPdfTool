# Research: Automated PDF Link Publishing

## Decision 1: Use Step Functions to orchestrate a Fargate worker for PDF processing

- Decision: Use S3 object-created events to start an AWS Step Functions state machine, and run the existing PDF-processing pipeline inside an ECS Fargate task.
- Rationale: The current pipeline is CPU and OCR heavy, processes pages sequentially, and is expected to handle large PDFs beyond practical Lambda execution limits. Step Functions provides workflow stage visibility, retry handling, and explicit control-flow transitions for processing, publication, and notification. Fargate runs the current Python stack inside a long-running Linux container without server management.
- Alternatives considered:
  - Single Lambda workflow: rejected because OCR-heavy PDFs and 80+ page inputs can exceed Lambda runtime and memory comfort.
  - SQS plus custom worker coordination: viable, but it pushes retry logic, status tracking, and stage transitions into application code instead of managed orchestration.
  - AWS Batch as the primary orchestrator: viable for larger-scale batch fleets, but heavier than necessary for a per-upload business workflow with several non-compute stages.

## Decision 2: Preserve the current PDF pipeline as the domain core and add service adapters around it

- Decision: Keep the existing PDF parsing, OCR interpretation, SKU extraction, and link-placement logic as the domain core, and add orchestration, storage, lookup, publication, and notification adapters around it.
- Rationale: The repository already contains a functioning page-by-page CLI pipeline with tests around SKU extraction and persisted link annotations. Reusing that core reduces behavioral drift and limits the refactor surface to integration boundaries.
- Alternatives considered:
  - Rewrite the pipeline for cloud-only execution: rejected because it increases delivery risk without clear business benefit.
  - Embed all cloud logic directly into `src/main.py`: rejected because it would entangle orchestration with PDF-processing logic and make testing harder.

## Decision 3: Use S3 for documents and artifacts, and DynamoDB for durable job-state tracking

- Decision: Store source PDFs, linked PDFs, and optional diagnostic artifacts in S3, and persist processing-job stage/state metadata in DynamoDB.
- Rationale: The spec requires durable visibility into ingest, processing, publication, notification, and final job status. Step Functions execution history alone is useful for workflow debugging, but DynamoDB gives stable queryable job records, supports notification summaries, and decouples retained business status from orchestration retention windows.
- Alternatives considered:
  - Step Functions execution history only: rejected because it is less suitable for durable business-facing status lookup and artifact association.
  - Local container files only: rejected because worker-local artifacts disappear after task completion.

## Decision 4: Integrate Magento, Flipbook, and notification delivery through dedicated clients with Secrets Manager credentials

- Decision: Implement separate integration clients for SKU-based Magento lookup, flipbook publication, and stakeholder notification, and source secrets from AWS Secrets Manager.
- Rationale: Each external system has distinct retry, error-reporting, and payload requirements. Dedicated clients make failures stage-specific, simplify unit tests, and keep secrets out of code and long-lived plain environment configuration.
- Alternatives considered:
  - Call all services inline from the worker without adapters: rejected because it hides stage boundaries and weakens testability.
  - Store credentials directly in code or unchecked environment files: rejected for operational and security reasons.

## Decision 5: Treat unmatched SKUs as non-failures and preserve page output without links

- Decision: When SKU extraction succeeds but the product catalog lookup returns no product URL, record the unmatched result, leave the corresponding image and description unchanged, and continue processing the rest of the job.
- Rationale: The feature explicitly allows unmatched products to be handled manually later. This avoids false job failures while preserving the remainder of the output PDF and related diagnostics.
- Alternatives considered:
  - Fail the entire job on the first unmatched SKU: rejected because it blocks delivery of valid links for the rest of the catalog.
  - Insert placeholder links or fallback URLs: rejected because it creates misleading output and complicates manual follow-up.

## Decision 6: Retain per-page processing artifacts behind configurable storage lifecycle rules

- Decision: Continue producing run-scoped artifacts such as per-page summaries and debug outputs, but store them in S3 with configurable lifecycle management.
- Rationale: The current CLI already emits per-page and run-level artifacts that help explain OCR and matching behavior. Preserving that model in cloud storage supports debugging while keeping long-term storage cost under control.
- Alternatives considered:
  - Disable all artifact retention: rejected because it removes the primary debugging surface for OCR and matching problems.
  - Retain artifacts indefinitely with no lifecycle control: rejected because storage costs will grow with each large catalog run.