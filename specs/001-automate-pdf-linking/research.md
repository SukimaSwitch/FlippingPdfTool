# Phase 0 Research: Automated PDF Link Publishing

## Decision 1: Route jobs by S3 prefix using a fixed site configuration table

**Decision**: Use the source object key prefix under `cmg-catalog-book/input` as the single source of truth for storefront routing. Support only `currentcatalog/`, `colorfulimages/`, and `lillianvernon/`, each mapped to its output prefix, product URL domain, and Magento store code.

**Rationale**: The spec states operators will upload PDFs manually into the correct site-specific S3 prefix. Using the prefix avoids unreliable filename parsing, keeps routing deterministic, and gives one consistent place to derive domain and Magento store selection.

**Alternatives considered**:
- Inspecting filenames or PDF content to guess the site: rejected because it is brittle and hard to validate.
- Passing the site separately in every event payload: rejected because it duplicates information already encoded by the storage layout.
- Defaulting unknown prefixes to one storefront: rejected because it can silently generate incorrect product links.

## Decision 2: Run the long-lived PDF processing step in a containerized worker, orchestrated outside the upload event path

**Decision**: Keep the upload event lightweight and hand off processing to an asynchronous container worker, coordinated by an orchestration layer that can track stages and continue beyond short event execution limits.

**Rationale**: The current pipeline is CPU- and I/O-heavy, already supports page-by-page progress, and must handle PDFs larger than 70 MB with more than 80 pages. A dedicated worker avoids tying success to event-runtime limits and matches the feature's requirement for long-running jobs.

**Alternatives considered**:
- Running the full pipeline directly inside the upload-triggered function: rejected because large PDFs exceed safe event-driven execution windows.
- Rewriting the pipeline as multiple fine-grained page-level functions immediately: rejected because it adds coordination complexity before the core worker contract is established.
- Manual batch execution only: rejected because it does not satisfy automated processing requirements.

## Decision 3: Preserve the existing `src/main.py` pipeline by extracting reusable services rather than replacing it

**Decision**: Keep `src/main.py` as the baseline CLI and extract reusable pipeline logic into service modules that both the CLI and worker can call.

**Rationale**: The current CLI already encapsulates the authoritative linking behavior, has working unit tests, and supports resumable page-level processing. Reusing that behavior reduces regression risk and keeps local debugging aligned with production behavior.

**Alternatives considered**:
- Building a separate worker-only implementation: rejected because it would duplicate business logic and increase drift risk.
- Leaving all logic in `src/main.py` and importing it directly everywhere: rejected because orchestration, storage, and publication concerns need clearer seams for testing.

## Decision 4: Store job state separately from generated PDF artifacts

**Decision**: Persist processing-job state, stage outcomes, and failure details in a dedicated job store while keeping linked PDFs and per-page diagnostics in S3.

**Rationale**: The spec requires explicit job-stage visibility, failure-stage recording, and preservation of artifacts created before downstream failures. A metadata store supports reliable status transitions without overloading object storage as the only state system.

**Alternatives considered**:
- Using only S3 objects and filenames to infer job status: rejected because it is awkward for partial failure tracking and notification retry logic.
- Embedding all state in the orchestration engine only: rejected because operations and notifications need stable queryable job records.

## Decision 5: Define orchestration contracts as JSON schemas for worker input and worker result payloads

**Decision**: Document the worker handoff and completion payloads as JSON schema files under `contracts/`.

**Rationale**: The system's external interface is not a public HTTP API; it is the payload boundary between ingestion/orchestration and the asynchronous worker. JSON schemas give a precise contract that can be validated in tests and consumed by multiple orchestrators or adapters.

**Alternatives considered**:
- Free-form markdown payload examples only: rejected because examples are insufficient for automated validation.
- Introducing OpenAPI for non-HTTP interactions: rejected because it adds ceremony without matching the actual interface shape.
# Research: Automated PDF Link Publishing

## Decision 1: Use Step Functions to orchestrate a Fargate worker for PDF processing

- Decision: Use S3 object-created events to start an AWS Step Functions state machine, and run the existing PDF-processing pipeline inside an ECS Fargate task.
- Rationale: The current pipeline is CPU and OCR heavy, processes pages sequentially, and is expected to handle large PDFs beyond practical Lambda execution limits. Step Functions provides workflow stage visibility, retry handling, and explicit control-flow transitions for processing, publication, and notification. Fargate runs the current Python stack inside a long-running Linux container without server management.
- Alternatives considered:
  - Single Lambda workflow: rejected because OCR-heavy PDFs and 80+ page inputs can exceed Lambda runtime and memory comfort.
  - SQS plus custom worker coordination: viable, but it pushes retry logic, status tracking, and stage transitions into application code instead of managed orchestration.
  - AWS Batch as the primary orchestrator: viable for larger-scale batch fleets, but heavier than necessary for a per-upload business workflow with several non-compute stages.

## Decision 2: Derive a strict Site Configuration at ingest and fail fast on unsupported prefixes

- Decision: Add an explicit ingest-routing step that inspects the uploaded key, accepts only `input/currentcatalog/`, `input/colorfulimages/`, and `input/lillianvernon/`, and derives a `Site Configuration` object containing the output prefix, customer-facing domain, and Magento store code. Any other prefix ends the job immediately as a failed ingest-routing outcome.
- Rationale: The latest spec makes the S3 prefix the source of truth for routing, output placement, and Magento store selection, and it requires unknown prefixes to be rejected before PDF processing starts. Centralizing that decision once at ingest avoids later ambiguity and prevents partially processed output for unsupported sites.
- Alternatives considered:
  - Pass site information manually to the worker: rejected because the spec requires routing to be derived from the uploaded object path.
  - Let the worker infer the site during processing: rejected because it delays validation and wastes compute on invalid uploads.
  - Default unknown prefixes to one site: rejected because it risks publishing links and notifications to the wrong destination.

## Decision 3: Preserve the current PDF pipeline as the domain core and add service adapters around it

- Decision: Keep the existing PDF parsing, OCR interpretation, SKU extraction, and link-placement logic as the domain core, and add orchestration, storage, lookup, publication, and notification adapters around it.
- Rationale: The repository already contains a functioning page-by-page CLI pipeline with tests around SKU extraction and persisted link annotations. Reusing that core reduces behavioral drift and limits the refactor surface to integration boundaries.
- Alternatives considered:
  - Rewrite the pipeline for cloud-only execution: rejected because it increases delivery risk without clear business benefit.
  - Embed all cloud logic directly into `src/main.py`: rejected because it would entangle orchestration with PDF-processing logic and make testing harder.

## Decision 4: Implement the spec's S3 locations as logical prefixes within the `cmg-catalog-book` bucket

- Decision: Represent the spec's `cmg-catalog-book/input` and `cmg-catalog-book/output` locations as the S3 bucket `cmg-catalog-book` with top-level prefixes `input/` and `output/`, preserving the site segment under each path.
- Rationale: Native S3 bucket names cannot contain slash-delimited path segments. Modeling the requirement as one bucket plus explicit prefixes keeps the storage layout implementable while preserving the business requirement that uploads land under the input location and outputs land under the matching site path in the output location.
- Alternatives considered:
  - Treat `cmg-catalog-book/input` and `cmg-catalog-book/output` as literal bucket names: rejected because S3 bucket naming does not support that structure.
  - Use separate buckets per site: rejected because the spec defines shared input and output locations with site-specific prefixes.

## Decision 5: Use S3 for documents and artifacts, and DynamoDB for durable job-state tracking

- Decision: Store source PDFs, linked PDFs, and optional diagnostic artifacts in S3, and persist processing-job stage/state metadata in DynamoDB.
- Rationale: The spec requires durable visibility into ingest, processing, publication, notification, and final job status. Step Functions execution history alone is useful for workflow debugging, but DynamoDB gives stable queryable job records, supports notification summaries, and decouples retained business status from orchestration retention windows.
- Alternatives considered:
  - Step Functions execution history only: rejected because it is less suitable for durable business-facing status lookup and artifact association.
  - Local container files only: rejected because worker-local artifacts disappear after task completion.

## Decision 6: Resolve product URLs through site-specific Magento store-code routes

- Decision: Build Magento lookup requests using the site-specific store-code path `GET /rest/<store_code>/V1/products?...` and then combine the returned product URL data with the site-specific public domain to form the final hyperlink.
- Rationale: The spec explicitly ties Magento lookup behavior to site configuration. Keeping store-code-aware lookup logic in a dedicated adapter prevents cross-site data leakage and guarantees that `currentcatalog`, `colorfulimages`, and `lillianvernon` each query the correct catalog view.
- Alternatives considered:
  - Use a single default Magento store code for every site: rejected because it breaks the clarified site-specific routing requirement.
  - Build product URLs from SKU only without catalog lookup: rejected because the spec requires lookup against the configured product catalog source.

## Decision 7: Integrate Magento, Flipbook, and notification delivery through dedicated clients with Secrets Manager credentials

- Decision: Implement separate integration clients for SKU-based Magento lookup, flipbook publication, and stakeholder notification, and source secrets from AWS Secrets Manager.
- Rationale: Each external system has distinct retry, error-reporting, and payload requirements. Dedicated clients make failures stage-specific, simplify unit tests, and keep secrets out of code and long-lived plain environment configuration.
- Alternatives considered:
  - Call all services inline from the worker without adapters: rejected because it hides stage boundaries and weakens testability.
  - Store credentials directly in code or unchecked environment files: rejected for operational and security reasons.

## Decision 8: Treat unmatched SKUs as non-failures, but treat unknown prefixes as ingest failures

- Decision: When SKU extraction succeeds but the product catalog lookup returns no product URL, record the unmatched result, leave the corresponding image and description unchanged, and continue processing the rest of the job. In contrast, when the source prefix is not one of the supported sites, fail the job immediately during ingest-routing and do not start PDF processing.
- Rationale: The feature explicitly allows unmatched products to remain unlinked while preserving output, but it also explicitly requires unsupported prefixes to be rejected early. Splitting these cases keeps business output flexible while maintaining hard routing safety.
- Alternatives considered:
  - Fail the entire job on the first unmatched SKU: rejected because it blocks delivery of valid links for the rest of the catalog.
  - Treat unknown prefixes as warnings and proceed: rejected because it violates the fail-fast routing requirement and risks misrouted output.

## Decision 9: Retain per-page processing artifacts behind configurable storage lifecycle rules

- Decision: Continue producing run-scoped artifacts such as per-page summaries and debug outputs, but store them in S3 with configurable lifecycle management.
- Rationale: The current CLI already emits per-page and run-level artifacts that help explain OCR and matching behavior. Preserving that model in cloud storage supports debugging while keeping long-term storage cost under control.
- Alternatives considered:
  - Disable all artifact retention: rejected because it removes the primary debugging surface for OCR and matching problems.
  - Retain artifacts indefinitely with no lifecycle control: rejected because storage costs will grow with each large catalog run.