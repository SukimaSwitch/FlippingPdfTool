# Data Model: Automated PDF Link Publishing

## Source PDF

Represents the uploaded catalog object that triggers the workflow.

| Field | Type | Required | Notes |
| ----- | ----- | -------- | ----- |
| `source_bucket` | string | Yes | Physical bucket name. Must be `cmg-catalog-book`. |
| `source_key` | string | Yes | Full object key such as `input/currentcatalog/spring-2026-catalog.pdf`. |
| `filename` | string | Yes | Original filename preserved for output naming and notifications. |
| `site_prefix` | enum | Derived | `currentcatalog`, `colorfulimages`, or `lillianvernon`, derived from `source_key`. |
| `size_bytes` | integer | No | Source object size for diagnostics and capacity tracking. |
| `uploaded_at` | datetime | No | Object-created timestamp. |
| `etag` | string | No | Source object version marker when available. |
| `dedupe_key` | string | No | Stable identifier derived from bucket, key, and version marker to prevent ambiguous duplicate job state. |

**Validation rules**:

- `source_key` must start with `input/`.
- `source_key` must end with `.pdf`.
- Unsupported site prefixes fail ingest-routing before PDF processing starts.

## Site Configuration

Routing metadata derived from the source prefix.

| Field | Type | Required | Notes |
| ----- | ----- | -------- | ----- |
| `site_prefix` | enum | Yes | `currentcatalog`, `colorfulimages`, `lillianvernon`. |
| `input_prefix` | string | Yes | `input/<site_prefix>/`. |
| `output_prefix` | string | Yes | `output/<site_prefix>/`. |
| `public_domain` | string | Yes | `https://www.currentcatalog.com`, `https://www.colorfulimages.com`, or `https://www.lillianvernon.com`. |
| `magento_store_code` | string | Yes | Store code used in `/rest/<store_code>/V1/products...`. |
| `magento_lookup_route_template` | string | Yes | Route template containing the site-specific store code and the SKU search filter. |

**Relationships**:

- One `Source PDF` resolves to exactly one `Site Configuration`.
- One `Site Configuration` can be reused by many `Processing Job` records.

## Processing Job

The end-to-end workflow record for one uploaded PDF.

| Field | Type | Required | Notes |
| ----- | ----- | -------- | ----- |
| `job_id` | string | Yes | Stable identifier shared across orchestration, worker logs, persistence, and notifications. |
| `source_pdf_ref` | Source PDF | Yes | The uploaded source document metadata. |
| `site_configuration_ref` | Site Configuration | Yes | Derived routing configuration. |
| `status` | enum | Yes | `received`, `routing_failed`, `routed`, `processing`, `processed`, `published`, `completed`, `partial_failure`, `failed`, `completed_with_errors`. |
| `current_stage` | enum | Yes | `ingest_routing`, `download`, `processing`, `upload`, `publication`, `notification`, `finalize`. |
| `started_at` | datetime | Yes | Job start timestamp. |
| `completed_at` | datetime | No | Set when a terminal state is reached. |
| `worker_run_id` | string | No | Run identifier used by the page-processing pipeline for artifact scoping. |
| `output_bucket` | string | No | Physical output bucket. Expected value: `cmg-catalog-book`. |
| `output_key` | string | No | Output PDF key such as `output/currentcatalog/spring-2026-catalog.pdf`. |
| `artifact_prefix` | string | No | Persisted artifact namespace such as `artifacts/<job_id>/`. |
| `flipbook_url` | string | No | Set when publication succeeds. |
| `failure_stage` | string | No | Set when a stage fails. |
| `failure_code` | string | No | Stable machine-readable error category. |
| `failure_message` | string | No | Human-readable triage detail. |
| `page_count` | integer | No | Total processed pages. |
| `matched_product_count` | integer | No | Count of successfully linked product matches. |
| `unmatched_product_count` | integer | No | Count of detected SKUs with no exact Magento match. |
| `unresolved_match_count` | integer | No | Count of exact Magento matches that lacked `url_key` and therefore remained unlinked. |
| `link_count` | integer | No | Count of inserted PDF hyperlinks. |

### Processing Job State Transitions

| From | To | Condition |
| ---- | -- | --------- |
| `received` | `routing_failed` | Source key is invalid or site prefix is unsupported. |
| `received` | `routed` | Source file is valid and site configuration is derived successfully. |
| `routed` | `processing` | Worker downloads the PDF and begins page processing. |
| `processing` | `processed` | Linked PDF and page artifacts are produced successfully. |
| `processed` | `published` | Flipbook publication returns a URL. |
| `published` | `completed` | Success notification is sent and final state is recorded. |
| `processing` | `failed` | PDF processing fails before a linked PDF is produced. |
| `processed` | `partial_failure` | Publication fails after the linked PDF exists. |
| `published` | `partial_failure` | Notification fails after publication succeeds. |
| `partial_failure` | `completed_with_errors` | Finalization preserves artifacts and records the downstream failure. |

## Page Result

Per-page processing output used for diagnostics and resumability.

| Field | Type | Required | Notes |
| ----- | ----- | -------- | ----- |
| `job_id` | string | Yes | Parent job identifier. |
| `page_number` | integer | Yes | 1-based page number. |
| `status` | enum | Yes | `processed`, `restored`, `failed`, `skipped`. |
| `rendered_image_key` | string | No | Artifact location for the rendered JPG when retained. |
| `textract_artifact_key` | string | No | Artifact location for the Textract JSON. |
| `summary_artifact_key` | string | No | Artifact location for the page summary. |
| `figure_count` | integer | No | Number of figure candidates on the page. |
| `match_count` | integer | No | Number of successful links placed on the page. |
| `unmatched_sku_count` | integer | No | Detected SKUs with no exact Magento match. |
| `unresolved_match_count` | integer | No | Exact Magento matches missing `url_key`. |
| `notes` | string | No | Error details or recovery notes. |

## Product Match

Resolved association between page content and a final product URL.

| Field | Type | Required | Notes |
| ----- | ----- | -------- | ----- |
| `job_id` | string | Yes | Parent job identifier. |
| `page_number` | integer | Yes | Page where the match occurs. |
| `sku` | string | Yes | Extracted product identifier. |
| `product_url` | string | Yes | Final URL `https://<domain>/<url_key>.html`. |
| `public_domain` | string | Yes | Domain selected from `Site Configuration`. |
| `url_key` | string | Yes | Canonical slug extracted from Magento `custom_attributes`. |
| `figure_bbox` | object | Yes | Figure region to annotate in the PDF. |
| `description_bbox` | object | No | Description text region when available. |
| `sku_source` | enum | Yes | `pdf`, `regional_ocr`, or `page_ocr`. |
| `score` | number | No | Matching confidence or ranking score. |
| `matched_at` | datetime | Yes | Timestamp of link resolution. |

**Validation rules**:

- `product_url` must use the `public_domain` selected by the parent `Site Configuration`.
- `url_key` must be non-empty.
- `sku` must exactly equal the matched Magento product SKU.

## Unresolved Product Match

Represents a catalog SKU candidate that could not be converted into a final product URL even after an exact Magento product match was found.

| Field | Type | Required | Notes |
| ----- | ----- | -------- | ----- |
| `job_id` | string | Yes | Parent job identifier. |
| `page_number` | integer | Yes | Page where the unresolved condition occurred. |
| `sku` | string | Yes | Detected catalog SKU. |
| `matched_magento_sku` | string | Yes | Exact Magento SKU that matched the catalog SKU. |
| `reason` | enum | Yes | Currently `missing_url_key`. |
| `figure_bbox` | object | No | Figure region that would have been linked. |
| `description_bbox` | object | No | Description region that would have been linked. |
| `recorded_at` | datetime | Yes | Timestamp when the unresolved match was recorded. |

## Magento Product Response

The subset of Magento product data needed for URL resolution.

| Field | Type | Required | Notes |
| ----- | ----- | -------- | ----- |
| `sku` | string | Yes | Used for exact equality validation against the detected catalog SKU. |
| `id` | integer | No | Product identifier returned by Magento. |
| `name` | string | No | Helpful for diagnostics only. |
| `custom_attributes` | array | Yes | Must be searched for an element whose `attribute_code` is `url_key`. |
| `url_key` | string | Derived | Derived from `custom_attributes[].value` where `attribute_code = url_key`. |

**Validation rules**:

- Search responses may return partial or fuzzy candidates; only exact SKU equality can produce a linkable match.
- If exact SKU equality exists but `url_key` is absent, record an `Unresolved Product Match` and do not add a link.

## Published Output

Linked PDF artifact plus external publication result.

| Field | Type | Required | Notes |
| ----- | ----- | -------- | ----- |
| `job_id` | string | Yes | Parent job identifier. |
| `linked_pdf_bucket` | string | Yes | Physical bucket for the linked PDF. |
| `linked_pdf_key` | string | Yes | Output object key preserving the site prefix and original filename. |
| `publication_status` | enum | Yes | `pending`, `published`, `failed`. |
| `flipbook_url` | string | No | Set only when publication succeeds. |
| `published_at` | datetime | No | Set when publication succeeds. |

## Notification Record

Represents an outbound stakeholder notification attempt.

| Field | Type | Required | Notes |
| ----- | ----- | -------- | ----- |
| `job_id` | string | Yes | Parent job identifier. |
| `notification_type` | enum | Yes | `success`, `failure`, `partial_failure`. |
| `recipient_group` | string | Yes | Configured destination group or address list. |
| `payload_summary` | object | Yes | Includes filename, final status, flipbook URL when present, and failure details when applicable. |
| `delivery_status` | enum | Yes | `pending`, `sent`, `failed`. |
| `attempted_at` | datetime | No | Timestamp of the latest delivery attempt. |
| `delivery_error` | string | No | Delivery failure details when sending fails. |

## Relationships Overview

- One `Processing Job` has one `Source PDF` and one `Site Configuration`.
- One `Processing Job` has many `Page Result` records.
- One `Processing Job` has many `Product Match` records.
- One `Processing Job` may have many `Unresolved Product Match` records.
- One `Processing Job` has zero or one `Published Output`.
- One `Processing Job` has one or more `Notification Record` entries over its lifecycle.
