---

description: "Implementation tasks for automated PDF link publishing"
---

# Tasks: Automated PDF Link Publishing

**Input**: Design documents from `/specs/001-automate-pdf-linking/`
**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), `contracts/`

**Tests**: Tests are required for this feature because the specification defines mandatory user-scenario coverage, contract validation, and integration checks.

**Organization**: Tasks are grouped by user story so each increment can be implemented and verified independently.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Prepare the repository for the worker-based workflow and shared runtime configuration.

- [ ] T001 Update worker and cloud runtime dependencies in requirements.txt
- [ ] T002 Create the worker package scaffold in src/worker/__init__.py
- [ ] T003 [P] Add a container build for the worker runtime in Dockerfile
- [ ] T004 [P] Document worker environment variables and AWS prerequisites in README.md

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Establish shared contracts, routing, persistence, and logging before user-story work begins.

**⚠️ CRITICAL**: No user story work should start until this phase is complete.

- [ ] T005 Reconcile worker input schema with the S3 bucket-plus-prefix routing model in specs/001-automate-pdf-linking/contracts/worker-job.schema.json
- [ ] T006 [P] Reconcile worker result schema and workflow payload examples in specs/001-automate-pdf-linking/contracts/worker-result.schema.json and specs/001-automate-pdf-linking/contracts/workflow-contracts.md
- [ ] T007 [P] Create shared job and site configuration models in src/worker/models.py
- [ ] T008 [P] Implement site-prefix validation and output routing in src/worker/routing.py
- [ ] T009 Implement durable job-state persistence for processing stages in src/worker/job_repository.py
- [ ] T010 [P] Add structured workflow logging helpers for stage and page progress in src/worker/logging_utils.py
- [ ] T011 Add foundational unit coverage for routing and job state persistence in tests/unit/test_site_routing.py and tests/unit/test_job_repository.py

**Checkpoint**: Routing, contracts, persistence, and logging are ready for story implementation.

---

## Phase 3: User Story 1 - Produce a linked catalog automatically (Priority: P1) 🎯 MVP

**Goal**: Accept a valid uploaded PDF, derive the site configuration from its S3 prefix, run the existing linking pipeline, and write the linked PDF to the matching output prefix.

**Independent Test**: Submit a routed worker job for a valid PDF and verify that the linked output PDF is written to the configured output key with preserved filename and link annotations for matched products.

### Tests for User Story 1

- [ ] T012 [P] [US1] Add worker-input contract validation coverage in tests/contract/test_workflow_contracts.py
- [ ] T013 [P] [US1] Add an accepted-route processing integration test in tests/integration/test_worker_flow.py

### Implementation for User Story 1

- [ ] T014 [P] [US1] Refactor src/main.py to expose a reusable PDF-linking pipeline entrypoint in src/main.py
- [ ] T015 [P] [US1] Implement the Magento SKU lookup adapter in src/worker/catalog_client.py
- [ ] T016 [P] [US1] Implement S3 download and upload helpers for source PDFs and linked outputs in src/worker/storage_client.py
- [ ] T017 [US1] Implement the worker pipeline runner that invokes the shared PDF-linking core and stages page artifacts in src/worker/pipeline_runner.py
- [ ] T018 [US1] Implement the worker entrypoint for accepted jobs and matched output routing in src/worker/entrypoint.py
- [ ] T019 [US1] Add page-result and product-match persistence during processing in src/worker/job_repository.py

**Checkpoint**: User Story 1 should produce a linked PDF from a valid uploaded catalog without publication or notification stages.

---

## Phase 4: User Story 2 - Publish the linked catalog and notify stakeholders (Priority: P2)

**Goal**: Publish a successfully linked PDF as a flipbook and send a success notification with the resulting URL.

**Independent Test**: Complete a successful processing run and verify that the flipbook URL is recorded and included in the success notification payload.

### Tests for User Story 2

- [ ] T020 [P] [US2] Add publication and success-notification contract coverage in tests/contract/test_workflow_contracts.py
- [ ] T021 [P] [US2] Add a publish-and-notify success integration test in tests/integration/test_worker_flow.py

### Implementation for User Story 2

- [ ] T022 [P] [US2] Implement the flipbook publication client in src/worker/publish_client.py
- [ ] T023 [P] [US2] Implement the stakeholder notification client for success outcomes in src/worker/notify_client.py
- [ ] T024 [US2] Extend the worker orchestration to publish linked PDFs and record flipbook URLs in src/worker/entrypoint.py
- [ ] T025 [US2] Persist publication and notification stage outcomes in src/worker/job_repository.py

**Checkpoint**: User Stories 1 and 2 should complete end to end for a successful job and emit a success notification with the flipbook URL.

---

## Phase 5: User Story 3 - Diagnose failures quickly (Priority: P3)

**Goal**: Reject unsupported uploads early, preserve successful artifacts after downstream failures, and surface clear terminal-state details for operations users.

**Independent Test**: Trigger rejected-prefix, invalid-PDF, publication-failure, and notification-failure scenarios and verify that job state, stored artifacts, and notifications reflect the exact failed stage.

### Tests for User Story 3

- [ ] T026 [P] [US3] Add rejected-routing and partial-failure contract coverage in tests/contract/test_workflow_contracts.py
- [ ] T027 [P] [US3] Add failure-path integration coverage for invalid PDFs, publication failures, and notification failures in tests/integration/test_worker_flow.py

### Implementation for User Story 3

- [ ] T028 [P] [US3] Extend the notification client for failure and partial-success payloads in src/worker/notify_client.py
- [ ] T029 [P] [US3] Persist failure-stage details, duplicate-upload dedupe keys, and terminal summaries in src/worker/job_repository.py
- [ ] T030 [P] [US3] Persist diagnostic artifacts and artifact-retention metadata in src/worker/storage_client.py
- [ ] T031 [US3] Extend the worker entrypoint to reject unsupported prefixes before processing and finalize partial-success outcomes in src/worker/entrypoint.py

**Checkpoint**: All terminal outcomes should be visible, diagnosable, and consistent with the preserved artifacts.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Finalize documentation, regression coverage, and end-to-end validation across the full workflow.

- [ ] T032 [P] Add regression coverage for shared CLI and worker pipeline reuse in tests/test_main.py
- [ ] T033 [P] Update operator validation steps and local workflow examples in specs/001-automate-pdf-linking/quickstart.md and README.md
- [ ] T034 Run the required unittest suite and capture any follow-up gaps in specs/001-automate-pdf-linking/quickstart.md

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1: Setup** has no dependencies and can begin immediately.
- **Phase 2: Foundational** depends on Phase 1 and blocks all story work.
- **Phase 3: User Story 1** depends on Phase 2.
- **Phase 4: User Story 2** depends on User Story 1 producing linked PDFs and shared job-state updates.
- **Phase 5: User Story 3** depends on User Stories 1 and 2 because it validates failure paths across routing, processing, publication, and notification.
- **Phase 6: Polish** depends on the stories that are in scope being complete.

### User Story Dependencies

- **US1** is the MVP and the first independently deliverable increment.
- **US2** depends on US1 artifacts and adds publication plus success notification.
- **US3** depends on the earlier stages existing so failure and partial-success behavior can be exercised end to end.

### Within Each User Story

- Contract and integration tests should be written before the corresponding implementation tasks.
- Shared adapters should be completed before orchestration changes that call them.
- Persistence updates should land before final orchestration wiring so status transitions can be asserted during tests.

### Parallel Opportunities

- `T003` and `T004` can run in parallel during setup.
- `T006`, `T007`, `T008`, and `T010` can run in parallel after `T005` starts the contract-alignment baseline.
- `T012` and `T013` can run in parallel for US1.
- `T014`, `T015`, and `T016` can run in parallel for US1 before `T017` and `T018`.
- `T020` and `T021` can run in parallel for US2.
- `T022` and `T023` can run in parallel for US2 before `T024`.
- `T026` and `T027` can run in parallel for US3.
- `T028`, `T029`, and `T030` can run in parallel for US3 before `T031`.
- `T032` and `T033` can run in parallel during polish.

---

## Parallel Example: User Story 1

```bash
# Write US1 validation first
Task: "T012 Add worker-input contract validation coverage in tests/contract/test_workflow_contracts.py"
Task: "T013 Add an accepted-route processing integration test in tests/integration/test_worker_flow.py"

# Build the core US1 adapters in parallel
Task: "T014 Refactor src/main.py to expose a reusable PDF-linking pipeline entrypoint in src/main.py"
Task: "T015 Implement the Magento SKU lookup adapter in src/worker/catalog_client.py"
Task: "T016 Implement S3 download and upload helpers for source PDFs and linked outputs in src/worker/storage_client.py"
```

---

## Parallel Example: User Story 2

```bash
# Validate the success-path contracts together
Task: "T020 Add publication and success-notification contract coverage in tests/contract/test_workflow_contracts.py"
Task: "T021 Add a publish-and-notify success integration test in tests/integration/test_worker_flow.py"

# Implement independent external-service adapters together
Task: "T022 Implement the flipbook publication client in src/worker/publish_client.py"
Task: "T023 Implement the stakeholder notification client for success outcomes in src/worker/notify_client.py"
```

---

## Parallel Example: User Story 3

```bash
# Cover failure contracts and flow scenarios together
Task: "T026 Add rejected-routing and partial-failure contract coverage in tests/contract/test_workflow_contracts.py"
Task: "T027 Add failure-path integration coverage for invalid PDFs, publication failures, and notification failures in tests/integration/test_worker_flow.py"

# Build failure-handling adapters together
Task: "T028 Extend the notification client for failure and partial-success payloads in src/worker/notify_client.py"
Task: "T029 Persist failure-stage details, duplicate-upload dedupe keys, and terminal summaries in src/worker/job_repository.py"
Task: "T030 Persist diagnostic artifacts and artifact-retention metadata in src/worker/storage_client.py"
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

Implement through **Phase 3 / US1** first. That yields the minimum valuable automation: valid uploaded PDFs are routed, processed with the existing linker, and written back to the correct output prefix.

---

## Notes

- Every task follows the required checklist format: checkbox, task ID, optional `[P]`, required story label for story phases, and explicit file path.
- Contract-alignment work is included early because the current schema files still encode logical bucket names differently from the routing design in the supporting docs.
- User Story 3 intentionally lands after US2 because its failure cases span publication and notification stages as well as core processing.