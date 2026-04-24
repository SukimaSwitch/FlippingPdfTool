# Quickstart: Automated PDF Link Publishing

## Goal

Validate the planned workflow that automates PDF linking, site-aware routing, publication, and notification around the existing `src/main.py` pipeline.

## Prerequisites

- Python environment installed for local tests.
- AWS credentials with access to S3, Textract, Step Functions, ECS/Fargate, DynamoDB, Secrets Manager, and the chosen notification mechanism.
- Test credentials for the Magento product catalog lookup and flipbook service.
- A sample catalog PDF larger than 70 MB with more than 80 pages.
- A container runtime such as Docker for local worker validation.

## 1. Verify the current local pipeline baseline

Run the existing unit tests to confirm the PDF-linking core still behaves as expected.

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Run the current CLI locally against a representative PDF to confirm the baseline artifact set.

```bash
python src/main.py "/path/to/sample-catalog.pdf" --domain www.currentcatalog.com --skip-existing
```

Expected result:

- A linked PDF is produced locally.
- Per-page summaries and Textract artifacts are created.
- Link annotations are visible after saving and reopening the output PDF.

## 2. Validate ingest-routing decisions before the worker runs

Use representative S3 event payloads or unit tests for the routing helper.

Acceptance cases:

- `input/currentcatalog/spring-2026-catalog.pdf` resolves to domain `https://www.currentcatalog.com`, store code `currentcatalog`, and output key `output/currentcatalog/spring-2026-catalog.pdf`.
- `input/colorfulimages/spring-2026-catalog.pdf` resolves to domain `https://www.colorfulimages.com`, store code `colorfulimages`, and output key `output/colorfulimages/spring-2026-catalog.pdf`.
- `input/lillianvernon/spring-2026-catalog.pdf` resolves to domain `https://www.lillianvernon.com`, store code `lillianvernon`, and output key `output/lillianvernon/spring-2026-catalog.pdf`.
- `input/unknown/spring-2026-catalog.pdf` is rejected during ingest-routing and does not invoke PDF processing.

Expected result:

- Every supported prefix produces a deterministic site configuration.
- Unknown prefixes create a failed job record with a routing-stage error and no worker run ID.

## 3. Containerize and invoke the worker entrypoint

Build the worker image that wraps the current pipeline plus cloud adapters.

```bash
docker build -t flipping-pdf-worker .
```

Run the worker locally with environment variables or a JSON payload that mimic a routed cloud job.

```bash
docker run --rm \
  -e JOB_ID=test-job-001 \
  -e SOURCE_BUCKET=cmg-catalog-book \
  -e SOURCE_KEY=input/currentcatalog/sample-catalog.pdf \
  -e OUTPUT_BUCKET=cmg-catalog-book \
  -e OUTPUT_KEY=output/currentcatalog/sample-catalog.pdf \
  -e SITE_PREFIX=currentcatalog \
  -e PUBLIC_DOMAIN=https://www.currentcatalog.com \
  -e MAGENTO_STORE_CODE=currentcatalog \
  flipping-pdf-worker
```

Expected result:

- The worker downloads the source PDF from S3.
- The worker performs Magento lookups with the configured store code.
- The worker uploads the linked PDF and diagnostic artifacts to S3.
- The worker emits a structured processing result payload.

## 4. Exercise the orchestration flow

Trigger the workflow with a test PDF upload or a representative S3 event payload.

Example worker input payload:

```json
{
  "jobId": "test-job-001",
  "sourceBucket": "cmg-catalog-book",
  "sourceKey": "input/currentcatalog/sample-catalog.pdf",
  "outputBucket": "cmg-catalog-book",
  "outputKey": "output/currentcatalog/sample-catalog.pdf",
  "triggeredAt": "2026-04-23T12:00:00Z"
}
```

Expected result:

- A Processing Job record is created.
- Job state first records ingest-routing acceptance or rejection.
- Accepted jobs run asynchronously without depending on short-lived upload event execution.
- Accepted jobs advance through processing, publication, notification, and finalization.

## 5. Validate publication and notification

Use a successful worker result to continue the flow.

Expected result:

- The processed PDF is published to the flipbook service.
- The success notification includes the original filename, final status, and flipbook URL.
- The notification payload also reflects the source site prefix and resulting output location for auditability.

## 6. Validate failure and partial-success paths

Test at least these scenarios:

- Invalid PDF source.
- Unknown S3 site prefix.
- SKU not found in the product catalog.
- Flipbook publication failure after the linked PDF is already created.
- Notification delivery failure after publication succeeds.

Expected result:

- Invalid PDFs end in a failed Processing Job with error details.
- Unknown prefixes fail during ingest-routing before worker invocation.
- Unmatched SKUs produce no links for those items and do not fail the job.
- Publication and notification failures preserve already-created artifacts and record the failed stage.
