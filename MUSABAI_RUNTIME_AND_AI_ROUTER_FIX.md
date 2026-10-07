# MusabAI Phase 10 — implementation and acceptance evidence

Scope: `phase10/final-validation` only. This report compares the owner's uploaded
`MUSABAI_10_PHASE_PLAN.md` with the applied code and available evidence. It does not
close Phase 10 or start Phase 11. CI and Linux checks are distinguished from the
Samsung screenshots and owner reports.

## Comparison with the ten-phase plan

| Plan area | Applied implementation | Evidence / remaining acceptance |
| --- | --- | --- |
| Baseline and signing | Pinned Action 43 engine and Action 125 native baseline; persistent certificate gate | Owner: #314 installed; #318 upgraded without uninstall. #332 CI succeeded. New build must pass the same gate. |
| Capability router | `provider_pool.py` request requirements, provider capability checks | Regression checks cover text, vision rejection, tools and compatible fallback; new phone behavior remains open. |
| Free pool and health | Independent adapters, credentials filter, cooldown/Retry-After, bounded request recovery, configured downloaded local last resort | Contract tests cover rate-limit recovery, Stop, no retry after partial output, and mocked local connection. Actual alternative provider/local inference on Samsung remains open. |
| Supervisor | Existing heartbeat/watchdog/checkpoints plus correct unfinished-task outcomes | Budget, unmet goal and failing-verification integration tests exercise `Agent.run`; phone long-task, stop/resume and recovery remain open. |
| Runtime | Android native, authenticated Termux and configured remote routes | Owner proved Termux connection/probing. Actual shell nonzero results and transport errors have separate tests. |
| Termux bridge | v3 separates command outcome from transport and retains authentication | Real localhost HTTP/shell checks pass on Linux; Samsung managed discovery screenshots support the corrected installation path. |
| MCP preparation | Managed direct-node pinned installs, real initialize/initialized/tools/list, new agent provisioning tools | Real npm Memory/Playwright integration on Linux; Samsung shows 9/25 verified tools. Browser execution, Memory task and reconnect still open. |
| Hub state | Live lifecycle states, concrete errors; first installation error is `health_failed` | Screenshot sharp failure was diagnosed honestly; no fake Android MCP support is introduced. |
| Self-update | Existing staging/verification/health/rollback, new automatic GitHub channel and idle activation | Contract tests exercise integrity rejection, busy task deferral, restart selection and rollback blocking. Actual phone automatic update/rollback remains open. |
| Final acceptance | Real APK workflow and this report plus `PHASE10_ACCEPTANCE.md` | Phase 10 cannot close from CI alone. Remaining Samsung tests are listed in the ledger. |

## Root causes and changes

1. **Missing npm entry prevented installation.** `test -f` exited 1, bridge v2
   reported `ok=false`, and runtime raised a transport error. The earlier #332 fix
   uses bridge v3 with handled command results (`status`, `exit_code`,
   `command_success`, stdout/stderr); auth/transport errors still raise. The npm
   installer distinguishes missing entry, successful installation and timeout.
   Memory/Filesystem pin published 0.6.2; 0.6.3 did not exist. Runtime npx is not
   reinstated.
2. **One usable free tools provider was exhausted.** Screenshots show
   `kilo-auto/free` rate limiting then cooling down. Anonymous AI Horde text
   generation cannot replace a tools-capable request. The runtime now preserves
   prior tool results, tries compatible credentialed alternatives, tries an
   already downloaded configured capable local model, and retries only the model
   request after cooldown within a bounded budget. Stop interrupts the wait.
   Partial streamed output is never replayed. User-facing aggregate failures are
   Arabic; sanitized raw provider details remain in diagnostics. This cannot
   guarantee unlimited free quota or invent provider credentials.
3. **Provisioning was available primarily through the UI.** `automation.py`
   exposes `capability_catalog`, `capability_ensure`, `plugin_install`,
   `skill_create`, and MCP Registry discovery/installation to the agent. Compatible
   npm MCP installation and initialization happen inside the app. A newly created
   skill is callable in the current session. Plugins are restricted to the shipped
   marketplace; Registry auto-install supports verified anonymous literal HTTPS
   remotes, not arbitrary package commands. Skills contain instructions; they do
   not train model weights. Dependencies or account consent cannot be fabricated.
4. **Bounded repair could be saved as completion.** Exhausted step budgets, open
   circuit breakers, unmet goals and still-failing project verification now retain
   an unfinished checkpoint and blocker. Repairs remain bounded and evidence
   driven; the app does not run endlessly or declare a failed goal successful.
5. **Verified improvements required manual activation, and GitHub artifacts had
   no automatic feed.** `self_evolve_activate` queues only unchanged verified
   candidates. Successful signed Phase 10 CI publishes versioned engine/APK assets
   before a channel JSON pointer. `auto_update.py` checks exact repository/branch,
   version, source commit, archive hash and native compatibility fingerprint;
   performs packaged verification; waits for active tasks; and selects the engine.
   `automatic_updates.js` invokes the existing Android restart bridge. Startup
   health either confirms the revision or restores the previous one. Invalid
   releases are blocked; interrupted downloads have at most three attempts. The
   Improve panel displays actual automatic state and errors.

## Changed files and architecture

- Runtime correction from #332: `runtime_manager.py`, `termux_bridge_server.py`,
  managed npm setup/tests and bridge regression tests.
- Agent preparation: `automation.py`, `automation_tests.py`, `agent_prompt.md`,
  `agent_policy.py`, `mcp_bundles.py`, `mcp_bundles_tests.py`.
- Recovery: `provider_pool.py`, `provider_pool_tests.py`,
  `task_supervisor_tests.py`; `apply.py` applies changes to the pinned original
  agent/model/service/server instead of replacing the original engine.
- Updating: `auto_update.py`, `auto_update_tests.py`, `automatic_updates.js`,
  `evolution.py`, `workspace.js` and UI tests, `publish_update_channel.py`,
  `test_update_publication.py`, `verify_package.py`, and the Android workflow.
- Real integration: `phase10_mcp_validation.py` now invokes the agent-accessible
  Memory provisioning path before real MCP write/read and stop/start checks.

The update worker runs only in the packaged app, polls the channel roughly every
60 seconds, and activates only when no task is running/reserved. Python changes
need an engine restart; the WebView requests it after verified idle activation.
UI-only allowed resources use the existing hot-update mechanism. User model
responses still determine repair choices; this is a stronger execution harness,
not a claim to reproduce Codex/Claude model quality.

## Verification and limits

Tests reproduced missing automatic APIs, incorrect unfinished-task completion,
and the inaccessible newly created skill before their fixes. The applied engine's
trusted regression suite, UI tests and signing/publication contracts are run
locally; the workflow repeats regression checks, real npm/MCP checks, package
validation, Android unit tests, APK build and certificate verification. Exact
Action/commit/artifact and publication success are reported in the handoff only
after the new workflow finishes. No new CI result is assumed in this file.

The real Linux harness returned Memory 9 tools and Playwright 25 tools, exercised
Memory write/read persistence and stop/start, and successfully invoked
`capability_ensure` with real npm installation. It does not launch Termux Chromium
or substitute for Samsung tests. Local-model fallback uses a mocked model connection
in regression checks; actual local inference has not been demonstrated.

Samsung screenshots show installed/discovered Memory/Playwright, stopped after
verification, and Termux connected. They do not prove completed browser/Memory
tasks, automatic GitHub update/rollback, long-task recovery or crash recovery.
Filesystem remains intentionally blocked at an app-private root. Optional
external Android MCP's sharp dependency remains unsupported on this tested
Android runtime; the native phone tool is a separate working route. Browser Use,
Docling, open-browser-use and GitHub MCP need compatible dependencies/configuration;
Google services need owner-side service enablement/OAuth. None is marked successful
by these changes without verification.

A first installation of the new successful APK is required to obtain this updater.
Following compatible published **engine** updates can apply automatically. A
native APK change still needs Android's installation confirmation on an ordinary
Samsung phone. The channel does not automatically publish the phone's generated
code to GitHub or obtain GitHub credentials; local verified self-improvements can
activate locally, and CI-published repository changes can download automatically.
