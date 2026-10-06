# Phase 9 — Verification evidence loop

Phase 9 extends the existing bounded code-test loop without replacing it.

## What it adds

- A privacy-safe local verification ledger for effectful actions.
- Exit code 0 from a completed command counts as direct execution evidence.
- File edits, connected-account writes, effectful MCP calls, and effectful phone actions are marked `needs_verification` until state is read back or a relevant test is run.
- Successful project test runs are recorded automatically as strong verification evidence.
- The agent receives an explicit instruction after an unverified write: verify state before claiming completion, and do not blindly repeat a failed action.
- `verification_status` and `verification_tail` expose only bounded metadata. They never store prompts, tool arguments, command output, project contents, tokens, or credentials.
- The original agent's existing two-round automatic test/fix loop remains the retry budget for project edits.

## Verification

CI runs unit tests for classification, privacy, project-check evidence, routing, the full connector/original-feature suite, package verification, and the Android APK build.
