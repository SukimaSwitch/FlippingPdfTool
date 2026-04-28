---

description: "Implementation tasks for automated PDF link publishing"

---

# Tasks: Automated PDF Link Publishing

**Input**: Design documents from `/specs/001-automate-pdf-linking/`
**Prerequisites**: `plan.md` (required), `spec.md` (required), `research.md`, `data-model.md`, `quickstart.md`, `contracts/`

**Tests**: Tests are required for this feature because the specification includes mandatory scenario coverage, worker-contract validation, and failure-path verification.

**Organization**: Tasks are grouped by user story so each increment can be implemented and validated independently.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel when the listed files do not overlap and prerequisite tasks are complete.
- **[Story]**: Story label for user-story phases only (`[US1]`, `[US2]`, `[US3]`).
- Every task includes the exact file path that should be changed or created.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Prepare the repository, runtime dependencies, and operator documentation for the worker-driven workflow.

- [x] T001 Align worker and local runtime dependencies in /home/xzhang/project/FlippingPdfTool/requirements.txt and /home/xzhang/project/FlippingPdfTool/Dockerfile
- [x] T002 Document AWS, Magento, flipbook, and notification configuration requirements in /home/xzhang/project/FlippingPdfTool/README.md and /home/xzhang/project/FlippingPdfTool/static/Requirements.txt
- [x] T003 [P] Refresh local validation and routed-upload setup steps in /home/xzhang/project/FlippingPdfTool/specs/001-automate-pdf-linking/quickstart.md

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Establish the shared contracts, routing model, persistence, and logging required by every story.

**⚠️ CRITICAL**: No user story work should start until this phase is complete.

- [x] T004 Normalize the shared-bucket plus site-prefix worker schemas in /home/xzhang/project/FlippingPdfTool/specs/001-automate-pdf-linking/contracts/worker-job.schema.json and /home/xzhang/project/FlippingPdfTool/specs/001-automate-pdf-linking/contracts/worker-result.schema.json
- [x] T005 [P] Encode exact-SKU matching, `custom_attributes.url_key` extraction, final `.html` URL construction, and unresolved-match rules in /home/xzhang/project/FlippingPdfTool/specs/001-automate-pdf-linking/contracts/workflow-contracts.md
- [x] T006 [P] Expand shared source, site, job, page-result, product-match, and unresolved-match models in /home/xzhang/project/FlippingPdfTool/src/worker/models.py
- [x] T007 [P] Implement supported-prefix validation, site-configuration derivation, and output-key routing in /home/xzhang/project/FlippingPdfTool/src/worker/routing.py
- [x] T008 Implement durable job-stage, page-result, and unresolved-match persistence in /home/xzhang/project/FlippingPdfTool/src/worker/job_repository.py
- [x] T009 [P] Add structured stage and page logging helpers in /home/xzhang/project/FlippingPdfTool/src/worker/logging_utils.py
- [x] T010 Add foundational routing and job-repository unit coverage in /home/xzhang/project/FlippingPdfTool/tests/unit/test_site_routing.py and /home/xzhang/project/FlippingPdfTool/tests/unit/test_job_repository.py

**Checkpoint**: Shared contracts, routing, persistence, and logging are ready for story work.

---

## Phase 3: User Story 1 - Produce a linked catalog automatically (Priority: P1) 🎯 MVP

**Goal**: Accept a valid routed catalog upload, resolve exact Magento matches into customer URLs, leave unmatched or unresolved items unlinked, and write the linked PDF to the site-matched output key.

**Independent Test**: Submit a routed worker job for a valid PDF and verify that the output PDF is written to the expected `output/<site-prefix>/...` key with links only for exact SKU matches that expose `url_key`.

### Tests for User Story 1

- [x] T011 [P] [US1] Add worker-contract assertions for exact SKU matching and unresolved `url_key` cases in /home/xzhang/project/FlippingPdfTool/tests/contract/test_workflow_contracts.py
- [x] T012 [P] [US1] Add Magento catalog-client unit coverage for exact matches, partial-only matches, and missing `url_key` responses in /home/xzhang/project/FlippingPdfTool/tests/unit/test_catalog_client.py
- [x] T013 [P] [US1] Add accepted-route processing integration coverage for linked output, unmatched SKUs, and unresolved matches in /home/xzhang/project/FlippingPdfTool/tests/integration/test_worker_flow.py

### Implementation for User Story 1

- [x] T014 [P] [US1] Refactor the reusable PDF-linking pipeline entrypoint in /home/xzhang/project/FlippingPdfTool/src/main.py
- [x] T015 [P] [US1] Implement Magento lookup, exact-SKU filtering, `custom_attributes` parsing, and final URL construction in /home/xzhang/project/FlippingPdfTool/src/worker/catalog_client.py
- [x] T016 [P] [US1] Implement source-download, output-upload, and artifact-prefix S3 helpers in /home/xzhang/project/FlippingPdfTool/src/worker/storage_client.py
- [x] T017 [US1] Wire routed page processing, resolved-link creation, and unresolved-match capture in /home/xzhang/project/FlippingPdfTool/src/worker/pipeline_runner.py
- [x] T018 [US1] Implement accepted-job worker execution and routed output handling in /home/xzhang/project/FlippingPdfTool/src/worker/entrypoint.py
- [x] T019 [US1] Persist page results, product matches, unmatched SKUs, and unresolved matches in /home/xzhang/project/FlippingPdfTool/src/worker/job_repository.py

**Checkpoint**: User Story 1 should produce a linked PDF from a valid routed upload without requiring publication or notification.

---

## Phase 4: User Story 2 - Publish the linked catalog and notify stakeholders (Priority: P2)

**Goal**: Publish the linked PDF as a flipbook, record the returned publication URL, and send a success notification with the final outcome.

**Independent Test**: Complete a successful processing run and verify that the flipbook URL is persisted and included in the success notification payload.

### Tests for User Story 2

- [x] T020 [P] [US2] Add publication and success-notification contract coverage in /home/xzhang/project/FlippingPdfTool/tests/contract/test_workflow_contracts.py
- [x] T021 [P] [US2] Add publish-and-notify success integration coverage in /home/xzhang/project/FlippingPdfTool/tests/integration/test_worker_flow.py
- [x] T022 [P] [US2] Add flipbook-client and success-notification unit coverage in /home/xzhang/project/FlippingPdfTool/tests/unit/test_publish_client.py and /home/xzhang/project/FlippingPdfTool/tests/unit/test_notify_client.py

### Implementation for User Story 2

- [x] T023 [P] [US2] Implement the flipbook publication client in /home/xzhang/project/FlippingPdfTool/src/worker/publish_client.py
- [x] T024 [P] [US2] Implement success notification payload construction and delivery in /home/xzhang/project/FlippingPdfTool/src/worker/notify_client.py
- [x] T025 [US2] Orchestrate publication, flipbook URL recording, and success notification dispatch in /home/xzhang/project/FlippingPdfTool/src/worker/entrypoint.py
- [x] T026 [US2] Persist publication and notification stage outcomes in /home/xzhang/project/FlippingPdfTool/src/worker/job_repository.py

**Checkpoint**: User Stories 1 and 2 should run end to end for a successful job and produce a notification containing the flipbook URL.

---

## Phase 5: User Story 3 - Diagnose failures quickly (Priority: P3)

**Goal**: Reject unsupported uploads early, preserve successful artifacts after downstream failures, and record terminal-state details that identify the failed stage without obscuring partial results.

**Independent Test**: Trigger unsupported-prefix, invalid-PDF, publication-failure, and notification-failure scenarios and verify that job state, notifications, and retained artifacts reflect the precise stage that failed.

### Tests for User Story 3

- [x] T027 [P] [US3] Add rejected-routing and partial-failure contract coverage in /home/xzhang/project/FlippingPdfTool/tests/contract/test_workflow_contracts.py
- [x] T028 [P] [US3] Add invalid-PDF, publication-failure, and notification-failure integration coverage in /home/xzhang/project/FlippingPdfTool/tests/integration/test_worker_flow.py
- [x] T029 [P] [US3] Add failure-notification and artifact-preservation unit coverage in /home/xzhang/project/FlippingPdfTool/tests/unit/test_notify_client.py and /home/xzhang/project/FlippingPdfTool/tests/unit/test_storage_client.py

### Implementation for User Story 3

- [x] T030 [P] [US3] Extend notification handling for failure and partial-success payloads in /home/xzhang/project/FlippingPdfTool/src/worker/notify_client.py
- [x] T031 [P] [US3] Preserve diagnostic artifacts and already-created outputs after downstream failures in /home/xzhang/project/FlippingPdfTool/src/worker/storage_client.py
- [x] T032 [P] [US3] Track dedupe keys, failure stages, terminal summaries, and completed-with-errors outcomes in /home/xzhang/project/FlippingPdfTool/src/worker/job_repository.py
- [x] T033 [US3] Reject unsupported prefixes before worker execution and finalize partial-failure outcomes in /home/xzhang/project/FlippingPdfTool/src/worker/entrypoint.py

**Checkpoint**: All terminal outcomes should be diagnosable and should preserve artifacts created before a downstream failure.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Finalize regression coverage, operator-facing documentation, and end-to-end validation notes.

- [x] T034 [P] Add shared CLI and worker-regression coverage in /home/xzhang/project/FlippingPdfTool/tests/test_main.py
- [x] T035 [P] Update operator validation steps for Magento exact-match and `url_key` rules in /home/xzhang/project/FlippingPdfTool/specs/001-automate-pdf-linking/quickstart.md and /home/xzhang/project/FlippingPdfTool/README.md
- [x] T036 Run the unittest suite and record any remaining infrastructure gaps in /home/xzhang/project/FlippingPdfTool/specs/001-automate-pdf-linking/quickstart.md

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1: Setup** has no dependencies and can begin immediately.
- **Phase 2: Foundational** depends on Phase 1 and blocks every user story.
- **Phase 3: US1** depends on Phase 2 and is the MVP slice.
- **Phase 4: US2** depends on US1 producing linked PDFs and persisted job-state updates.
- **Phase 5: US3** depends on US1 and US2 because it verifies failures across routing, processing, publication, and notification.
- **Phase 6: Polish** depends on the in-scope user stories being complete.

### User Story Dependencies

- **US1** is the first independently deliverable increment.
- **US2** depends on US1 artifacts and adds publication plus stakeholder notification.
- **US3** depends on the earlier stages existing so failure and partial-success paths can be exercised end to end.

### Within Each User Story

- Contract, unit, and integration tests should be written before the implementation tasks they verify.
- Shared adapters should land before orchestration code that invokes them.
- Persistence updates should land before final orchestration wiring so stage transitions can be asserted.

### Parallel Opportunities

- `T003` can run in parallel with `T001` and `T002` during setup.
- `T005`, `T006`, `T007`, and `T009` can run in parallel after `T004` establishes the baseline schema shape.
- `T011`, `T012`, and `T013` can run in parallel for US1.
- `T014`, `T015`, and `T016` can run in parallel for US1 before `T017` and `T018`.
- `T020`, `T021`, and `T022` can run in parallel for US2.
- `T023` and `T024` can run in parallel for US2 before `T025`.
- `T027`, `T028`, and `T029` can run in parallel for US3.
- `T030`, `T031`, and `T032` can run in parallel for US3 before `T033`.
- `T034` and `T035` can run in parallel during polish.

---

## Parallel Example: User Story 1

```bash
# Cover the Magento semantics first
Task: "T011 Add worker-contract assertions for exact SKU matching and unresolved `url_key` cases in tests/contract/test_workflow_contracts.py"
Task: "T012 Add Magento catalog-client unit coverage for exact matches, partial-only matches, and missing `url_key` responses in tests/unit/test_catalog_client.py"
Task: "T013 Add accepted-route processing integration coverage for linked output, unmatched SKUs, and unresolved matches in tests/integration/test_worker_flow.py"

# Build the independent US1 adapters together
Task: "T014 Refactor the reusable PDF-linking pipeline entrypoint in src/main.py"
Task: "T015 Implement Magento lookup, exact-SKU filtering, `custom_attributes` parsing, and final URL construction in src/worker/catalog_client.py"
Task: "T016 Implement source-download, output-upload, and artifact-prefix S3 helpers in src/worker/storage_client.py"
```

---

## Parallel Example: User Story 2

```bash
# Validate publication and notification success-path behavior together
Task: "T020 Add publication and success-notification contract coverage in tests/contract/test_workflow_contracts.py"
Task: "T021 Add publish-and-notify success integration coverage in tests/integration/test_worker_flow.py"
Task: "T022 Add flipbook-client and success-notification unit coverage in tests/unit/test_publish_client.py and tests/unit/test_notify_client.py"

# Build the independent US2 adapters together
Task: "T023 Implement the flipbook publication client in src/worker/publish_client.py"
Task: "T024 Implement success notification payload construction and delivery in src/worker/notify_client.py"
```

---

## Parallel Example: User Story 3

```bash
# Exercise failure contracts and failure flows together
Task: "T027 Add rejected-routing and partial-failure contract coverage in tests/contract/test_workflow_contracts.py"
Task: "T028 Add invalid-PDF, publication-failure, and notification-failure integration coverage in tests/integration/test_worker_flow.py"
Task: "T029 Add failure-notification and artifact-preservation unit coverage in tests/unit/test_notify_client.py and tests/unit/test_storage_client.py"

# Build failure-handling components together
Task: "T030 Extend notification handling for failure and partial-success payloads in src/worker/notify_client.py"
Task: "T031 Preserve diagnostic artifacts and already-created outputs after downstream failures in src/worker/storage_client.py"
Task: "T032 Track dedupe keys, failure stages, terminal summaries, and completed-with-errors outcomes in src/worker/job_repository.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup.
2. Complete Phase 2: Foundational.
3. Complete Phase 3: User Story 1.
4. Validate the accepted-route processing flow independently before expanding scope.

### Incremental Delivery

1. Deliver US1 to prove site-aware routed PDF linking and output storage.
2. Add US2 to publish the linked PDF and notify stakeholders on successful jobs.
3. Add US3 to harden rejected-routing, downstream failure visibility, and artifact preservation.
4. Finish with Phase 6 regression coverage and operator-facing documentation.

### Suggested MVP Scope

Implement through **Phase 3 / US1** first. That is the smallest useful automation slice: valid uploaded PDFs are routed, processed with exact Magento matching rules, and written to the correct output prefix.

---

## Notes

- Total tasks: 36.
- Story task counts: US1 = 9, US2 = 7, US3 = 7.
- All tasks follow the required checklist format: checkbox, task ID, optional `[P]`, required story label for story phases, and explicit file paths.
- The Magento clarifications are enforced in contract, unit, integration, and implementation tasks so exact SKU filtering and `url_key` handling cannot be skipped.
