# Quickstart: Automated PDF Link Publishing

## Goal

Validate the planned workflow that automates PDF linking, publication, and notification around the existing `src/main.py` pipeline.

## Prerequisites

- Python environment installed for local tests.
- AWS credentials with access to S3, Textract, orchestration services, and the chosen notification mechanism.
- Test credentials for the product catalog lookup and flipbook service.
- A sample catalog PDF larger than 70 MB with more than 80 pages.

## 1. Verify the current local pipeline baseline

Run the existing unit tests to confirm the PDF-linking core still behaves as expected.

```bash
/home/xzhang/project/FlippingPdfTool/.venv/bin/python -m unittest discover -s tests -v
```

Run the current CLI locally against a representative PDF to confirm the baseline artifact set.

```bash
python src/main.py "/path/to/sample-catalog.pdf" --domain www.currentcatalog.com --skip-existing
```

Expected result:

- A linked PDF is produced locally.
- Per-page summaries and Textract artifacts are created.
- Link annotations are visible after saving and reopening the output PDF.

## 2. Containerize and invoke the worker entrypoint

Build the worker image that wraps the current pipeline plus cloud adapters.

```bash
docker build -t flipping-pdf-worker .
```

Run the worker locally with environment variables that mimic a cloud job payload.

```bash
docker run --rm \
  -e JOB_ID=test-job-001 \
  -e SOURCE_BUCKET=catalog-input-bucket \
  -e SOURCE_KEY=imports/sample-catalog.pdf \
  -e OUTPUT_BUCKET=catalog-output-bucket \
  -e OUTPUT_KEY=processed/sample-catalog.pdf \
  flipping-pdf-worker
```

Expected result:

- The worker downloads the source PDF from S3.
- The worker uploads the linked PDF and diagnostic artifacts to S3.
- The worker emits a structured processing result payload.

## 3. Exercise the orchestration flow

Trigger the workflow with a test PDF upload or a representative event payload.

Expected result:

- A Processing Job record is created.
- The worker runs asynchronously without depending on Lambda runtime duration.
- Job state advances through ingest, processing, publication, notification, and finalization.

## 4. Validate publication and notification

Use a successful worker result to continue the flow.

Expected result:

- The processed PDF is published to the flipbook service.
- The success notification includes the original filename, final status, and flipbook URL.

## 5. Validate failure and partial-success paths

Test at least these scenarios:

- Invalid PDF source.
- SKU not found in the product catalog.
- Flipbook publication failure after the linked PDF is already created.
- Notification delivery failure after publication succeeds.

Expected result:

- Invalid PDFs end in a failed Processing Job with error details.
- Unmatched SKUs produce no links for those items and do not fail the job.
- Publication and notification failures preserve already-created artifacts and record the failed stage.