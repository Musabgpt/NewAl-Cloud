# Source work report — 13 October 2026

## Repository update
- Repository: `Musabgpt/NewAl-Cloud`
- Base branch: `feat/claude-harness-core`
- Working branch: `fix/code-intel-outline-regressions`
- Source commit recorded in the supplied archive: `9ef6aceab54cf8ea5200abc7bd5dde143b586b25`

## Changes in this branch

1. Fixed Python code-outline traversal so nested classes and functions are included with qualified names.
2. Fixed invalid Python handling: no misleading partial outline is returned when parsing fails.
3. Extended code outline recognition to common Java/Kotlin/C#/C/C++ method declarations.
4. Added eight regression tests for nested and invalid Python, TypeScript declarations, Java methods, bounded project scanning, ignored directories, shell syntax diagnostics, and optional linters.
5. Updated the connector packaging step to include the regression tests in the engine package.
6. Added the regression suite to the Android CI test command.

## Local verification recorded from the source work

- `py_compile` for changed Python files: passed.
- Isolated code-intelligence harness: 8/8 tests passed.
- `compileall` for `connectors`, `desktop/autonomy`, and `tools`: passed.
- Node syntax checks for `ui.js`, `workspace.js`, and `stream_ui.js`: passed.
- Android XML parse: 9/9 passed.
- JSON parse: 4/4 passed.
- Signing/publication Python tests: 8 passed.

## Remaining verification limits

- The full connector suite depends on pinned engine source from `Musabgpt/NewAl`, which is not included in the uploaded archive.
- `npm ci` did not complete in the original work environment; tests requiring `jsdom` remain unverified there.
- No local Gradle executable or Android SDK was available, so no local APK build or Android JUnit run is claimed.
- No physical Android / Termux test is claimed.
- These changes are on a working branch and need CI review before merge.
