# MusabAI V4 prompt experiment (not deployed)

Experimental branch: `experiment/v4-evidence-gates`. Base commit: `5a22c00c1adc6ce0e26565f1593eb3f43446bd20` (Phase 9 known-good release).

- The default packaged system prompt is UNCHANGED.
- The new instruction supplement is staged at `connectors/agent_prompt_v4.md`, and only loads when `MUSABAI_PROMPT_EXPERIMENT=v4` is set in the engine process.
- No signing identity, APK package, permission controls, OAuth setup, provider credentials or app UI is altered.
- The connector packaging step copies the file alongside `agent_prompt.md`.
- Prompt integration tests check normal and opt-in behavior, local/phone constraints and compiled prompt length below 16k. Existing CI still runs Android/package, runtime and regression tests.
- Tests of prompt wiring, code compilation and routing are not live model A/B results. Do not promote or merge based solely on green CI.

## Next evaluation gate
Test baseline versus V4 on the same pinned serving model, tool catalog, permission mode, fixed tasks and fresh workspace snapshots. Collect real tool traces and independently checked file/build/UI outcomes. Count false-success claims, regressions, security violations, recovery success and cost. Do not use fabricated traces or live destructive actions. Use a fresh held-out set before adopting the prompt. Keep baseline until improvement is demonstrated.

## Rollback
Unset `MUSABAI_PROMPT_EXPERIMENT`, or simply keep the release branch unchanged. This branch is for evaluation only.
