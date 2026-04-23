# Data Model: Automated PDF Link Publishing

## Source PDF

Represents the uploaded catalog object that triggers processing.

| Field | Type | Required | Notes |
|------|------|----------|-------|
| `source_bucket` | string | Yes | Must be `cmg-catalog-book/input`. |
| `source_key` | string | Yes | Must begin with one of `currentcatalog/`, `colorfulimages/`, or `lillianvernon/`. |
| `filename` | string | Yes | Original PDF filename, preserved for output naming and notifications. |
| `size_bytes` | integer | Yes | Used for diagnostics and operational visibility. |
| `uploaded_at` | datetime | Yes | Ingestion timestamp. |
| `content_type` | string | No | Expected to be `application/pdf`. |
| `site_code` | string | Derived | Derived from the first S3 key segment. |

**Validation rules**:
- `source_key` must end in `.pdf`.
- Unsupported prefixes fail routing before page processing begins.
- Non-PDF content is out of scope and should fail ingestion validation.

## Site Configuration

Routing metadata derived from the source prefix.

| Field | Type | Required | Notes |
|------|------|----------|-------|
| `site_code` | enum | Yes | `currentcatalog`, `colorfulimages`, `lillianvernon`. |
| `input_prefix` | string | Yes | Site-specific prefix under `cmg-catalog-book/input`. |
| `output_prefix` | string | Yes | Matching site-specific prefix under `cmg-catalog-book/output`. |
| `product_domain` | string | Yes | Site-specific base domain used to generate product URLs. |
| `magento_store_code` | string | Yes | Used in `/rest/<store_code>/V1/products...`. |

**Relationships**:
- One `Source PDF` resolves to exactly one `Site Configuration`.
- One `Site Configuration` can be reused by many jobs.

## Processing Job

The top-level lifecycle record for one uploaded PDF.

| Field | Type | Required | Notes |
|------|------|----------|-------|
| `job_id` | string | Yes | Unique identifier shared across orchestration, worker logs, and notifications. |
| `source_pdf` | Source PDF | Yes | Input document metadata. |
| `site_configuration` | Site Configuration | Yes | Derived routing configuration. |
| `status` | enum | Yes | See state transitions below. |
| `current_stage` | enum | Yes | `ingest`, `routing`, `download`, `processing`, `upload`, `publication`, `notification`, `finalize`. |
| `started_at` | datetime | Yes | Job start timestamp. |
| `completed_at` | datetime | No | Set when terminal state is reached. |
| `output_bucket` | string | No | Expected to be `cmg-catalog-book/output` for successful or partial-success jobs. |
| `output_key` | string | No | Output PDF key mirroring the site prefix and filename. |
| `flipbook_url` | string | No | Present only when publication succeeds. |
| `failure_stage` | string | No | Set when a stage fails. |
| `failure_code` | string | No | Stable machine-readable error category. |
| `failure_message` | string | No | Human-readable triage detail. |
| `page_count` | integer | No | Total pages discovered in the PDF. |
| `matched_product_count` | integer | No | Count of successful product-link matches. |
| `unmatched_product_count` | integer | No | Count of SKU candidates without a resolvable destination URL. |

### Processing Job State Transitions

| From | To | Condition |
|------|----|-----------|
| `received` | `routing_failed` | Source key prefix is unsupported or input is invalid. |
| `received` | `routed` | Source file is valid and site configuration is resolved. |
| `routed` | `processing` | Worker downloads the PDF and begins page processing. |
| `processing` | `processed` | Linked PDF and page artifacts are produced successfully. |
| `processed` | `published` | Flipbook publication returns a URL. |
| `published` | `completed` | Notification succeeds and final state is recorded. |
| `processing` | `failed` | PDF processing fails before a linked PDF is produced. |
| `processed` | `partial_failure` | Publication or notification fails after the linked PDF exists. |
| `partial_failure` | `completed_with_errors` | Finalization completes with preserved artifacts and explicit failure metadata. |

## Page Result

Per-page processing output used for diagnostics and resumability.

| Field | Type | Required | Notes |
|------|------|----------|-------|
| `job_id` | string | Yes | Parent job identifier. |
| `page_number` | integer | Yes | 1-based page number. |
| `status` | enum | Yes | `processed`, `restored`, `failed`, `skipped`. |
| `textract_artifact_key` | string | No | Path or S3 key to Textract JSON. |
| `summary_artifact_key` | string | No | Path or S3 key to per-page summary. |
| `figure_count` | integer | No | Figures detected on the page. |
| `match_count` | integer | No | Links created on the page. |
| `unmatched_sku_count` | integer | No | SKU candidates left unlinked. |
| `notes` | string | No | Error details or recovery notes. |

## Product Match

Resolved association between page content and a destination product URL.

| Field | Type | Required | Notes |
|------|------|----------|-------|
| `job_id` | string | Yes | Parent job identifier. |
| `page_number` | integer | Yes | Page where the match occurs. |
| `sku` | string | Yes | Extracted product identifier. |
| `product_url` | string | Yes | Final link URL, site-specific. |
| `figure_bbox` | object | Yes | Figure bounding box to annotate in the PDF. |
| `description_bbox` | object | No | Description text bounding box, when available. |
| `score` | number | Yes | Match confidence or ranking score. |
| `sku_source` | enum | Yes | `pdf`, `regional-ocr`, or `ocr`. |
| `matched_at` | datetime | Yes | Timestamp of resolution. |

**Validation rules**:
- `product_url` must match the selected `Site Configuration.product_domain`.
- `sku` must be non-empty and conform to the pipeline's SKU extraction rules.

## Published Output

Linked PDF artifact plus publication result.

| Field | Type | Required | Notes |
|------|------|----------|-------|
| `job_id` | string | Yes | Parent job identifier. |
| `linked_pdf_bucket` | string | Yes | Output bucket for the processed PDF. |
| `linked_pdf_key` | string | Yes | Output object key. |
| `flipbook_url` | string | No | Set after successful publication. |
| `published_at` | datetime | No | Set when publication succeeds. |
| `publication_status` | enum | Yes | `pending`, `published`, `failed`. |

## Notification Record

Represents an outbound stakeholder notification attempt.

| Field | Type | Required | Notes |
|------|------|----------|-------|
| `job_id` | string | Yes | Parent job identifier. |
| `notification_type` | enum | Yes | `success`, `failure`, `partial_failure`. |
| `recipient_group` | string | Yes | Configured destination group. |
| `payload_summary` | object | Yes | Includes filename, final status, failed stage, and flipbook URL when present. |
| `delivery_status` | enum | Yes | `pending`, `sent`, `failed`. |
| `attempted_at` | datetime | No | Timestamp for the latest delivery attempt. |
| `delivery_error` | string | No | Error details when delivery fails. |

## Relationships Overview

- One `Processing Job` has one `Source PDF` and one `Site Configuration`.
- One `Processing Job` has many `Page Result` records.
- One `Processing Job` has many `Product Match` records.
- One `Processing Job` has zero or one `Published Output`.
- One `Processing Job` has one or more `Notification Record` entries over its lifecycle.
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