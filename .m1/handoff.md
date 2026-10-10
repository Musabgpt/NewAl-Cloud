# Completed recovery point

Goal: repair the game/WhatsApp task contamination and compaction-loop failure.
Base: Android build 370, commit 30015cf. The user explicitly authorized immediate
publication; historical approval and Git transport blockers are resolved.

Published branch: fix/durable-task-boundaries in Musabgpt/NewAl-Cloud.
Tested source commit: bf327befcc4cd6c05033346e4f292ce32958b15d.
Its tree exactly matches the locally tested repair.

Verified locally: six regressions reproduced on the base; 58 targeted tests pass;
146 original-engine tests pass (19 existing platform skips). The two broad local
fixture failures were environmental. GitHub Android CI run 38013030424, build 371,
completed all gates successfully, including release signing.

Downloaded artifact 11654466973. Verified archive digest, APK digest, v2/v3 APK
signatures, approved signing certificate, seven packaged repaired engine files,
original packaged features, and all 156 hot-update manifest file hashes.

Deliverable: /workspace/scratch/d607775b5ad3/release-371/MusabAI-371.apk
APK SHA-256: 27fc1f4fb954608c283b216eaca84abd6b94332e32e9c73d00458854e6ee3b6c
Signer SHA-256: 6af53b6b3e2574eed16aaae7ce92ade3dcde702a74af1dfae994c9c87609cbb6
Persistent deliverable identity: libfile_d155b899b66c81919b3cc78492a0cd3c.

Changed components: task identity, automatic context retention, supervisor pinning,
checkpoint default target, task API active pin, assembly patch and regressions.
No Android native code, signing identity, project files or production update
channel changed. No merge to main was performed.

No remaining build or delivery blocker. Actual Samsung UI and live-provider
execution were not tested in this environment.
