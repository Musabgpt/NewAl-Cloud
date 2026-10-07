# Phase 10 — validation in progress

Scope: Phase 10 only. Phase 11 has not started. This is an evidence ledger,
not final acceptance. Samsung results below were supplied by the project owner;
Linux/CI checks cannot replace the remaining phone tests.

## Follow-up: owner rejected provider/add-on acceptance

New Samsung screenshots show an app-shell uv/uvx probe ending in exit 127 and
provider cooldown, with no completed dependency installation. #334 therefore
does not establish acceptance for those tasks.

The follow-up fixes route environment-only bash version probes to Termux, add
`dependency_install` (official `pkg install uv`, then actual uv and uvx version
checks), and bootstrap uv before Browser Use/Docling MCP verification. Installing
uv alone never marks either MCP installed. Native Python dependencies may still
reject Android and must return their actual errors.
Persisted conversations also refresh their built-in tool schemas after upgrade;
previously they could retain only the pre-upgrade tools despite the new prompt.

The provider router previously rejected every alternative model sharing Kilo's
base URL. It now discovers zero-price, tools-capable routes from Kilo's real
catalog. Model-specific upstream capacity failures may select another model;
account/gateway rate limits block all sibling models for the cooldown. These are
alternative model backends on the same gateway, not independent gateway services.
An anonymous live API probe returned a real tool call from StepFun 3.7 Flash.
Phone completion with the new build remains unverified.

## Established Samsung evidence (owner report)

- Action #314: persistent-signing baseline, installed and launched.
- Action #318: installed over #314 without uninstall; launched successfully.
- Termux connection, RUN_COMMAND bootstrap, authenticated localhost bridge,
  command probing, and the Termux test button succeeded.
- MCP stdio reached Termux; stderr exposed the previous npx binary-resolution error.
- Owner screenshots from the session show packaged v332, connected Termux,
  Playwright with 25 verified tools, and Memory with 9 verified tools. Both MCPs
  are shown stopped, which is the expected state after enable-time verification.
  This supports successful managed installation and discovery on Samsung; it
  does not establish browser launch, Memory write/read, or reconnect acceptance.
- The browser conversation shows a `playwright.browser_tabs` invocation followed
  by provider rate limiting/cooldown. Its collapsed result does not prove a
  completed browser task.
- Optional external Android MCP fails loading `sharp` on android-arm64. Other
  screenshots show missing uvx/obu/server binaries and owner-side Google service
  setup. These are explicit dependency/configuration blockers, not evidence of
  a broken Termux connection.

## Current correction

The managed install's initial `test -f` legitimately exits 1 for a missing entry.
Bridge protocol v2 incorrectly returned `ok=false`, and the runtime raised
`BridgeError` before npm could run. Protocol v3 returns `ok=true` for handled
command outcomes, including nonzero exits and timeouts. Callers inspect `status`,
`exit_code`, `command_success`, `stdout`, and `stderr`. Authentication, invalid
requests, transport errors, and bridge-operation errors still raise. The existing
health/version check automatically replaces a running v2 bridge through RUN_COMMAND.

The installer accepts only completed exit 0 as an existing/verified entry,
completed exit 1 as a missing entry, and explicit exit 0 from npm setup. Missing
exit codes or timeouts cannot become success. No timeout values were increased.

A real npm installation exposed another pre-existing blocker: Memory and Filesystem
`0.6.3` do not exist in the npm registry. They now pin the nearest published version,
`0.6.2`; Playwright remains `0.0.83` and Android MCP remains `1.14.4`. Termux starts
npm bundles with `node` and their managed entry path, without runtime npx.
Filesystem remains intentionally unavailable for app-private projects.

Enabling still persists configuration only after real initialize,
notifications/initialized, and tools/list complete successfully.

## Host evidence and reproducible CI checks

- 49 focused runtime/bridge/MCP regression tests passed locally, including actual
  authenticated HTTP + shell nonzero-exit handling, initial missing-entry flow,
  retained auth/bridge failures, timeout results, and v2 replacement.
- `connectors/phase10_mcp_validation.py` installed the real pinned Memory and
  Playwright npm packages into fresh temporary directories and ran them through
  the actual HTTP bridge and direct-node stdio path on Linux.
- Memory: initialize + initialized + tools/list returned 9 tools; create_entities
  succeeded and read_graph retained its entity after stop/start.
- Playwright: initialize + initialized + tools/list returned 25 tools; stop/start
  rediscovered the tools. Browser launch was NOT tested by this host check.
- The Android workflow runs this integration script after its regression suite.
  Android discovery and HOME are substituted for this Linux harness; npm, HTTP,
  shell, JSON-RPC and MCP servers are real. This is NOT Samsung evidence.
- CI success, release signing verification, and artifact identity must be checked
  on the workflow run for the exact new commit before recommending its APK.

## Required Samsung evidence before closing Phase 10

Use only the successful persistent-signed build identified in the handoff. Install
over the existing app. All operations below use the app; no manual Termux commands
are required. Record the build number and exact UI result/error for each operation.

1. On the new build, ask the agent for a Memory and browser task. Confirm it uses
   `capability_ensure` where needed, starts the MCP and verifies live discovery.
   Initial v332 discovery is evidenced above; new automatic preparation and
   actual task completion still require phone results.
2. Run a real Memory write/read task and a Playwright browser task. Check results,
   then stop/start/reconnect each MCP and repeat. Playwright must actually launch
   Termux Chromium; discovery alone is insufficient browser acceptance.
3. Disconnect/reconnect during a real task. Confirm honest failure/pause state and
   successful recovery without duplicate or fabricated results.
4. Restart the app and then the phone. Check persisted configuration, correct live
   process state, Memory data, and successful MCP restart/reconnect.
5. Exercise a verified hot update and rollback on Samsung; record active revision
   before update, after update, and after rollback.
6. Run a long task; stop, resume from checkpoint, and exercise watchdog recovery.
   Verify durable checkpoint/state and absence of duplicate side effects.
7. Exercise crash/recovery; collect the app's crash report and verify restored task
   and MCP state. Final acceptance remains open until these results are recorded.

Samsung managed-install/discovery evidence is recorded above. Phase 10 remains
open for the remaining real task, restart, recovery and update acceptance.

## Automatic preparation, recovery and update changes

The agent now has tools for compatible bundled MCP preparation, packaged plugin
installation, evidence-backed project skill creation, and restricted HTTPS MCP
Registry discovery/installation. MCP configuration still requires successful
initialize/initialized/tools/list; first-install errors show `health_failed`.

Provider recovery retries only an uncommitted model request, respecting cooldown,
capabilities, Stop and a bounded budget. Downloaded, explicitly capable configured
local models can be tried as a last resort. Tests of this local fallback mock the
model runtime; no real GGUF inference is claimed. Unmet goals, exhausted step
budgets, breaker stops and failed verification remain resumable, not complete.

Successful persistent-signed Phase 10 CI builds publish immutable versioned engine
assets before updating the GitHub channel pointer. A packaged background worker
stages and verifies compatible updates, waits for idle and requests the existing
Android engine restart through the WebView. Native startup health/rollback remains
the final acceptance gate. Native APK changes still require Android confirmation.
See `MUSABAI_RUNTIME_AND_AI_ROUTER_FIX.md` for the plan comparison and limitations.
