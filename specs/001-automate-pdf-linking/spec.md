# Feature Specification: Automated PDF Link Publishing

**Feature Branch**: `[001-automate-pdf-linking]`  
**Created**: 2026-04-23  
**Status**: Draft  
**Input**: User description: "Automate the workflow that turns an uploaded catalog PDF into a linked output PDF, publishes it as a flipbook, notifies stakeholders, and records job outcomes."

## Clarifications

### Session 2026-04-23

- Q: How should the workflow handle PDFs uploaded outside the known site-specific S3 prefixes? -> A: Reject them during ingest/routing and mark the job failed.

### Session 2026-04-28

- Q: How should the URL builder derive the final product page URL from the Magento product response? -> A: Search products through the Magento API, read the `url_key` value from `custom_attributes`, and build the product URL as `https://<domain>/<url_key>.html`.
- Q: How should Magento SKU search results be matched when multiple or partial candidates are returned? -> A: Use only an exact SKU match after the Magento search; if no exact match exists, leave the item unlinked.
- Q: How should the workflow handle an exact-match Magento product that does not include a `url_key` attribute? -> A: Leave the item unlinked and record it as an unresolved product match.
- Q: How should the worker authenticate to Magento before product lookup requests? -> A: If a preissued bearer token is not supplied, exchange the configured Magento username and password through `POST /rest/V1/integration/admin/token`, then reuse that bearer token for subsequent product search requests.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Produce a linked catalog automatically (Priority: P1)

As a catalog operations manager, I want an uploaded catalog PDF to be processed automatically so that every product image and matching product description links to the correct product page without manual editing.

**Why this priority**: This is the core business outcome. If the system does not reliably turn uploaded catalogs into linked PDFs, the rest of the workflow has no value.

**Independent Test**: Upload a valid catalog PDF containing recognizable product SKUs and verify that the resulting output PDF is written to the configured output location with clickable links on matched product images and descriptions.

**Acceptance Scenarios**:

1. **Given** a valid catalog PDF is placed in the configured import location, **When** processing starts, **Then** the system creates one processing job for that file and processes the PDF page by page.
2. **Given** a page contains a product image and description with a recognizable SKU, **When** the page is processed, **Then** the system adds a hyperlink for the resolved product page to both the product image region and the associated description text in the output PDF.
3. **Given** a SKU is detected but no product is returned by the catalog lookup, **When** the page is processed, **Then** the system leaves the related image and text unchanged and does not add a hyperlink for that product candidate.
4. **Given** processing completes successfully, **When** the output is written, **Then** the processed PDF is stored in the configured output location using the same filename as the source file.

---

### User Story 2 - Publish the linked catalog and notify stakeholders (Priority: P2)

As a marketing stakeholder, I want the finished linked PDF to be published as an online flipbook and shared automatically so that the team can review or distribute the finished catalog immediately.

**Why this priority**: Publishing and notification turn the processed file into a usable business deliverable and remove manual follow-up work after processing.

**Independent Test**: Complete a successful processing run and verify that an online flipbook is generated from the processed PDF and that the configured email group receives the flipbook URL together with the job outcome.

**Acceptance Scenarios**:

1. **Given** a processed PDF is available, **When** publication is requested, **Then** the system submits that processed PDF to the configured flipbook service and captures the resulting publication URL.
2. **Given** the flipbook is created successfully, **When** the job finishes, **Then** the configured email group receives a success notification that includes the source filename, processing result, and flipbook URL.

---

### User Story 3 - Diagnose failures quickly (Priority: P3)

As a support or operations user, I want failures and partial results to be recorded clearly so that I can identify where processing stopped and what needs attention without re-running blind.

**Why this priority**: The workflow touches several external systems and long-running document work. Clear visibility reduces recovery time and operational risk.

**Independent Test**: Trigger representative failures such as an unreadable PDF, missing product matches, publication failure, or notification failure, and verify that the job records a clear outcome and sends an error notification with useful details.

**Acceptance Scenarios**:

1. **Given** processing fails before the output PDF is produced, **When** the job ends, **Then** the system records the failure reason and sends a failure notification containing the file name and error details.
2. **Given** PDF processing succeeds but a later publication or notification step fails, **When** the workflow completes, **Then** the system records which stage failed and preserves the successfully produced artifacts created before that failure.

### Edge Cases

- A source file is not a valid PDF or cannot be opened for page-by-page processing.
- A source file is uploaded outside the supported site prefixes and therefore cannot be routed to a valid domain or Magento store code.
- A page contains text or images but no SKU that can be matched to a product URL.
- A SKU is detected but no product URL is returned from the product catalog service, so the related image and description must remain unlinked.
- A Magento lookup returns partial or multiple non-exact SKU candidates, and the system must ignore those candidates unless one product SKU exactly matches the detected catalog SKU.
- A Magento product exactly matches the detected SKU but does not provide a `url_key`, so the related image and description must remain unlinked and the unresolved match must be recorded for triage.
- The same SKU appears multiple times on a page and each matching image-description pair must receive the correct link.
- The processed PDF is created successfully, but the flipbook service rejects the upload or does not return a publication URL.
- The workflow completes or fails, but the notification email cannot be delivered.
- A duplicate upload uses the same filename as an earlier job and must not make the final job status ambiguous.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST detect when a PDF file is added to the configured import location and start a single processing job for that file.
- **FR-001a**: The configured import location MUST be the `cmg-catalog-book/input` bucket with site-specific prefixes selected manually at upload time: `currentcatalog/`, `colorfulimages/`, and `lillianvernon/`.
- **FR-002**: The system MUST retrieve the uploaded PDF from storage and process it using the existing page-by-page catalog-linking workflow as the baseline business logic.
- **FR-002a**: The system MUST derive the site configuration from the source object's S3 prefix and use that configuration for output routing, product URL domain selection, and Magento store-code selection.
- **FR-003**: The system MUST process the PDF one page at a time and evaluate every page for product figures and related descriptive text.
- **FR-004**: The system MUST derive candidate product identifiers from page content and use the detected SKU value to search the configured product catalog source for a destination product URL.
- **FR-004a**: The site configuration mappings MUST be: `currentcatalog/` -> domain `https://www.currentcatalog.com`, store code `currentcatalog`; `colorfulimages/` -> domain `https://www.colorfulimages.com`, store code `colorfulimages`; `lillianvernon/` -> domain `https://www.lillianvernon.com`, store code `lillianvernon`.
- **FR-004aa**: Before issuing Magento product search requests, the system MUST authenticate with Magento using one of these methods: a preissued bearer token from configuration, or an admin-token exchange through `POST /rest/V1/integration/admin/token` using the configured Magento username and password.
- **FR-004ab**: When username/password authentication is used, the admin-token exchange request MUST send XML login payload data and reuse the returned bearer token for subsequent product search requests within the same worker execution.
- **FR-004b**: Product lookup requests to Magento MUST use the site-specific store code in the route `GET /rest/<store_code>/V1/products?searchCriteria[filterGroups][0][filters][0][field]=sku&searchCriteria[filterGroups][0][filters][0][value]=<SKU>&searchCriteria[filterGroups][0][filters][0][conditionType]=like`.
- **FR-004c**: When Magento returns a matching product, the system MUST inspect the product `custom_attributes` array, find the `url_key` attribute, and treat its `value` as the canonical page slug for link generation.
- **FR-004d**: The final product URL MUST be constructed as `https://<domain>/<url_key>.html`, where `<domain>` comes from the site configuration mapping and `<url_key>` comes from the Magento product response.
- **FR-004e**: The system MUST add a product link only when the Magento response contains at least one product whose SKU exactly matches the detected catalog SKU; partial or fuzzy matches MUST be ignored.
- **FR-004f**: If an exact SKU match is found but the matching Magento product does not contain a `url_key` attribute, the system MUST leave the related image and description unlinked and record the product candidate as an unresolved match.
- **FR-005**: The system MUST add hyperlinks to the output PDF for each matched product image and its corresponding product description when a product URL is resolved.
- **FR-006**: The system MUST leave image and text regions unchanged when no product URL can be resolved for a detected SKU.
- **FR-007**: The system MUST preserve pages that have no valid product match without corrupting the remainder of the output PDF.
- **FR-008**: The system MUST support background processing for large uploaded PDFs so the job can continue to completion without requiring the upload event itself to remain active for the full processing duration.
- **FR-009**: The system MUST write the processed PDF to the configured output location using the same filename as the source PDF.
- **FR-009a**: The configured output location MUST be the `cmg-catalog-book/output` bucket, and processed PDFs MUST be written to the site-matching prefix that corresponds to the input prefix.
- **FR-010**: The system MUST submit the processed PDF to the configured flipbook publishing service after the output PDF is created.
- **FR-011**: The system MUST capture the resulting flipbook URL when publication succeeds and associate it with the processing job result.
- **FR-012**: The system MUST send a success notification to the configured email group after a fully successful run, including at minimum the source filename, overall processing result, and flipbook URL.
- **FR-013**: The system MUST send a failure notification to the configured email group whenever any stage of the workflow fails, including at minimum the source filename, failed stage, and error details sufficient for triage.
- **FR-014**: The system MUST log major workflow stages, page-level progress, external service call outcomes, and error conditions for each processing job.
- **FR-015**: The system MUST retain enough job metadata to distinguish source file ingestion, PDF processing, output storage, publication, notification, and final job status.
- **FR-016**: The system MUST ensure that failure in a downstream step does not erase or invalidate artifacts that were already created successfully earlier in the same job.
- **FR-017**: The system MUST reject any uploaded PDF whose source key does not match one of the supported site prefixes and mark the job as failed during ingest/routing before PDF processing begins.

### Key Entities *(include if feature involves data)*

- **Source PDF**: An uploaded catalog document identified by filename, storage location, upload time, and processing eligibility.
- **Site Configuration**: The routing metadata derived from the source S3 prefix, including input prefix, output prefix, product URL domain, and Magento store code.
- **Processing Job**: The end-to-end workflow instance for one uploaded PDF, including lifecycle state, timestamps, stage outcomes, and references to generated artifacts.
- **Page Result**: The per-page record of extracted content, identified products, matched link targets, unresolved product candidates, and page-level success or failure notes.
- **Product Match**: The association between a detected product identifier, its resolved product URL, the image region to link, and the description region to link.
- **Unresolved Product Match**: A detected SKU or exact Magento product candidate that could not be converted into a final product URL because a required field such as `url_key` was missing.
- **Magento Product Response**: The product lookup payload that includes product identity fields and a `custom_attributes` collection from which the `url_key` value is extracted.
- **Published Output**: The finished linked PDF and any resulting online publication URL associated with a completed processing job.
- **Notification Record**: The delivery payload and outcome for stakeholder notifications sent for success or failure states.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For successful jobs, 100% of processed PDFs that are published produce a usable flipbook URL included in the stakeholder notification.
- **SC-002**: 100% of failed jobs generate a notification and a recorded failure reason identifying the stage where the workflow stopped.
- **SC-003**: 100% of successful job notifications include the source filename, final job result, and the published flipbook URL.
- **SC-004**: The workflow successfully accepts and completes processing for uploaded catalog PDFs larger than 70 MB and exceeding 80 pages when the input file is otherwise valid.
- **SC-005**: The workflow does not fail solely because processing exceeds a predefined execution-time limit; long-running jobs remain eligible to continue until they complete or encounter a functional error.

## Assumptions

- The import and output locations are preconfigured and accessible to the automation workflow.
- Operators manually upload each PDF into the site-appropriate prefix under `cmg-catalog-book/input`.
- Only the supported site prefixes `currentcatalog/`, `colorfulimages/`, and `lillianvernon/` are in scope for automated processing.
- The existing catalog-linking logic remains the authoritative basis for page rendering, content extraction, SKU detection, and link placement behavior.
- Uploaded files in scope are catalog PDFs only; non-PDF assets are out of scope for this feature.
- The product catalog source supports SKU-based search and returns product URL information when a matching product exists.
- Magento authentication credentials are available either as a reusable bearer token or as a username/password pair that is authorized to mint an admin access token.
- Magento SKU search may return partial matches, so link generation relies on validating an exact SKU match in the response before using any returned product data.
- For in-scope Magento responses, the canonical product page slug is supplied as the `url_key` entry inside `custom_attributes`, and the final customer-facing URL is derived by combining that slug with the site-specific domain and the `.html` suffix.
- If an exact-match Magento product omits `url_key`, the workflow records that condition for follow-up and does not fail the full PDF job solely because of that missing field.
- Catalog PDFs in scope may exceed 70 MB and 80 pages, and long-running processing is acceptable for valid jobs.
- The configured email group, publication account, and service credentials are available before processing begins.
- This feature covers automated processing of one uploaded PDF per job and does not include a manual review or correction interface.
