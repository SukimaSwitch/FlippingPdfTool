# Implementation Plan: Automated PDF Link Publishing

**Branch**: `[001-automate-pdf-linking]` | **Date**: 2026-04-23 | **Spec**: `specs/001-automate-pdf-linking/spec.md`
**Input**: Feature specification from `specs/001-automate-pdf-linking/spec.md`

## Summary

Automate catalog processing from site-specific S3 ingest through linked-PDF generation, flipbook publication, and stakeholder notification by wrapping the existing page-by-page Python linker in an asynchronous AWS workflow. The design adds an explicit ingest-routing step that validates the source prefix, derives the site configuration for `currentcatalog`, `colorfulimages`, or `lillianvernon`, writes the linked PDF back to the matching output prefix, and fails fast before PDF processing when the prefix is unknown.

## Technical Context

**Language/Version**: Python 3.14 container runtime for worker and helper entrypoints; existing local pipeline remains Python-based  
**Primary Dependencies**: `boto3`, `requests`, `PyMuPDF`, `Pillow`, `opencv-python`, `numpy`, Amazon Textract, AWS Step Functions, ECS/Fargate, SES or SNS, Secrets Manager  
**Storage**: Amazon S3 for source PDFs, linked PDFs, and retained artifacts; DynamoDB for durable processing-job state; ephemeral container storage for intermediate page images  
**Testing**: `unittest` via `.venv/bin/python -m unittest discover -s tests -v`, plus unit tests for routing and state transitions, contract tests for workflow payloads, and integration tests for worker orchestration boundaries  
**Target Platform**: Linux containers on ECS Fargate coordinated by AWS Step Functions  
**Project Type**: Single Python repository with a reusable PDF-linking core plus workflow and orchestration adapters  
**Performance Goals**: Meet the spec targets of unattended completion for valid uploads, linked output available within 15 minutes for catalogs up to 100 pages, and notifications for all terminal outcomes  
**Constraints**: Preserve the existing page-by-page linking behavior as the domain core; route strictly from the uploaded S3 prefix; reject unknown prefixes before PDF processing; keep successful upstream artifacts when downstream steps fail; use site-specific Magento store codes and domains; support duplicate uploads without ambiguous final job state  
**Scale/Scope**: One uploaded catalog PDF per job, up to 100 pages per success target, three supported site configurations, one linked PDF and optional flipbook URL per job

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- Constitution file review: `.specify/memory/constitution.md` is still an unfilled template with placeholder principle names and no ratified project-specific rules.
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
│   ├── worker-job.schema.json
│   ├── worker-result.schema.json
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

## Phase 0 Research Summary

Phase 0 outputs are recorded in `specs/001-automate-pdf-linking/research.md`.

## Phase 1 Design Summary

Phase 1 outputs are recorded in:

- `specs/001-automate-pdf-linking/data-model.md`
- `specs/001-automate-pdf-linking/contracts/worker-job.schema.json`
- `specs/001-automate-pdf-linking/contracts/worker-result.schema.json`
- `specs/001-automate-pdf-linking/contracts/workflow-contracts.md`
- `specs/001-automate-pdf-linking/quickstart.md`

## Post-Design Constitution Check

The constitution file still contains placeholders only, so there are no enforceable post-design gates to evaluate. The design remains consistent with the repository's current lightweight Python CLI structure and adds only the minimum new modules required for asynchronous orchestration.

**Gate Result (post-design)**: PASS, with no enforceable constitution rules present.
