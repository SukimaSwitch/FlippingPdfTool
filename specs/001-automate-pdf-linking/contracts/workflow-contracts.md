# Workflow Contracts: Automated PDF Link Publishing

## 1. Ingest Event Contract

- Purpose: Minimum source event data required to start a processing job.
- Producer: S3 object-created trigger.
- Consumer: Workflow starter.

### Required fields

```json
{
  "bucket": "cmg-catalog-book",
  "key": "input/currentcatalog/spring-2026-catalog.pdf",
  "sizeBytes": 73400320,
  "etag": "abc123",
  "eventTime": "2026-04-23T18:30:00Z"
}
```

### Contract rules

- `key` must reference a PDF object under `input/<site-prefix>/`.
- `sizeBytes` is captured for job diagnostics and capacity planning.
- Duplicate events for the same object version must resolve to one logical Processing Job.

## 2. Site Routing Contract

- Purpose: Normalize the upload path into an approved site configuration before the worker runs.
- Producer: Workflow starter or dedicated routing step.
- Consumer: Step Functions workflow state and worker-input builder.

### Accepted routing result

```json
{
  "jobId": "job-20260423-001",
  "routingStatus": "accepted",
  "siteConfiguration": {
    "sitePrefix": "currentcatalog",
    "publicDomain": "https://www.currentcatalog.com",
    "magentoStoreCode": "currentcatalog",
    "outputBucket": "cmg-catalog-book",
    "outputKey": "output/currentcatalog/spring-2026-catalog.pdf"
  }
}
```

### Rejected routing result

```json
{
  "jobId": "job-20260423-001",
  "routingStatus": "rejected",
  "failureStage": "ingest-routing",
  "failureCode": "unknown-prefix",
  "failureMessage": "Unsupported site prefix 'unknown' in key input/unknown/spring-2026-catalog.pdf"
}
```

### Contract rules

- Supported prefixes are only `currentcatalog`, `colorfulimages`, and `lillianvernon`.
- The routing step must derive both the public domain and the Magento store code from the prefix.
- Rejected routing results must terminate the job before PDF processing starts.

## 3. Worker Input Contract

- Purpose: Defines the payload used to run the containerized PDF processor.
- Producer: Workflow orchestrator.
- Consumer: Worker entrypoint.

### Required fields

```json
{
  "jobId": "job-20260423-001",
  "sourceBucket": "cmg-catalog-book",
  "sourceKey": "input/currentcatalog/spring-2026-catalog.pdf",
  "outputBucket": "cmg-catalog-book",
  "outputKey": "output/currentcatalog/spring-2026-catalog.pdf",
  "artifactBucket": "cmg-catalog-book",
  "artifactPrefix": "artifacts/job-20260423-001/",
  "siteConfiguration": {
    "sitePrefix": "currentcatalog",
    "publicDomain": "https://www.currentcatalog.com",
    "magentoStoreCode": "currentcatalog",
    "magentoProductLookupRoute": "/rest/currentcatalog/V1/products?searchCriteria[filterGroups][0][filters][0][field]=sku&searchCriteria[filterGroups][0][filters][0][value]={sku}&searchCriteria[filterGroups][0][filters][0][conditionType]=like"
  },
  "notificationGroup": "catalog-ops@example.com",
  "flipbookProfile": "default"
}
```

### Contract rules

- The worker must download the source PDF from `sourceBucket/sourceKey`.
- The worker must preserve the original filename in `outputKey` and keep the site-matching output prefix.
- The worker must use `siteConfiguration.magentoStoreCode` when building Magento requests.
- The worker must treat missing product results as unmatched records, not as fatal job errors.

## 4. Worker Result Contract

- Purpose: Defines the result returned after PDF processing completes.
- Producer: Worker entrypoint.
- Consumer: Workflow orchestrator.

### Required fields

```json
{
  "jobId": "job-20260423-001",
  "status": "processed",
  "workerRunId": "58f48d87ca3b",
  "sitePrefix": "currentcatalog",
  "outputBucket": "cmg-catalog-book",
  "outputKey": "output/currentcatalog/spring-2026-catalog.pdf",
  "pageCount": 96,
  "matchedSkuCount": 148,
  "unmatchedSkuCount": 7,
  "linkCount": 296,
  "artifactPrefix": "artifacts/job-20260423-001/"
}
```

### Contract rules

- `status` must be `processed` or `failed`.
- `outputBucket` and `outputKey` are required when `status = processed`.
- `sitePrefix` must match the accepted routing decision.
- `artifactPrefix` must point to persisted diagnostic artifacts for troubleshooting.

## 5. Flipbook Publication Contract

- Purpose: Defines the business payload needed to publish the linked PDF.
- Producer: Workflow orchestrator.
- Consumer: Flipbook integration client.

### Required request fields

```json
{
  "jobId": "job-20260423-001",
  "sitePrefix": "currentcatalog",
  "pdfBucket": "cmg-catalog-book",
  "pdfKey": "output/currentcatalog/spring-2026-catalog.pdf",
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

## 6. Notification Contract

- Purpose: Defines the payload for stakeholder outcome notifications.
- Producer: Workflow orchestrator.
- Consumer: Notification client.

### Required fields

```json
{
  "jobId": "job-20260423-001",
  "notificationType": "success",
  "recipientGroup": "catalog-ops@example.com",
  "sitePrefix": "currentcatalog",
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
- Failure notifications for rejected prefixes must report `failureStage = ingest-routing`.
- Partial-success notifications must identify the completed artifacts that remain available.