# Successful-action loop repair: publication pending

Current branch: fix/successful-action-stop. Base: e721091 (verified build 371).
User reported repeated WhatsApp launch after success; four regression cases failed
against the delivered 371 engine. Publication and Android delivery remain authorized.

Implemented: complete call/result pairs through compaction; durable action receipts;
strict single-app launch completion; bounded suppression of successful-action replay;
explicit repeat counts; native failure propagation; phone observations no longer
reset compaction progress; supervisor respects task_complete. Verification, goal and
stop-hook gates remain; terminal state persists only after those gates succeed.

Evidence: 65 initial focused tests passed. Final expanded suite ran 104 cases with
one prompt-budget failure; the prompt was shortened and all 3 prompt tests passed.
The final repeat-budget and completion checks passed. Original engine: 146 tests,
19 existing platform skips. Full clean Android CI remains the release gate.

Sources are under connectors/ plus .github/workflows/android.yml. Assembled test
engine: /workspace/scratch/d607775b5ad3/validation-success-final/desktop/newal_code.
Logs: /workspace/scratch/d607775b5ad3/evidence/success-loop-*.log.
Report: SUCCESSFUL_ACTION_COMPLETION.md. No secrets, signing identity or native
Android code changed. No main merge or production update channel publication.

Next: commit/publish the tested tree; follow its Android build; download and verify
actual APK and approved certificate, then deliver it. Live provider and actual
Samsung UI testing have not been performed here.
