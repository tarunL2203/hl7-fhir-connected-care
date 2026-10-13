# Milestone reports

Contemporaneous working reports, written during the build to record exactly what was run, what passed and what was still unproven. They were drafted with AI assistants, which is why they describe the project owner in the third person ("the user") and are careful to separate verified results from expectations. They are kept unedited, apart from replacing account identifiers and addresses with placeholders.

| Report | Milestone |
|---|---|
| [2026-10-03 reviewer milestone](2026-10-03-reviewer-milestone.md) | Live authenticated reviewer demonstration: 15/15 checks |
| [2026-10-03 repeatable verification](2026-10-03-repeatable-verification.md) | Preflight, start, smoke and reviewer tooling; 34/34 offline checks |
| [2026-10-04 connection check](2026-10-04-connection-check.md) | Recovery after AWS session expiry and the Firely evaluation uptime limit |
| [2026-10-04 S3 → Snowflake RAW](2026-10-04-s3-snowflake-raw.md) | Export and S3 landing; the external stage blocked at `sts:AssumeRole` |
| [2026-10-05 connection check](2026-10-05-connection-check.md) | Infrastructure and smoke checks before the internal-stage load |
| [2026-10-05 Snowflake internal stage](2026-10-05-snowflake-internal-stage.md) | Internal-stage RAW load, reconciliation and repeat load |
| [2026-10-06 typed analytics](2026-10-06-typed-analytics.md) | Typed tables, three reports, rule tests and query history |

For the edited, end-to-end account, read [docs/project-history.md](../../docs/project-history.md).
