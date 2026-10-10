# Successful action termination

Reported after Android 371: a single request to open WhatsApp repeatedly invoked
the phone tool and automatically compacted the conversation, despite a successful
launch. The previous task-isolation repair did not cover this successful-action
loop.

## Reproduced causes

Four regression tests failed against the delivered engine before this change:

1. A provider repeatedly requesting `phone(open_app)` ran the action until the
   step budget was spent. Successful phone calls bypassed the original breaker.
2. Automatic compaction dropped actual assistant/tool exchanges and ended with
   the original user command, inviting another execution.
3. Native `ok: false` was buried inside metadata and emitted as a successful tool
   completion.
4. Complex requests repeatedly replayed their successful first action instead
   of performing the remaining work.

Phone observations also reset the compaction epoch as if they changed state.
The supervisor could reopen a task just closed by `task_complete` by writing a
generic checkpoint for that tool's completion event.

## Repair and boundaries

- Keep up to two complete, bounded assistant/tool exchanges in chronological
  order after the latest real user request. Never fabricate results or retain
  orphan tool responses. Summaries are not instructions to restart.
- Persist a scoped successful-action receipt independently of model context.
  Cache exact successful stable-target actions; a different state-changing
  action invalidates the receipt. UI coordinates/gestures are not cached by
  arguments alone. A new explicit user request starts a new execution scope.
- A strictly matched single-app launch request ends on the native successful
  launch receipt. Compound, wrong-target, failed, and pending requests do not
  qualify. A pure continuation preserves the completed result after restart.
- Complex work can continue with different actions and normal verification.
  If a provider insists on replaying the same successful action twice, end the
  loop without executing the action again, preserve the checkpoint, and report
  that the rest of the task remains unverified.
- Respect explicit task completion without reopening it. Stop hooks, project
  verification, and goal checks remain part of the ordinary completion path.
- Surface native failure as failure; phone inspections are not state changes.

The integration tests execute the assembled agent, real phone-tool adapter,
session persistence, checkpoint store, and compaction. Provider and Android
responses are scripted so an adversarial repeating provider is reproducible.
These tests do not constitute testing the user's Samsung phone or live provider.

Local validation: 65 initial affected checks passed. The expanded suite ran 104
checks; its only failure was the existing 16,000-character prompt ceiling. The
prompt was shortened without changing that ceiling and all three prompt tests
passed. Final repeat-count/termination checks passed. The original engine suite
passed 146 tests with 19 existing platform skips. Clean Android CI is still
required before delivery.

## Verified delivery

Android [build 372](https://github.com/Musabgpt/NewAl-Cloud/actions/runs/38042791100)
completed successfully, including all required CI gates. Source commit:
`c3cfcb27512bbdefed5e0a057f00a922b8bad242`; tree
`17527f15a6360e3d1f5ab70f6ea206caff2b26a6` exactly matched the local tested tree.
Branch: `fix/successful-action-stop`. Artifact: `11665939422`.

- Delivered APK: `MusabAI-372.apk`, 40,110,206 bytes.
- APK SHA-256: `e94cfaa56122812398203cc4e0c8ca3ac0dca91ff1a369b1f5e55a552a6087d2`.
- Artifact ZIP SHA-256: `ddf607bbfb8fad9673762d5b40acfbbc6808258e385a57fb3f9db9fce3fa0172`.
- Independent Google apksig validation passed, signature schemes v2 and v3.
- Certificate SHA-256: `6af53b6b3e2574eed16aaae7ce92ade3dcde702a74af1dfae994c9c87609cbb6`,
  matching the approved signing identity.
- Eleven engine files inside the actual APK match the tested sources byte for
  byte. The packaged original-feature gate also passed.
- The hot-update bundle identifies this same commit and run; all 158 listed file
  hashes verified. No production update channel change or merge to main occurred.

The native-phone responses and repeating provider were simulated in the agent
integration tests. Actual Samsung UI and live provider execution remain untested
here; the APK, build gates, packaged source and signature were independently checked.
