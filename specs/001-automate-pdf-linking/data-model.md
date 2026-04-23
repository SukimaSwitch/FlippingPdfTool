# Data Model: Automated PDF Link Publishing

## Source PDF

- Purpose: Represents the uploaded catalog document that starts the workflow.
- Fields:
  - `source_bucket`: Physical S3 bucket name. Planned value: `cmg-catalog-book`.
  - `source_key`: Full S3 object key, for example `input/currentcatalog/spring-2026-catalog.pdf`.
  - `logical_input_location`: Derived logical import location. Planned value pattern: `cmg-catalog-book/input`.
  - `site_prefix`: Site segment extracted from the key. Allowed values: `currentcatalog | colorfulimages | lillianvernon`.
  - `filename`: Original source filename preserved for the output artifact.
  - `size_bytes`: Uploaded file size.
  - `uploaded_at`: Source object creation timestamp.
  - `etag`: Source object version marker when available.
  - `dedupe_key`: Stable identifier derived from bucket, key, and version marker to prevent ambiguous duplicate job state.
- Validation rules:
  - `source_key` must start with `input/`.
  - `source_key` must end with `.pdf`.
  - `site_prefix` must be derivable from the first segment after `input/`.
- Relationships:
  - One Source PDF creates one Processing Job.
  - One Source PDF resolves to one Site Configuration.

## Site Configuration

- Purpose: Holds the routing metadata derived from the source S3 prefix.
- Fields:
  - `site_prefix`: `currentcatalog | colorfulimages | lillianvernon`.
  - `output_prefix`: Matching output path under the logical output location, for example `output/currentcatalog/`.
  - `public_domain`: `https://www.currentcatalog.com | https://www.colorfulimages.com | https://www.lillianvernon.com`.
  - `magento_store_code`: `currentcatalog | colorfulimages | lillianvernon`.
  - `product_lookup_route_template`: `GET /rest/<store_code>/V1/products?...conditionType=like`.
- Validation rules:
  - Every supported `site_prefix` must map to exactly one `public_domain` and one `magento_store_code`.
  - Unknown prefixes are invalid and cause the job to fail during ingest-routing.
- Relationships:
  - One Site Configuration may be reused by many Processing Jobs.

## Processing Job

- Purpose: Tracks the full lifecycle of one automated catalog-processing run.
- Fields:
  - `job_id`: Stable unique identifier for the workflow instance.
  - `source_pdf_ref`: Reference to the Source PDF.
  - `site_configuration_ref`: Reference to the derived Site Configuration.
  - `status`: `queued | processing | publishing | notifying | completed | failed | partial-success`.
  - `current_stage`: `ingest-routing | pdf-processing | output-write | flipbook-publish | notification | finalize`.
  - `routing_status`: `accepted | rejected`.
  - `started_at`: Timestamp when execution begins.
  - `completed_at`: Timestamp when execution ends.
  - `worker_run_id`: Run identifier used by the PDF-processing pipeline for page artifacts.
  - `output_pdf_bucket`: Physical output bucket name. Planned value: `cmg-catalog-book`.
  - `output_pdf_key`: Output object key, for example `output/currentcatalog/spring-2026-catalog.pdf`.
  - `flipbook_url`: Published flipbook URL when available.
  - `failure_stage`: Stage name when the job fails.
  - `failure_message`: Human-readable error summary.
  - `failure_code`: Stable machine-readable code such as `unknown-prefix`, `invalid-pdf`, `publication-failed`, or `notification-failed`.
  - `unmatched_sku_count`: Number of detected SKUs without a product URL.
  - `matched_sku_count`: Number of resolved product matches.
  - `link_count`: Number of inserted PDF hyperlinks.
- Relationships:
  - One Processing Job owns many Page Results.
  - One Processing Job may create zero or one Published Output.
  - One Processing Job may create one or more Notification Records.
- State transitions:
  - `queued -> failed` when ingest-routing rejects the source key
  - `queued -> processing` when ingest-routing accepts the source key
  - `processing -> publishing`
  - `publishing -> notifying`
  - `notifying -> completed`
  - `processing -> failed`
  - `publishing -> partial-success` when linked PDF exists but publication fails
  - `notifying -> partial-success` when publication succeeds but notification fails

## Page Result

- Purpose: Captures the per-page output of OCR, matching, and link placement.
- Fields:
  - `job_id`: Parent Processing Job identifier.
  - `page_number`: 1-based page number.
  - `rendered_image_key`: Optional artifact path for the rendered JPG.
  - `textract_result_key`: Optional artifact path for the Textract response.
  - `summary_key`: Optional artifact path for the page summary.
  - `status`: `processed | skipped | failed`.
  - `figure_count`: Number of figure candidates considered.
  - `match_count`: Number of Product Matches resolved on the page.
  - `unmatched_skus`: List of detected SKUs with no resolved product URL.
  - `error_message`: Page-level failure details when applicable.
- Relationships:
  - One Page Result belongs to one Processing Job.
  - One Page Result may contain many Product Matches.

## Product Match

- Purpose: Represents one resolved product link candidate for an image-description pair.
- Fields:
  - `job_id`: Parent Processing Job identifier.
  - `page_number`: Page containing the match.
  - `sku`: Detected product SKU.
  - `product_url`: Resolved destination URL.
  - `public_domain`: Domain selected from the Site Configuration.
  - `magento_store_code`: Store code used for the lookup request.
  - `figure_bbox`: Normalized bounding box for the figure link region.
  - `description_bbox`: Normalized bounding box for the description link region when present.
  - `description_text`: Matched descriptive text.
  - `sku_source`: `pdf | regional-ocr | page-ocr`.
  - `score`: Matching confidence or ranking score.
  - `status`: `linked | unmatched`.
- Validation rules:
  - `product_url` is required only when `status = linked`.
  - `figure_bbox` must always be present for linkable matches.
  - `description_bbox` is optional because some matches may link image-only regions.
  - `public_domain` and `magento_store_code` must match the parent Site Configuration.

## Published Output

- Purpose: Represents the linked PDF artifact and the external published representation.
- Fields:
  - `job_id`: Parent Processing Job identifier.
  - `output_bucket`: Destination bucket for the linked PDF. Planned value: `cmg-catalog-book`.
  - `output_key`: S3 object key for the linked PDF, preserving the site-matching prefix and original filename.
  - `published_at`: Timestamp when flipbook publication succeeds.
  - `flipbook_url`: External publication URL.
  - `publication_status`: `pending | published | failed`.
- Relationships:
  - One Published Output belongs to one Processing Job.

## Notification Record

- Purpose: Records the notification sent for success, failure, or partial success.
- Fields:
  - `job_id`: Parent Processing Job identifier.
  - `notification_type`: `success | failure | partial-success`.
  - `recipient_group`: Logical email group name or address list reference.
  - `sent_at`: Timestamp when delivery is attempted.
  - `delivery_status`: `sent | failed`.
  - `message_subject`: Rendered notification subject.
  - `message_summary`: Compact message body summary.
  - `included_flipbook_url`: Flipbook URL included for success and eligible partial-success messages.
  - `included_failure_stage`: Failed stage included for triage-oriented notifications.
- Relationships:
  - One Processing Job may have multiple Notification Records when retries or compensating notices occur.