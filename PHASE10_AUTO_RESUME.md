# Phase 10 — Automatic durable resume

Phase 10 makes durable continuation less dependent on the selected model remembering to call a tool.

## Added

- Explicit continuation requests such as `continue`, `resume`, `كمل`, `تابع`, and `استأنف` automatically receive the latest active project checkpoint as bounded context.
- Ordinary unrelated requests do not receive checkpoint injection.
- The injected checkpoint is clearly marked as prior state to verify, not higher-priority instructions.
- Successful project checks automatically clear the active checkpoint blocker and store privacy-safe evidence such as `project_tests:passed exit=0`.
- Failed project checks automatically add an actionable blocker and next step to the latest active checkpoint.
- Verification synchronization never creates a task by itself; it only updates an already active checkpoint.
- No command text or command output is copied into the checkpoint by the automatic verification sync.

## Why

Phase 8 provided durable checkpoints and Phase 9 added verification evidence. Phase 10 connects them to the core turn lifecycle so a short “continue” request can recover verified project state even if the model does not independently remember to call `task_resume`.
