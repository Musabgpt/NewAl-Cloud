# MusabAI

Android coding assistant with persistent project memory, document tools, official OAuth/MCP connections, Termux execution and tested engine candidates.

This development line starts from successful Action 216 (`d8a270382c51e009148fc2ae034beb40788fdf6c`). It keeps that build's pinned Action 43 Python engine and byte-verified Action 125 native libraries.

## Using the app

- Start or open a project conversation, then use **Workspace / مساحة العمل** for Files, Memory and Improve.
- Files supports HTML, Markdown, PDF, ZIP and TXT import, creation, reading and export.
- Memory is local and project-scoped. Search its Arabic/English lessons and evidence, delete them or disable capture. Observed corrected tool calls can become lessons; this does not train model weights.
- Improve prepares a separate Python engine candidate. Packaged regression tests run before activation. Explicitly restart the engine after activation; Restore original selects the packaged engine. Android rechecks the code and app build before startup.
- Connections uses the deployed broker and native account vault. Current provider status and remaining registration requirements are in [REGISTRATION.md](connectors/hosted/REGISTRATION.md).
- The agent's `bash` commands run in the project and stream into the existing terminal pane as well as the conversation. Background servers use `bash(background=true)` and `job`. Shell permission checks and cancellation remain active; installing Termux is not required for the built-in shell.
- Each model request includes the actual terminal availability, permission mode and connected service tool counts, refreshed within existing conversations. The behavior profile requires relevant tools for execution and live account tasks, with build/test/repair guidance. This does not guarantee compliance by every model or install missing SDKs.
- **Connections → Add MCP server / إضافة خادم MCP** adds a remote Streamable HTTP endpoint to the current project, with an optional Bearer token. Test and add performs real initialization and paginated tool discovery before saving. Re-test and removal are supported; the running conversation refreshes its tools on its next request. Credentials live in a private app configuration file (mode 0600), outside project files and API listings. Custom browser OAuth and stdio installation are not part of this form; official OAuth services keep their existing connection cards.
- Android built-ins now include the existing Accessibility UI reader plus `screenshot`, `install_apk` (Android confirmation remains required), notification reading after the user enables Notification Access, and `automation_start/stop/list/replay`. `MusabTestBridge` exposes crash, test and ANR-report files for debug APKs; it does not pretend to read another app's Logcat. These are local phone capabilities and do not require wireless debugging or MCP.
- **Tasks / المهام** (⏰ in the workspace bar, the chat in plain words, `/schedule` or the `schedule_task` tool) runs work on its own at a time: once, daily, on chosen weekdays or every N minutes within set hours. Each task has one thread of its own (the model and permission mode of the thread it was made in). Every run continues it, and with each run comes a short journal of what the earlier runs did and the rule never to repeat it (the same post twice). When the thread grows past 20k characters, it keeps only its last run, and the journal keeps the rest. Runs wait while a thread of the user's is working, so they never slow the user down. Write in that thread to change the task ("make it 9pm"); the Tasks panel edits it too. Each run's result arrives as an Android notification. `/duet on` adds a morning brief (08:00) and a quiet check-in (every 3 hours, 08:00-22:00) that notifies only when something needs attention. Approvals the mode requires show Allow/Deny on the notification. Android's alarm wakes the engine at the task's time with the screen off. A connected service (Activepieces, Gmail…) comes before the screen: a task whose service is connected runs through its API with the screen off and the phone locked, and in lean mode its thread is offered those tools. Each task's screen setting is auto, yes or no (Tasks > Edit). A task that uses the screen runs alone and turns the screen on first. A PIN/pattern/fingerprint lock cannot be opened by any app, so such a task waits and asks the user to unlock. Times missed while the phone was off run once on return; Force stop cancels the alarms until the app is opened again.
- **Facebook Page** (Connections, the only card besides GitHub, Termux and Activepieces on the phone): posts go up through Facebook's Graph API (v26.0), with no app opening, the screen off and the phone locked. This works for Pages only, because Facebook lets no app post on a personal profile. The access token goes from the card straight to the Keystore vault (`FacebookPage.java`) and never passes through the engine or reaches the model. With the Meta app's ID and secret it is exchanged so the Page token does not expire, and the card says whether it lasts. The agent gets `facebook_page_post` and `facebook_page_recent` (the latest posts, so a new post says something new), and a scheduled task about Facebook runs through them. A Meta app still in development mode shows its posts to its own roles only: switch it to Live.
- **Phone by sight and in bursts** (ideas from Google's Artemis): `screen_tap` taps what the accessibility service cannot list (games, Flutter/Compose canvases, pictures, unlabeled icons). A vision model points at the target on a screenshot, then again on a magnified crop for the exact spot. `phone_steps` runs up to 12 phone actions back to back in one call, each checked, for controls that fade before the next model turn. They are not in lean mode's set (the phone's default), because every tool there goes with every request. Settings `"lean": false` offers them. `screen_tap` needs a vision-capable model.
- Model transport uses a real fallback pool. Kilo Auto Free is attempted without a key; OpenRouter, Groq, Cerebras, Gemini and Hugging Face free tiers are used when their own environment key is present. Overload, timeout, network and HTTP failures move to the next configured provider and the successful provider is recorded. Free-tier quotas and model names can change, so unconfigured entries are skipped instead of shown as connected.
- The built-in MCP catalog includes the official Microsoft Playwright MCP repository and the official MCP reference server templates (filesystem, memory and fetch). `/api/mcp-bundles` reports actual local runtime availability. Playwright/reference servers are started only where `node`/`npx` exists; no fake tools or hidden downloads are claimed. MusabAI's native files, memory and phone capabilities remain available when those runtimes are absent.

## Behavior profile

[agent_prompt.md](connectors/agent_prompt.md) adapts the user's uploaded `claude-code-cloud-fable-5.1.md` behavior instructions to MusabAI's actual tools and identity. The upload also contained another person's account/session context, repository directions and tool catalogs; those are not runtime configuration for this application. They are not included in the APK or this repository.

Source upload SHA-256: `a51e2376a001d5708b00762440d065e689a264b4de4f7f3ba55cd72f2b1ba863`.

The profile applies to default cloud/local conversations, including reopened conversations using the old built-in prompt. Messages and project instructions are preserved.

## Build and test

Root Gradle and `android-lite` build the same application: `dev.newal.code.lite.connectors`. Obsolete standalone chat source was removed and remains recoverable in Git history.

Run **MusabAI — Android** (`.github/workflows/android.yml`). It tests pinned agent integration, memory, Python/JavaScript/Java contracts and original engine features; then packages the verified native baseline and builds the APK. Download `MusabAI-Connectors` from the successful run.

Local UI tests: `npm ci --prefix connectors && npm test --prefix connectors`.
Memory tests: `python3 -m unittest discover -s desktop/autonomy -p 'test_*.py' -v`.
Set `NEWAL_UPSTREAM` to a Git checkout of pinned Musabgpt/NewAl source for agent integration tests.

The free default model endpoint can change availability and rate limits. Recalled memories enter the selected model's context like conversation text. Candidate checks execute with the application's OS permissions. Development signing and physical-phone acceptance are documented in [DEPLOYMENT.md](connectors/DEPLOYMENT.md).

See [applied recommendations and verification scope](connectors/EVOLUTION.md).

