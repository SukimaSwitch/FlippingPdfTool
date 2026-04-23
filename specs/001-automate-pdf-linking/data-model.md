# Data Model: Automated PDF Link Publishing

## Source PDF

- Purpose: Represents the uploaded catalog document that starts the workflow.
- Fields:
  - `source_bucket`: S3 bucket containing the uploaded PDF.
  - `source_key`: S3 object key for the uploaded PDF.
  - `filename`: Original source filename preserved for the output artifact.
  - `size_bytes`: Uploaded file size.
  - `uploaded_at`: Source object creation timestamp.
  - `etag`: Source object version marker when available.
- Relationships:
  - One Source PDF creates one Processing Job.

## Processing Job

- Purpose: Tracks the full lifecycle of one automated catalog-processing run.
- Fields:
  - `job_id`: Stable unique identifier for the workflow instance.
  - `source_pdf_ref`: Reference to the Source PDF.
  - `status`: `queued | processing | publishing | notifying | completed | failed | partial-success`.
  - `started_at`: Timestamp when execution begins.
  - `completed_at`: Timestamp when execution ends.
  - `current_stage`: `ingest | pdf-processing | output-write | flipbook-publish | notification | finalize`.
  - `worker_run_id`: Run identifier used by the PDF-processing pipeline for page artifacts.
  - `output_pdf_s3_key`: S3 object key for the linked PDF when created.
  - `flipbook_url`: Published flipbook URL when available.
  - `failure_stage`: Stage name when the job fails.
  - `failure_message`: Human-readable error summary.
  - `unmatched_sku_count`: Number of detected SKUs without a product URL.
  - `link_count`: Number of inserted PDF hyperlinks.
- Relationships:
  - One Processing Job owns many Page Results.
  - One Processing Job may create zero or one Published Output.
  - One Processing Job may create one or more Notification Records.
- State transitions:
  - `queued -> processing`
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

## Published Output

- Purpose: Represents the linked PDF artifact and the external published representation.
- Fields:
  - `job_id`: Parent Processing Job identifier.
  - `output_bucket`: Destination bucket for the linked PDF.
  - `output_key`: S3 object key for the linked PDF.
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
- Relationships:
  - One Processing Job may have multiple Notification Records when retries or compensating notices occur.