# FlippingPdfTool

A Python CLI application that renders catalog PDFs to JPG, identifies product figures and nearby descriptions, extracts SKUs, and adds product links back onto the figure regions in the PDF.

The pipeline now processes one page at a time, prints a live progress bar in the terminal, and can resume previously completed pages from saved page summaries.

For the cloud workflow, see `specs/001-automate-pdf-linking/aws-beginner-setup.md` for the operator guide and `aws/templates/` for the checked-in task definition, Step Functions, and EventBridge templates.

## Installation

1. Clone the repository:
2. Navigate to the project directory:
3. Install dependencies with `pip install -r requirements.txt`.
4. Configure AWS credentials with permission to call Amazon Textract.
5. Optionally set `AWS_REGION`, `TEXTRACT_ADAPTER_ID`, and `TEXTRACT_ADAPTER_VERSION`.

## Worker Runtime Prerequisites

The cloud workflow runs the PDF-linking pipeline inside an ECS Fargate worker coordinated by AWS Step Functions.

Minimum AWS prerequisites:

- An S3 bucket layout that uses `cmg-catalog-book` with `input/` and `output/` prefixes.
- AWS access for S3, Textract, Step Functions, ECS/Fargate, DynamoDB, Secrets Manager, and CloudWatch.
- A DynamoDB table for durable processing-job state.
- Secrets Manager entries for any Magento and notification credentials.
- An ECS task definition that injects worker environment variables and secrets.

Required third-party configuration:

- Magento base route access for each supported store code: `currentcatalog`, `colorfulimages`, and `lillianvernon`.
- A notification target using SES or SNS plus the stakeholder email group or topic mapping.

For a guided setup, see `specs/001-automate-pdf-linking/aws-beginner-setup.md`. For deployable AWS artifacts, see `aws/templates/README.md`.

## Worker Environment Variables

The worker container is expected to receive routing and job context from the orchestration layer.

Required worker variables:

- `JOB_ID`: Unique processing job identifier shared across logs, persistence, and notifications.
- `SOURCE_BUCKET`: Physical S3 bucket name for the uploaded source PDF.
- `SOURCE_KEY`: Full source object key such as `input/currentcatalog/sample-catalog.pdf`.
- `OUTPUT_BUCKET`: Physical S3 bucket name for the linked output PDF.
- `OUTPUT_KEY`: Full output object key such as `output/currentcatalog/sample-catalog.pdf`.
- `SITE_PREFIX`: Routed site code such as `currentcatalog`, `colorfulimages`, or `lillianvernon`.
- `PUBLIC_DOMAIN`: Site-specific public domain such as `https://www.currentcatalog.com`.
- `MAGENTO_STORE_CODE`: Site-specific Magento store code used for catalog lookups.

Common optional worker variables:

- `DYNAMODB_TABLE_NAME`: Processing-job table name.
- `AWS_REGION`: Default AWS region for SDK clients.
- `TEXTRACT_ADAPTER_ID`: Optional Textract adapter identifier.
- `TEXTRACT_ADAPTER_VERSION`: Optional Textract adapter version.
- `MAGENTO_SECRET_NAME`: Secrets Manager secret name containing Magento connection settings such as host and credentials.
- `MAGENTO_SEARCH_BASE_URL`: Optional override for the Magento API origin when it differs from `PUBLIC_DOMAIN`.
- `MAGENTO_BEARER_TOKEN_SECRET_NAME`: Secrets Manager secret name for Magento API authentication.
- `NOTIFICATION_MODE`: Notification adapter selection such as `ses` or `sns`.
- `NOTIFICATION_TARGET`: Email address, group alias, or SNS topic ARN used for job notifications.
- `NOTIFICATION_SECRET_NAME`: Secrets Manager secret name containing notification defaults such as the recipient address.
- `NOTIFICATION_SOURCE`: Required when `NOTIFICATION_MODE=ses` unless the notification secret already contains a `source` email address.
- `NOTIFICATION_TOPIC_ARN`: Required when `NOTIFICATION_MODE=sns` unless the notification secret already contains `topic_arn`.

Do not place third-party credentials directly in plain environment variables when deploying to AWS. Prefer ECS secret injection from Secrets Manager.

Example local container invocation:

```bash
docker build -t flipping-pdf-worker .

docker run --rm \
  -e JOB_ID=test-job-001 \
  -e SOURCE_BUCKET=cmg-catalog-book \
  -e SOURCE_KEY=input/currentcatalog/sample-catalog.pdf \
  -e OUTPUT_BUCKET=cmg-catalog-book \
  -e OUTPUT_KEY=output/currentcatalog/sample-catalog.pdf \
  -e SITE_PREFIX=currentcatalog \
  -e PUBLIC_DOMAIN=https://www.currentcatalog.com \
  -e MAGENTO_STORE_CODE=currentcatalog \
  -e AWS_REGION=us-east-1 \
  flipping-pdf-worker
```

## Local Worker Validation

The worker orchestration can also be exercised directly from Python without deploying AWS infrastructure.

Example routed worker payload:

```python
from src.worker.entrypoint import process_worker_request

payload = {
    "jobId": "test-job-001",
    "sourceBucket": "cmg-catalog-book",
    "sourceKey": "input/currentcatalog/sample-catalog.pdf",
    "triggeredAt": "2026-04-28T12:00:00Z",
    "notificationGroup": "catalog-ops@example.com",
}

result = process_worker_request(payload)
print(result)
```

Expected behavior:

- Accepted prefixes route to the matching `output/<site-prefix>/...` key.
- Unknown prefixes fail before PDF processing starts.
- Magento lookups only link exact SKU matches and build final customer URLs from `custom_attributes.url_key` using the routed storefront template: `currentcatalog` and `colorfulimages` use `https://<domain>/buy/<url_key>.html`, while `lillianvernon` uses `https://<domain>/goods/<url_key>.html`.
- Exact SKU matches without `url_key` remain unlinked and are recorded as unresolved matches.
- The container runtime can now bootstrap worker jobs directly from environment variables and Secrets Manager when launched with `python -m src.worker.entrypoint`.
- The worker writes the linked PDF to S3 and treats that exported artifact as a successful processing outcome.
- Failure notifications now fire for rejected-routing and processing-stage failures when notification delivery is configured.
- Success notifications include the output PDF URL so operators can access the exported file directly.
- Partial-success outcomes are limited to downstream notification delivery failures after the PDF has already been exported.

Staging note:

- A notification recipient secret provides the target address only; actual SES or SNS delivery still depends on a real sender or topic configuration in the deployed environment.
- For SES delivery, the runtime now fails fast unless it can resolve a sender email from `NOTIFICATION_SOURCE` or `NOTIFICATION_SECRET_NAME.source`.
- Automatic third-party upload has been removed from the worker runtime.

## Usage

Run the pipeline with a PDF URL or a local PDF path:

```bash
python src/main.py "https://example.com/catalog.pdf" --domain www.lillianvernon.com --debug-overlays
```

For larger PDFs, process a bounded page range and keep the run resumable:

```bash
python src/main.py "/home/xzhang/Workspace/Temp/Current Spring 2026 Sale.pdf" --domain www.lillianvernon.com --page-start 1 --page-end 25 --skip-existing
```

You can also let the script prompt for the PDF input:

```bash
python src/main.py
```

## CLI Options

- `--domain`: Destination domain used for fallback local link generation. Default: `www.currentcatalog.com`
- `--output-dir`: Directory where rendered page images and the linked PDF are written. Default: `extracted_images`
- `--figure-info-dir`: Directory where Textract JSON, overlays, and run summaries are written. Default: `figure_info`
- `--dpi`: Render DPI for the intermediate JPG files. Default: `220`
- `--url-template`: Optional full product URL template for local runs. The worker path can override link resolution through Magento-backed URL lookup.
- `--aws-region`: AWS region for Textract
- `--textract-adapter-id`: Optional Textract adapter ID
- `--textract-adapter-version`: Optional Textract adapter version
- `--page-start`: First 1-based page number to process. Default: `1`
- `--page-end`: Last 1-based page number to process. Default: process through the final page
- `--max-pages`: Maximum number of pages to process after the page range is applied
- `--resume-run-id`: Resume a previous run directory by ID
- `--skip-existing`: Restore completed pages from existing per-page summaries instead of reprocessing them
- `--keep-rendered-pages`: Keep intermediate rendered JPG files after each page is processed
- `--textract-retries`: Retry count for Textract requests. Default: `3`
- `--debug-overlays`: Writes annotated JPG overlays that show figure and description matches

## Output

Each run creates a unique subdirectory under `extracted_images/` and `figure_info/` unless `--resume-run-id` is used.

- Rendered page JPG files are written to `extracted_images/<run-id>/pages/` when `--keep-rendered-pages` or `--debug-overlays` is enabled
- The linked PDF is written to `extracted_images/<run-id>/linked_<input-name>.pdf`
- Per-page Textract responses are written to `figure_info/<run-id>/page_###_textract.json`
- Per-page processing summaries are written to `figure_info/<run-id>/page_###_summary.json`
- Match details and counts are written to `figure_info/<run-id>/run_summary.json`
- If `--debug-overlays` is enabled, annotated page overlays are written to `figure_info/<run-id>/page_###_overlay.jpg`

## Notes

- The pipeline matches `LAYOUT_FIGURE` blocks to nearby `LAYOUT_TEXT`, `LAYOUT_TITLE`, and `LAYOUT_LIST` blocks using page geometry.
- SKU extraction first tries PDF-native text from the matched page region and falls back to OCR text when the PDF has no selectable text.
- For image-only PDFs, the pipeline performs a second-pass regional OCR on high-DPI crops around each matched description to improve SKU accuracy.
- SKU extraction is regex-based and can be tuned in `src/main.py` if your catalog format differs.
- If Textract does not return figure blocks for a page, the script falls back to OpenCV-based image region detection.
- Textract calls are retried automatically up to the configured retry limit.
- The terminal prints a live page progress bar with cumulative match and link counts.

## Validation Status

Latest local validation on 2026-04-28:

- `python -m unittest tests.test_main -v`
- `python -m unittest discover -s tests -v`

Current validated coverage includes:

- Shared CLI and worker pipeline reuse
- Accepted-route processing and matched output routing
- Exact-SKU Magento matching plus unresolved `url_key` handling
- Success notification flow after routed S3 output write
- Rejected-prefix, invalid-PDF, and notification-failure handling
