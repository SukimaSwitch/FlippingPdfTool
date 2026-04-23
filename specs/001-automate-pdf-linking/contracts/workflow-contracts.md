# Workflow Contracts: Automated PDF Link Publishing

## 1. Ingest Event Contract

- Purpose: Minimum source event data required to start a processing job.
- Producer: S3 object-created trigger.
- Consumer: Workflow starter.

### Required fields

```json
{
  "bucket": "catalog-input-bucket",
  "key": "imports/spring-2026-catalog.pdf",
  "sizeBytes": 73400320,
  "etag": "abc123",
  "eventTime": "2026-04-23T18:30:00Z"
}
```

### Contract rules

- `key` must reference a PDF object.
- `sizeBytes` is captured for job diagnostics and capacity planning.
- Duplicate events for the same object version must resolve to one logical Processing Job.

## 2. Worker Input Contract

- Purpose: Defines the payload used to run the containerized PDF processor.
- Producer: Workflow orchestrator.
- Consumer: Worker entrypoint.

### Required fields

```json
{
  "jobId": "job-20260423-001",
  "sourceBucket": "catalog-input-bucket",
  "sourceKey": "imports/spring-2026-catalog.pdf",
  "outputBucket": "catalog-output-bucket",
  "outputKey": "processed/spring-2026-catalog.pdf",
  "artifactBucket": "catalog-artifacts-bucket",
  "artifactPrefix": "runs/job-20260423-001/",
  "catalogLookup": {
    "baseUrl": "https://magento.example.com",
    "skuQueryMode": "exact-or-like"
  },
  "notificationGroup": "catalog-ops@example.com",
  "flipbookProfile": "default"
}
```

### Contract rules

- The worker must download the source PDF from `sourceBucket/sourceKey`.
- The worker must preserve the original filename in `outputKey`.
- The worker must treat missing product results as unmatched records, not as fatal job errors.

## 3. Worker Result Contract

- Purpose: Defines the result returned after PDF processing completes.
- Producer: Worker entrypoint.
- Consumer: Workflow orchestrator.

### Required fields

```json
{
  "jobId": "job-20260423-001",
  "status": "processed",
  "workerRunId": "58f48d87ca3b",
  "outputBucket": "catalog-output-bucket",
  "outputKey": "processed/spring-2026-catalog.pdf",
  "pageCount": 96,
  "matchedSkuCount": 148,
  "unmatchedSkuCount": 7,
  "linkCount": 296,
  "artifactPrefix": "runs/job-20260423-001/"
}
```

### Contract rules

- `status` must be `processed` or `failed`.
- `outputBucket` and `outputKey` are required when `status = processed`.
- `artifactPrefix` must point to persisted diagnostic artifacts for troubleshooting.

## 4. Flipbook Publication Contract

- Purpose: Defines the business payload needed to publish the linked PDF.
- Producer: Workflow orchestrator.
- Consumer: Flipbook integration client.

### Required request fields

```json
{
  "jobId": "job-20260423-001",
  "pdfBucket": "catalog-output-bucket",
  "pdfKey": "processed/spring-2026-catalog.pdf",
  "filename": "spring-2026-catalog.pdf"
}
```

### Required response fields

```json
{
  "jobId": "job-20260423-001",
  "publicationStatus": "published",
  "flipbookUrl": "https://flipbook.example.com/books/12345"
}
```

### Contract rules

- Publication failures must include an error message that can be surfaced in job state and notifications.
- A successful publication must return a non-empty `flipbookUrl`.

## 5. Notification Contract

- Purpose: Defines the payload for stakeholder outcome notifications.
- Producer: Workflow orchestrator.
- Consumer: Notification client.

### Required fields

```json
{
  "jobId": "job-20260423-001",
  "notificationType": "success",
  "recipientGroup": "catalog-ops@example.com",
  "filename": "spring-2026-catalog.pdf",
  "finalStatus": "completed",
  "flipbookUrl": "https://flipbook.example.com/books/12345",
  "failureStage": null,
  "failureMessage": null
}
```

### Contract rules

- Success notifications must include `filename`, `finalStatus`, and `flipbookUrl`.
- Failure notifications must include `filename`, `finalStatus`, `failureStage`, and `failureMessage`.
- Partial-success notifications must identify the completed artifacts that remain available.