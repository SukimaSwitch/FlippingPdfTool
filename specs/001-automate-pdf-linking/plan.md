# Implementation Plan: Automated PDF Link Publishing

**Branch**: `[001-automate-pdf-linking]` | **Date**: 2026-04-28 | **Spec**: `/home/xzhang/project/FlippingPdfTool/specs/001-automate-pdf-linking/spec.md`
**Input**: Feature specification from `/home/xzhang/project/FlippingPdfTool/specs/001-automate-pdf-linking/spec.md`

## Summary

 Automate catalog PDF processing by routing uploads from `cmg-catalog-book/input/<site-prefix>/...` into a site-aware worker workflow that reuses the existing page-by-page PDF-linking pipeline, writes linked PDFs to `cmg-catalog-book/output/<site-prefix>/...`, and sends stakeholder notifications. Magento lookups remain site-specific and must authenticate first, either with a preissued bearer token or by exchanging configured username/password credentials through `POST /rest/V1/integration/admin/token`, then use the store-code product route, require an exact SKU match from the response, extract `url_key` from `custom_attributes`, and build the final customer URL as `https://<domain>/<url_key>.html`; exact matches without `url_key` stay unlinked and are recorded as unresolved matches.

## Technical Context

**Language/Version**: Python 3.14 container runtime for the worker, with the existing Python CLI reused locally  
 **Primary Dependencies**: boto3, requests, PyMuPDF, Pillow, opencv-python-headless, numpy, AWS Textract integration, Step Functions/ECS adapters, SES or SNS notification adapter, Magento admin-token exchange over XML login payloads  
**Storage**: Amazon S3 for source/output/artifacts, DynamoDB for durable job state, Secrets Manager for third-party credentials, local ephemeral container storage for rendered/intermediate page files  
**Testing**: Python `unittest` suite with unit, integration, and contract coverage  
**Target Platform**: Linux container on ECS/Fargate, orchestrated by AWS Step Functions  
**Project Type**: Python CLI plus asynchronous worker/orchestration service  
**Performance Goals**: Complete valid jobs for PDFs larger than 70 MB and 80+ pages without failing solely due to short-lived trigger runtime limits  
**Constraints**: Reject unsupported prefixes before processing, preserve successfully created artifacts after downstream failures, keep existing page-linking behavior as the domain core, and treat partial/non-exact Magento matches as non-linkable  
**Scale/Scope**: One processing job per uploaded PDF, three supported storefronts, page-by-page artifact capture for diagnostics and resumability

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- The repository constitution at `/home/xzhang/project/FlippingPdfTool/.specify/memory/constitution.md` is still an unratified placeholder template with no enforceable project-specific principles.
- Result before research: PASS for planning execution because there are no concrete gates to violate.
- Result after design: PASS unchanged; follow-up needed outside this feature to replace the placeholder constitution with real governance rules if future planning gates should be binding.

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
└── tasks.md
```

### Source Code (repository root)

```text
src/
├── __init__.py
├── main.py
└── worker/
  ├── __init__.py
  ├── catalog_client.py
  ├── entrypoint.py
  ├── job_repository.py
  ├── logging_utils.py
  ├── models.py
  ├── notify_client.py
  ├── pipeline_runner.py
  ├── routing.py
  └── storage_client.py

tests/
├── __init__.py
├── test_main.py
├── contract/
├── integration/
└── unit/

static/
└── Requirements.txt
```

**Structure Decision**: Keep a single Python project. Reuse `src/main.py` as the domain pipeline entrypoint and isolate cloud-specific orchestration, routing, persistence, manual-upload handoff, and notification concerns inside `src/worker/`. Keep design contracts under `specs/001-automate-pdf-linking/contracts/` because the external interface for this feature is the orchestration payload boundary rather than a public HTTP API.

## Phase 0: Research Focus

- Confirm the worker orchestration model for long-running PDFs.
- Confirm the physical S3 bucket plus logical prefix layout implied by the spec.
- Confirm the Magento authentication and URL-resolution rules: admin-token exchange or bearer-token reuse, store-code route, exact SKU filtering, `url_key` extraction, final `.html` URL shape, and unresolved-match handling.
- Confirm persistence and artifact-retention strategy for diagnosable partial failures.

## Phase 1: Design Focus

- Model routing, processing, page-level diagnostics, resolved links, unresolved matches, exported PDF artifacts, and notification outcomes.
- Define the worker handoff/result contracts and document Magento authentication plus resolution semantics that affect worker behavior.
- Capture an operator/developer quickstart that validates routing, worker execution, Magento URL generation, exported-PDF access, and failure handling.
- Refresh agent context after the design artifacts are updated.

## Post-Design Constitution Check

- Re-checked after Phase 1 artifact updates.
- No enforceable constitution gates exist yet, so the design remains PASS.
- No justified violations were required.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
| --------- | ---------- | ----------------------------------- |
| None | N/A | N/A |
