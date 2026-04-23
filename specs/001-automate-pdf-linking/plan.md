# Implementation Plan: Automated PDF Link Publishing

**Branch**: `[001-automate-pdf-linking]` | **Date**: 2026-04-23 | **Spec**: [/home/xzhang/project/FlippingPdfTool/specs/001-automate-pdf-linking/spec.md](/home/xzhang/project/FlippingPdfTool/specs/001-automate-pdf-linking/spec.md)
**Input**: Feature specification from `/specs/001-automate-pdf-linking/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Automate the current PDF-linking CLI so an uploaded catalog PDF starts an asynchronous cloud workflow that downloads the source from S3, runs the existing page-by-page OCR and hyperlinking pipeline inside a container worker, stores the linked PDF back to S3, publishes the result to the flipbook service, and sends outcome notifications with durable job-stage logging.

## Technical Context

<!--
  ACTION REQUIRED: Replace the content in this section with the technical details
  for the project. The structure here is presented in advisory capacity to guide
  the iteration process.
-->

**Language/Version**: Python 3.14 container runtime for the worker and helper entrypoints  
**Primary Dependencies**: boto3, requests, PyMuPDF, Pillow, OpenCV, NumPy, AWS Textract, AWS Step Functions, ECS/Fargate, SES or SNS, Secrets Manager  
**Storage**: Amazon S3 for source/output PDFs and processing artifacts, DynamoDB for durable processing-job state, local ephemeral container storage for intermediate page images  
**Testing**: `unittest` for unit/integration tests, persisted-PDF verification for link annotations, contract-style tests for worker inputs and external service adapters  
**Target Platform**: Linux containers running on AWS Fargate, triggered from AWS-managed event sources
**Project Type**: Single-project Python service/worker built around the existing CLI pipeline  
**Performance Goals**: Correctly process one uploaded catalog per job, support large PDFs over 70 MB and 80+ pages, and complete end-to-end workflow without Lambda runtime constraints  
**Constraints**: Must preserve the existing page-by-page linking logic, skip unmatched SKUs without adding links, handle long-running OCR-heavy jobs asynchronously, keep the source filename for the output artifact, and preserve partial artifacts when downstream publication/notification fails  
**Scale/Scope**: One orchestration per uploaded PDF, dozens to hundreds of pages per file, per-page Textract and artifact generation, operational visibility across ingest, processing, publish, and notification stages

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

The current constitution file is an unfilled template with placeholder sections only, so it defines no enforceable project-specific gates yet.

- Gate status before Phase 0: PASS, no concrete constitutional constraints to violate.
- Additional follow-up: establish a real constitution before later features if project-level engineering gates are expected.
- Gate status after Phase 1 design: PASS, design artifacts do not conflict with any active constitutional rules.

## Project Structure

### Documentation (this feature)

```text
specs/001-automate-pdf-linking/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)
<!--
  ACTION REQUIRED: Replace the placeholder tree below with the concrete layout
  for this feature. Delete unused options and expand the chosen structure with
  real paths (e.g., apps/admin, packages/something). The delivered plan must
  not include Option labels.
-->

```text
src/
├── __init__.py
├── main.py
├── worker.py
├── orchestrators/
│   └── workflow_entry.py
├── integrations/
│   ├── flipbook_client.py
│   ├── magento_client.py
│   ├── notifier.py
│   ├── s3_storage.py
│   └── job_store.py
└── pipeline/
  ├── processor.py
  └── models.py

tests/
├── test_main.py
├── unit/
│   ├── test_magento_client.py
│   ├── test_flipbook_client.py
│   └── test_notifier.py
├── integration/
│   ├── test_worker_flow.py
│   └── test_job_store.py
└── contract/
  └── test_worker_contract.py
```

**Structure Decision**: Keep the repository as a single Python project rooted in `src/` and `tests/`. Extract cloud orchestration and service integrations from the current `src/main.py` into focused modules while preserving the existing PDF-processing logic as the core pipeline implementation.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |
