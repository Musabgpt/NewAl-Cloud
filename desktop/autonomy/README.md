# NewAl-Cloud Autonomous Layer

This layer extends the exact Action #43 runtime; it does not replace the agent loop.

## Guarantees
- Persistent SQLite/WAL memory survives app restarts.
- Failures and successful turns become durable evidence.
- Recalled lessons are emitted as structured events without bloating the fixed system prompt.
- Self-evolution uses a clean Git working tree, creates a candidate branch, runs checks, and refuses unsafe overwrite.
- No force-push and no destructive in-place promotion.

## Self-evolution
Set NEWAL_SELF_REPO to the checked-out NewAl source repository. The agent can then use the self-evolution controller after making changes, which verifies the candidate before any later promotion.

The production APK remains recoverable because APK generation is still performed by verified GitHub Actions.
