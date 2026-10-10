# Current recovery point

Goal: repair the game/WhatsApp task contamination and compaction-loop failure.
Base: Android build 370, commit 30015cf.
Branch: fix/durable-task-boundaries.

Verified locally: six regressions reproduced on the base; 58 focused checks now
pass, including real HTML write/edit under context pressure and session reload;
146 original-engine checks pass (19 existing platform skips).

The wider 331-test local run reported two failures: host skills invalidate an
empty-skill assumption, and the Termux bridge fixture's process-identity check
returns unknown after restart. Do not weaken these checks. Clean GitHub CI must
pass before calling the Android artifact verified.

Changed components: task identity, automatic context retention, supervisor pinning,
checkpoint default target, task API active pin, assembly patch and regressions.
No Android native code, signing identity, project files or production update
channel changed.

Code commit: fa25f4d064aae1eb2e82db0636b5e254990c864e.

Blocked operation: push the new branch to Musabgpt/NewAl-Cloud. Automatic approval
review rejected the push because explicit authorization for that destination was
missing. Remote branch search confirmed it is absent. Do not retry through another
tool or create a misleading hot-update manifest claiming CI passed.

Next action: request explicit permission to push fix/durable-task-boundaries to
Musabgpt/NewAl-Cloud and start Android CI. On approval, recover state, verify the
local commit and remote branch, push, inspect CI, verify signing and deliver APK.
Samsung and live-provider execution remain untested in this environment.
