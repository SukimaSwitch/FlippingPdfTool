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
  "eventTime": "2026-04-28T18:30:00Z"
}
```

### Ingest rules

- `key` must reference a PDF object under `input/<site-prefix>/`.
- `sizeBytes` is captured for diagnostics and capacity planning.
- Duplicate events for the same object version must resolve to one logical `Processing Job`.

## 2. Site Routing Contract

- Purpose: Normalize the upload path into an approved site configuration before the worker runs.
- Producer: Workflow starter or dedicated routing step.
- Consumer: Step Functions state and worker-input builder.

### Accepted routing result

```json
{
  "jobId": "job-20260428-001",
  "routingStatus": "accepted",
  "siteConfiguration": {
    "sitePrefix": "currentcatalog",
    "publicDomain": "https://www.currentcatalog.com",
    "magentoStoreCode": "currentcatalog",
    "productUrlTemplate": "https://www.currentcatalog.com/buy/{url_key}.html",
    "outputBucket": "cmg-catalog-book",
    "outputKey": "output/currentcatalog/spring-2026-catalog.pdf"
  }
}
```

### Rejected routing result

```json
{
  "jobId": "job-20260428-001",
  "routingStatus": "rejected",
  "failureStage": "ingest-routing",
  "failureCode": "unknown-prefix",
  "failureMessage": "Unsupported site prefix 'unknown' in key input/unknown/spring-2026-catalog.pdf"
}
```

### Routing rules

- Supported prefixes are only `currentcatalog`, `colorfulimages`, and `lillianvernon`.
- The physical S3 bucket remains `cmg-catalog-book`; site routing is expressed only through the `input/<site-prefix>/...` and `output/<site-prefix>/...` keys.
- Routing must derive both the public domain and the Magento store code from the prefix.
- Rejected routing results must terminate the job before PDF processing starts.

## 3. Worker Input Contract

- Purpose: Defines the payload used to run the containerized PDF processor.
- Producer: Workflow orchestrator.
- Consumer: Worker entrypoint.

### Worker input payload

```json
{
  "jobId": "job-20260428-001",
  "sourceBucket": "cmg-catalog-book",
  "sourceKey": "input/currentcatalog/spring-2026-catalog.pdf",
  "outputBucket": "cmg-catalog-book",
  "outputKey": "output/currentcatalog/spring-2026-catalog.pdf",
  "artifactBucket": "cmg-catalog-book",
  "artifactPrefix": "artifacts/job-20260428-001/",
  "siteConfiguration": {
    "sitePrefix": "currentcatalog",
    "publicDomain": "https://www.currentcatalog.com",
    "magentoStoreCode": "currentcatalog",
    "magentoProductLookupRoute": "/rest/currentcatalog/V1/products?searchCriteria[filterGroups][0][filters][0][field]=sku&searchCriteria[filterGroups][0][filters][0][value]={sku}&searchCriteria[filterGroups][0][filters][0][conditionType]=like",
    "productUrlTemplate": "https://www.currentcatalog.com/buy/{url_key}.html"
  },
  "notificationGroup": "catalog-ops@example.com",
  "triggeredAt": "2026-04-28T18:30:00Z"
}
```

### Worker input rules

- The worker downloads the source PDF from `sourceBucket/sourceKey`.
- The worker preserves the original filename in `outputKey` and keeps the site-matching output prefix.
- The worker uses `siteConfiguration.magentoStoreCode` when building Magento requests.
- The worker uses `siteConfiguration.productUrlTemplate` to convert Magento `url_key` values into the storefront-specific product URL shape.
- The worker persists page-level diagnostic artifacts under `artifactPrefix`.

## 4. Magento Resolution Contract

- Purpose: Define the exact semantics used to turn a detected catalog SKU into a customer-facing product URL.
- Producer: Magento catalog client.
- Consumer: PDF-linking pipeline.

### Search request shape

```text
GET /rest/<store_code>/V1/products?searchCriteria[filterGroups][0][filters][0][field]=sku&searchCriteria[filterGroups][0][filters][0][value]=<SKU>&searchCriteria[filterGroups][0][filters][0][conditionType]=like
```

### Linkable match example

```json
{
  "detectedSku": "123456",
  "publicDomain": "https://www.currentcatalog.com",
  "items": [
    {
      "sku": "123456",
      "custom_attributes": [
        {
          "attribute_code": "url_key",
          "value": "spring-floral-mug"
        }
      ]
    }
  ],
  "resolvedUrl": "https://www.currentcatalog.com/spring-floral-mug.html"
}
```

### Unresolved exact-match example

```json
{
  "detectedSku": "123456",
  "publicDomain": "https://www.currentcatalog.com",
  "items": [
    {
      "sku": "123456",
      "custom_attributes": []
    }
  ],
  "resolvedUrl": null,
  "unresolvedReason": "missing_url_key"
}
```

### Magento resolution rules

- Search requests must use the routed store code in the Magento path.
- Search responses may include partial or fuzzy candidates because the request uses `conditionType=like`.
- A product is linkable only when one returned item's `sku` exactly equals the detected catalog SKU.
- Final customer URLs must be built as `https://<domain>/<url_key>.html`.
- If no exact SKU exists, the candidate remains unmatched and unlinked.
- If an exact SKU exists but `url_key` is missing, the candidate remains unlinked and must be recorded as an unresolved match.
- Unmatched candidates and unresolved exact matches must remain non-fatal for the overall PDF job unless a separate worker-stage error occurs.

## 5. Worker Result Contract

- Purpose: Defines the result returned after PDF processing completes.
- Producer: Worker entrypoint.
- Consumer: Workflow orchestrator.

### Successful result example

```json
{
  "jobId": "job-20260428-001",
  "status": "processed",
  "workerRunId": "58f48d87ca3b",
  "sitePrefix": "currentcatalog",
  "outputBucket": "cmg-catalog-book",
  "outputKey": "output/currentcatalog/spring-2026-catalog.pdf",
  "pageCount": 96,
  "matchedSkuCount": 148,
  "unmatchedSkuCount": 7,
  "unresolvedMatchCount": 2,
  "linkCount": 296,
  "artifactPrefix": "artifacts/job-20260428-001/"
}
```

### Failed result example

```json
{
  "jobId": "job-20260428-001",
  "status": "failed",
  "workerRunId": "58f48d87ca3b",
  "sitePrefix": "currentcatalog",
  "artifactPrefix": "artifacts/job-20260428-001/",
  "failureStage": "processing",
  "failureCode": "invalid-pdf",
  "failureMessage": "PDF could not be opened for page processing."
}
```

### Worker result rules

- `status` must be `processed` or `failed`.
- `outputBucket` and `outputKey` are required when `status = processed` and must use the physical bucket `cmg-catalog-book` with an `output/<site-prefix>/...` key.
- `matchedSkuCount`, `unmatchedSkuCount`, `unresolvedMatchCount`, and `linkCount` summarize the worker's PDF-processing outcome.
- Persisted page-level summaries under `artifactPrefix` must preserve both unmatched SKU lists and unresolved exact-match details so operators can triage missing links without rerunning the job blindly.
- `failureStage` and `failureMessage` are required when `status = failed`.
- `sitePrefix` must match the accepted routing decision.
- `artifactPrefix` must point to persisted diagnostic artifacts.
- Worker results cover only the PDF-processing slice. Publication and notification outcomes are handled by later workflow steps.

## 6. Flipbook Publication Contract

- Purpose: Defines the payload needed to publish the linked PDF.
- Producer: Workflow orchestrator.
- Consumer: Flipbook integration client.

### Required request fields

```json
{
  "jobId": "job-20260428-001",
  "sitePrefix": "currentcatalog",
  "pdfBucket": "cmg-catalog-book",
  "pdfKey": "output/currentcatalog/spring-2026-catalog.pdf",
  "filename": "spring-2026-catalog.pdf"
}
```

### Required response fields

```json
{
  "jobId": "job-20260428-001",
  "publicationStatus": "published",
  "flipbookUrl": "https://flipbook.example.com/books/12345"
}
```

### Publication rules

- Publication failures must include an error message that can be surfaced in job state and notifications.
- A successful publication must return a non-empty `flipbookUrl`.

## 7. Notification Contract

- Purpose: Defines the payload for stakeholder outcome notifications.
- Producer: Workflow orchestrator.
- Consumer: Notification client.

### Success notification example

```json
{
  "jobId": "job-20260428-001",
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

### Failure notification rules

- Success notifications must include `filename`, `finalStatus`, and `flipbookUrl`.
- Failure notifications must include `filename`, `finalStatus`, `failureStage`, and `failureMessage`.
- Failure notifications for rejected prefixes must report `failureStage = ingest-routing`.
- Partial-success notifications must identify preserved artifacts that remain available even though a downstream stage failed.
