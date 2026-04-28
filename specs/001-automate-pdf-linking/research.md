# Phase 0 Research: Automated PDF Link Publishing

## Decision 1: Use Step Functions to orchestrate a long-running ECS/Fargate worker

**Decision**: Start the workflow from an S3 object-created event and hand the PDF-processing step to an ECS/Fargate worker coordinated by AWS Step Functions.

**Rationale**: The existing pipeline is CPU- and OCR-heavy, runs page by page, and must support PDFs larger than 70 MB and 80+ pages. Step Functions gives explicit stage transitions and retry control, while Fargate runs the current Python stack without Lambda-style runtime pressure.

**Alternatives considered**:

- Run the full job inside a single Lambda: rejected because large PDFs and OCR-heavy runs are poor fits for short-lived serverless execution.
- Build custom queue and worker coordination from scratch: rejected because it moves workflow-state and retry logic into application code.
- Rewrite immediately into page-level distributed workers: rejected because it increases complexity before the worker contract is stable.

## Decision 2: Derive routing from the S3 key and reject unsupported prefixes before processing

**Decision**: Treat `input/<site-prefix>/...` under the physical bucket `cmg-catalog-book` as the source of truth for routing, and support only `currentcatalog`, `colorfulimages`, and `lillianvernon`.

**Rationale**: The clarified spec requires routing, output placement, product domain selection, and Magento store selection to come from the uploaded object's prefix. Failing unsupported prefixes during ingest avoids wasted compute and eliminates cross-site link risk.

**Alternatives considered**:

- Infer the site from filename or PDF content: rejected because it is brittle and hard to validate.
- Pass the site independently of the object key: rejected because it duplicates the routing source of truth.
- Default unknown prefixes to one storefront: rejected because it can silently generate incorrect links.

## Decision 3: Keep the existing PDF-linking pipeline as the domain core

**Decision**: Reuse the current `src/main.py` page-by-page linking pipeline and place orchestration, storage, routing, publication, and notification behavior around it.

**Rationale**: The current CLI already performs rendering, OCR/Textract analysis, SKU extraction, figure/description matching, and PDF link insertion. Reusing that core reduces regression risk and keeps local validation aligned with worker execution.

**Alternatives considered**:

- Rewrite the linking pipeline specifically for cloud execution: rejected because it duplicates proven domain logic.
- Leave all worker logic inside `src/main.py`: rejected because it couples orchestration concerns to document-processing logic.

## Decision 4: Model storage as one S3 bucket with logical input/output/artifact prefixes plus DynamoDB job state

**Decision**: Use `cmg-catalog-book` as the physical bucket, keep `input/`, `output/`, and artifact prefixes as logical object-key namespaces, and persist durable workflow/job state in DynamoDB.

**Rationale**: The specification names logical input/output locations, but S3 implements that as prefixes inside one bucket. DynamoDB provides durable, queryable job-stage visibility that survives beyond worker runtime and supports partial-failure reporting.

**Alternatives considered**:

- Use S3 objects alone to infer job status: rejected because it is weak for stage tracking and failure reporting.
- Keep all state only in Step Functions execution history: rejected because operations need durable business-level job records.
- Split the design into separate site-specific buckets: rejected because the spec defines shared input and output locations with site-specific prefixes.

## Decision 5: Resolve Magento product URLs with store-code-specific search plus exact-match validation

**Decision**: Query Magento through `GET /rest/<store_code>/V1/products?...conditionType=like`, filter the response down to an exact SKU match, read `url_key` from that matched product's `custom_attributes`, and build the final URL as `https://<domain>/<url_key>.html`.

**Rationale**: The clarified spec explicitly requires store-specific Magento routing, exact SKU validation after the search response, and URL assembly from `url_key` rather than from SKU. This keeps link generation consistent with Magento's canonical storefront URLs.

**Alternatives considered**:

- Use the first Magento search result regardless of exact SKU equality: rejected because Magento search can return partial or fuzzy matches.
- Build URLs directly from SKU: rejected because the clarified requirement makes `url_key` the canonical slug source.
- Use one default store code for all sites: rejected because it violates site-specific catalog routing.

## Decision 6: Record unresolved exact matches separately from ordinary unmatched SKUs

**Decision**: Distinguish between ordinary unmatched SKU detections and unresolved exact Magento matches that lack `url_key`, leaving both unlinked but recording the latter as a specific triage outcome.

**Rationale**: The spec treats "no exact Magento match" and "exact match without `url_key`" differently. The first is a normal unmatched outcome; the second is a data-quality issue that operations should be able to identify and follow up on.

**Alternatives considered**:

- Treat missing `url_key` as a fatal job error: rejected because the spec explicitly says the job should continue.
- Collapse missing `url_key` into the same metric as "no match": rejected because it hides a distinct catalog-data defect.

## Decision 7: Define worker payloads as JSON schemas and keep publication/notification as downstream contracts

**Decision**: Use JSON schemas for worker input and worker result payloads, and document the surrounding routing, Magento resolution, publication, and notification contracts in markdown.

**Rationale**: The critical interface for this feature is the orchestration payload boundary rather than a public HTTP API. JSON schemas provide machine-validatable worker contracts, while markdown captures the surrounding stage-specific business semantics.

**Alternatives considered**:

- Markdown examples only: rejected because examples are not sufficient for automated validation.
- OpenAPI for the whole workflow: rejected because the feature does not expose an HTTP API boundary.
