# Task/context recovery regression repair

Base: `30015cfdfc858e76fce15c3ffc908f3cd62719a0` (Android build 370).
Trigger: one conversation builds an HTML game, switches to WhatsApp, then resumes.

The base already removed repeated model-driven automatic compaction, but the
assembled engine still had several independently reproduced failures:

| Failure | Cause | Repair |
| --- | --- | --- |
| A game follow-up loses its checkpoint after restart | The agent overwrote the task objective after supervisor creation; the supervisor only reused a checkpoint for literal continuation words | One identity writer; all classified follow-ups reuse the active checkpoint |
| Touch-control instructions disappear during compaction | Only the anchor and continuation words were retained | Preserve current-task user instructions, with a bounded history and a notice when older turns are omitted |
| Images and the end of long requests disappear on a task switch | Wrapped user content did not exactly match the truncated anchor; compaction substituted a short synthetic request | Persist exact input provenance and task ownership separately; preserve the actual text and image content |
| Legacy WhatsApp sessions inherit an HTML checklist | Old versions never associated their live checklist with a task | One-time migration discards unowned live checklist state; matching durable checkpoints, transcript and project files remain available |
| Agent-written checkpoints are not used on resume | The tool created an independent record while the supervisor held a different pin | Default checkpoint writes update the pinned task; supervisor retains their actual progress and next step |
| Repeated compaction loses the last tool result | The next reduction discarded its own prior bounded evidence | Retain structured, task-scoped evidence without replaying tool calls |

Actual user input and runtime reminders carry separate internal metadata. Provider
requests strip that metadata. Model-generated summaries are never task authority.

## Validation

- Six new cases failed against the base before implementation.
- Tests in `connectors/task_identity_tests.py` exercise the **assembled** agent,
  real session save/load, actual checkpoint tools, repeated compaction, images,
  long input, Arabic follow-ups, and real HTML file creation/editing under context
  pressure. Existing continuity, no-progress and supervisor tests remain enabled.
- The original engine suite and full connector suite remain required in Android CI.
- The signed APK must match `android-lite/signing-cert-sha256.txt` before delivery.

Current local results: **58 targeted tests passed; 146 upstream tests passed
(19 existing platform skips)**. The GitHub push was rejected by automatic
approval review, which requires explicit authorization for the repository
destination. No remote branch, CI build, APK or installable hot-update bundle
was produced. The bundle builder requires successful full CI, so its release
checks have not been bypassed.

Initial local wide testing exposed missing pytest in the isolated upstream test
environment, installed host skills affecting the empty-skill fixture, and a
process-identity probe failing after the Termux bridge fixture restart. These are
recorded rather than weakening those gates; clean GitHub CI is the release gate.
A controlled child-process check confirmed that this host hides the process
environment marker used by the bridge restart identity check, even though its
start time is visible.

## Limits

Task classification includes deterministic language heuristics; it is not a claim
of understanding every possible task transition. The repaired scenarios have
regressions. Real Samsung UI, Android permissions, and a live free-model service
are not exercised by offline scripted-model tests. No project files are deleted
by migration or compaction; no production update channel is changed by this branch.
