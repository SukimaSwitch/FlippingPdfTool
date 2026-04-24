# Implementation Plan: Automated PDF Link Publishing

**Branch**: `[001-automate-pdf-linking]` | **Date**: 2026-04-23 | **Spec**: `/home/xzhang/project/FlippingPdfTool/specs/001-automate-pdf-linking/spec.md`
**Input**: Feature specification from `/home/xzhang/project/FlippingPdfTool/specs/001-automate-pdf-linking/spec.md`

## Summary

Automate the existing page-by-page PDF linking pipeline behind an asynchronous AWS-driven workflow that routes incoming PDFs by S3 prefix, resolves store-specific product URLs through Magento, stores linked outputs back to site-matched S3 prefixes, publishes the final PDF to the flipbook service, and sends success or failure notifications while preserving partial artifacts and explicit job state.

## Technical Context

**Language/Version**: Python 3.14 container runtime for worker and helper entrypoints; existing local pipeline remains Python-based  
**Primary Dependencies**: `boto3`, `requests`, `pymupdf`, `opencv-python`, `numpy`, `pillow`, Python `unittest`  
**Storage**: AWS S3 (`cmg-catalog-book/input`, `cmg-catalog-book/output`), local ephemeral worker filesystem for intermediate files, DynamoDB for processing-job metadata  
**Testing**: `unittest` via `/home/xzhang/project/FlippingPdfTool/.venv/bin/python -m unittest discover -s tests -v`, plus new contract and integration tests for orchestration adapters  
**Target Platform**: Linux-based container worker in AWS, triggered from S3-backed orchestration  
**Project Type**: Python CLI plus asynchronous worker/orchestration service  
**Performance Goals**: Accept valid PDFs larger than 70 MB and 80+ pages, avoid upload-event timeout coupling, preserve resumable page processing, emit terminal or structured job progress  
**Constraints**: Preserve existing `src/main.py` linking behavior, route strictly by supported S3 prefixes, reject unknown prefixes before processing, keep downstream failures from deleting generated artifacts, use site-specific Magento store codes and product domains  
**Scale/Scope**: One PDF per processing job, three supported storefronts (`currentcatalog`, `colorfulimages`, `lillianvernon`), page-level artifacts per run, asynchronous publication and notification stages

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

The repository constitution at `/home/xzhang/project/FlippingPdfTool/.specify/memory/constitution.md` still contains template placeholders rather than enforceable project rules. No active constitutional constraints or mandatory gates are defined, so the feature can proceed. This should be corrected separately so future plans have real governance input.

**Gate Result (pre-research)**: PASS, with no enforceable constitution rules present.

## Project Structure

### Documentation (this feature)

```text
specs/001-automate-pdf-linking/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── worker-job.schema.json
│   └── worker-result.schema.json
└── tasks.md
```

### Source Code (repository root)

```text
src/
├── main.py
├── config.py                  # site prefix and environment configuration
├── worker.py                  # container entrypoint for async processing
├── job_models.py              # processing job, stage result, and payload models
├── orchestration/
│   └── event_handler.py       # S3 event normalization and job kickoff
├── services/
│   ├── pdf_pipeline.py        # extracted reusable page-by-page linking pipeline
│   ├── routing.py             # prefix-to-site resolution and validation
│   ├── publication.py         # flipbook publishing workflow
│   ├── notifications.py       # success and failure notification dispatch
│   └── job_tracker.py         # job state transitions and persistence
└── adapters/
    ├── s3_storage.py          # input download and output upload
    ├── magento_catalog.py     # site-aware SKU lookup
    ├── flipbook_client.py     # external publication client
    └── dynamodb_jobs.py       # job metadata persistence

tests/
├── test_main.py
├── unit/
├── integration/
└── contract/
```

**Structure Decision**: Keep a single Python project rooted in `src/` and preserve `src/main.py` as the local CLI entrypoint. Extract reusable pipeline logic behind service and adapter modules so the same core linking behavior can be invoked both locally and from the asynchronous worker.

## Complexity Tracking

No constitution violations require justification.

## Phase 0 Research Summary

Phase 0 outputs are recorded in `/home/xzhang/project/FlippingPdfTool/specs/001-automate-pdf-linking/research.md`.

## Phase 1 Design Summary

Phase 1 outputs are recorded in:

- `/home/xzhang/project/FlippingPdfTool/specs/001-automate-pdf-linking/data-model.md`
- `/home/xzhang/project/FlippingPdfTool/specs/001-automate-pdf-linking/contracts/worker-job.schema.json`
- `/home/xzhang/project/FlippingPdfTool/specs/001-automate-pdf-linking/contracts/worker-result.schema.json`
- `/home/xzhang/project/FlippingPdfTool/specs/001-automate-pdf-linking/quickstart.md`

## Post-Design Constitution Check

The constitution file still contains placeholders only, so there are no enforceable post-design gates to evaluate. The design remains consistent with the repository's current lightweight Python CLI structure and adds only the minimum new modules required for asynchronous orchestration.

**Gate Result (post-design)**: PASS, with no enforceable constitution rules present.
# Implementation Plan: Automated PDF Link Publishing

**Branch**: `[001-automate-pdf-linking]` | **Date**: 2026-04-23 | **Spec**: `/home/xzhang/project/FlippingPdfTool/specs/001-automate-pdf-linking/spec.md`
**Input**: Feature specification from `/home/xzhang/project/FlippingPdfTool/specs/001-automate-pdf-linking/spec.md`

## Summary

Automate catalog processing from site-specific S3 ingest through linked-PDF generation, flipbook publication, and stakeholder notification by wrapping the existing page-by-page Python linker in an AWS Step Functions and ECS Fargate workflow. The design adds an explicit ingest-routing step that validates the source prefix, derives the site configuration for `currentcatalog`, `colorfulimages`, or `lillianvernon`, writes the linked PDF back to the matching output prefix, and fails fast before PDF processing when the prefix is unknown.

## Technical Context

**Language/Version**: Python 3.14 container runtime for worker and helper entrypoints; existing local pipeline remains Python-based  
**Primary Dependencies**: boto3, requests, PyMuPDF, Pillow, OpenCV, NumPy, Amazon Textract, AWS Step Functions, ECS/Fargate, SES or SNS, Secrets Manager  
**Storage**: Amazon S3 for source PDFs, linked PDFs, and retained artifacts; DynamoDB for durable processing-job state; ephemeral container storage for intermediate page images  
**Testing**: Existing `unittest` suite for `src/main.py`; planned unit tests for routing and state transitions; contract tests for workflow payloads; integration tests for worker orchestration boundaries  
**Target Platform**: Linux containers on ECS Fargate coordinated by AWS Step Functions
**Project Type**: Single Python repository with a reusable PDF-linking core plus workflow/orchestration adapters  
**Performance Goals**: Meet spec targets of 95% unattended completion for valid uploads, linked output available within 15 minutes for catalogs up to 100 pages, 90% hyperlink coverage for resolvable pairs, and notifications for 100% of failures  
**Constraints**: Preserve the existing page-by-page linking behavior as the domain core; route strictly from the uploaded S3 prefix; reject unknown prefixes before PDF processing; keep successful upstream artifacts when downstream steps fail; use site-specific Magento store codes and domains; support duplicate uploads without ambiguous final job state  
**Scale/Scope**: One uploaded catalog PDF per job, up to 100 pages per success target, three supported site configurations, one linked PDF and optional flipbook URL per job

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- Constitution file review: `/home/xzhang/project/FlippingPdfTool/.specify/memory/constitution.md` is still an unfilled template with placeholder principle names and no ratified project-specific rules.
- Pre-Phase 0 gate result: PASS by default. No enforceable constitution clauses exist that would block planning.
- Post-Phase 1 gate result: PASS by default. The design remains conservative by preserving the tested PDF-linking core, adding explicit contracts, and documenting failure isolation.

## Project Structure

### Documentation (this feature)

```text
specs/001-automate-pdf-linking/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── workflow-contracts.md
└── tasks.md               # Created later by /speckit.tasks
```

### Source Code (repository root)

```text
src/
├── main.py                # Existing PDF-linking core to preserve
└── worker/
    ├── entrypoint.py      # Planned worker orchestration entrypoint
    ├── routing.py         # Planned S3 prefix validation and site mapping
    ├── catalog_client.py  # Planned Magento lookup adapter
    ├── publish_client.py  # Planned flipbook publication adapter
    ├── notify_client.py   # Planned SES/SNS notification adapter
    └── job_repository.py  # Planned DynamoDB job-state persistence

tests/
├── test_main.py           # Existing PDF-linking unit coverage
├── contract/
│   └── test_workflow_contracts.py
├── integration/
│   └── test_worker_flow.py
└── unit/
    └── test_site_routing.py
```

**Structure Decision**: Keep the repository as a single Python project. `src/main.py` remains the business-logic core for rendering, OCR, SKU extraction, and PDF annotation, while new workflow adapters live under `src/worker/` so cloud orchestration concerns stay isolated from the proven linking logic.

## Complexity Tracking

No constitution violations are currently defined, so no complexity exceptions are required.
