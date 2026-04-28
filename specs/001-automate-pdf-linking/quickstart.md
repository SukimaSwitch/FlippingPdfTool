# Quickstart: Automated PDF Link Publishing

## Goal

Validate the planned workflow that automates PDF linking, site-aware routing, Magento URL resolution, flipbook publication, and stakeholder notification around the existing `src/main.py` pipeline.

## Prerequisites

- Python environment available for local tests.
- AWS credentials with access to S3, Textract, Step Functions, ECS/Fargate, DynamoDB, Secrets Manager, and the selected notification mechanism.
- Test credentials for Magento product search and the flipbook service.
- A representative catalog PDF, ideally including at least one exact Magento match, one partial-only Magento response, and one exact match missing `url_key`.
- Docker or another container runtime for local worker validation.

## 1. Verify the local pipeline baseline

Run the current test suite to confirm the PDF-linking core is stable before orchestration work is exercised.

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Optionally run the CLI locally against a representative PDF to confirm the baseline artifact set.

```bash
python src/main.py "/path/to/sample-catalog.pdf" --domain www.currentcatalog.com --skip-existing
```

Expected result:

- A linked PDF is produced locally.
- Per-page summaries and Textract artifacts are created.
- Link annotations remain visible after saving and reopening the output PDF.

## 2. Validate ingest-routing decisions before worker execution

Use representative S3 event payloads or routing-unit tests.

Acceptance cases:

- `input/currentcatalog/spring-2026-catalog.pdf` resolves to `https://www.currentcatalog.com`, store code `currentcatalog`, and output key `output/currentcatalog/spring-2026-catalog.pdf`.
- `input/colorfulimages/spring-2026-catalog.pdf` resolves to `https://www.colorfulimages.com`, store code `colorfulimages`, and output key `output/colorfulimages/spring-2026-catalog.pdf`.
- `input/lillianvernon/spring-2026-catalog.pdf` resolves to `https://www.lillianvernon.com`, store code `lillianvernon`, and output key `output/lillianvernon/spring-2026-catalog.pdf`.
- `input/unknown/spring-2026-catalog.pdf` is rejected during ingest-routing and does not invoke PDF processing.

Expected result:

- Every supported prefix produces one deterministic site configuration.
- Unknown prefixes create a failed job record with a routing-stage error and no worker run ID.

## 3. Validate Magento URL resolution rules in isolation

Test the catalog lookup adapter with representative Magento responses before running end-to-end jobs.

Required validation cases:

- The worker calls `GET /rest/<store_code>/V1/products?...conditionType=like` using the routed store code.
- If the search response contains an item whose `sku` exactly equals the detected catalog SKU and that item has `custom_attributes[].attribute_code = url_key`, build the final link as `https://<domain>/<url_key>.html`.
- If the response contains only partial or fuzzy SKU candidates, add no link and count the SKU as unmatched.
- If the response contains an exact SKU match but no `url_key`, add no link and record an unresolved match for triage.

Expected result:

- Only exact SKU equality can produce a link.
- Final URLs come from `url_key`, not directly from SKU.
- Missing `url_key` does not fail the job.

## 4. Run the worker locally with a routed payload

Build the worker image.

```bash
docker build -t flipping-pdf-worker .
```

Run the worker with routed environment variables.

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

Optional direct Python validation path:

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

Expected result:

- The worker downloads the source PDF from S3.
- Magento lookups use the routed store code.
- Exact-match products with `url_key` produce `https://<domain>/<url_key>.html` links.
- Exact-match products without `url_key` remain unlinked and are recorded as unresolved.
- The worker uploads the linked PDF and diagnostic artifacts and emits a structured processing result.

## 5. Exercise orchestration, publication, and notification

Trigger the workflow with a test upload or a representative routed payload.

Expected result:

- A `Processing Job` record is created.
- Accepted jobs advance through routing, processing, publication, notification, and finalization.
- Successful jobs record the flipbook URL and send a success notification containing the filename, final status, and flipbook URL.

## 6. Validate failure and partial-success paths

Test at least these scenarios:

- Invalid PDF source.
- Unsupported site prefix.
- SKU with no exact Magento match.
- Exact Magento match without `url_key`.
- Flipbook publication failure after the linked PDF is created.
- Notification delivery failure after publication succeeds.

Expected result:

- Invalid PDFs end in a failed job with processing-stage error details.
- Unsupported prefixes fail during ingest-routing before worker invocation.
- Non-exact or missing Magento matches do not fail the overall job.
- Missing `url_key` cases are recorded as unresolved matches.
- Publication and notification failures preserve already-created artifacts and record the failed stage.

## 7. Latest Local Validation Snapshot

Validated locally on 2026-04-28:

```bash
.venv/bin/python -m unittest tests.test_main -v
.venv/bin/python -m unittest discover -s tests -v
```

Observed result:

- The current suite passed locally before this planning refresh.
- Coverage includes shared CLI and worker reuse plus contract and integration coverage for routed processing, publication, success notification, rejected routing, invalid-PDF handling, publication failure, and notification failure.

Open validation gap:

- Live AWS integration remains unverified in automation and still depends on real infrastructure, credentials, and third-party endpoints.
