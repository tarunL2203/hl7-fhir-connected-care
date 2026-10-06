# Firely analytics demonstration — October 6, 2026

## Step 6: present the result (approximately 3 minutes)
1. Open Firely-Analytics-Demo.pptx. Use View → Notes to read each script, or Presenter View when presenting.
   Expected: seven slides, each with a speaking script in its Notes pane.
2. Present slides 1–2: the purpose and actual internal-stage data route.
   Expected: your audience understands how the saved synthetic batch reaches Snowflake.
3. Present slides 3–5. Optionally show the corresponding CSV files, or run the matching REPORT block in firely-demo-reports.sql after the context block.
   Expected: Report 1 has 2 rows, Report 2 has 3 rows, Report 3 has 2 rows.
4. Present slides 6–7: reliability evidence and scaling plans.
   Expected: the audience understands what was checked and what comes next.

The SQL is the supplied demonstration file, preserved as uploaded. Its context commands appear twice; this is harmless. Report queries are SELECT-only. It assumes existing typed tables and the role used during this walkthrough. It does not rebuild tables or load data.

## Verified uploaded results
- Ravi: 2 observations, 1 appointment, valid birth date.
- Person02: 1 observation, 1 appointment, missing birth date.
- Glucose: Ravi 95 and 102 mg/dL on October 1, 2026 at 13:00 and 14:00 UTC; Person02 95 mg/dL on October 5 at 12:00 UTC. All final.
- Appointments: 2 and 1 qualifying glucose results respectively; both information_complete.

## Evidence scope
The three report CSVs are the actual uploaded outputs, inspected for this package. Earlier exported SQL predicate tests show 9 PASS results. The query-history export supports initial inserts of 2/3/2 and repeat Observation/Appointment inserts of zero. Patient repeat zero and the typed quality/link/payload checks were confirmed by the user during the walkthrough; they do not have separate exports in this package. Earlier application and AWS milestones are documented history, not fresh runtime checks performed while preparing the presentation.

This is a saved synthetic two-patient batch. The availability rule is bounded to two configured appointments and qualifying glucose observations within [appointment minus seven days, appointment). It does not represent clinical clearance or production readiness. Source JSON and batch provenance are retained in the existing typed tables. Serial repeat behavior is demonstrated; concurrent uniqueness is not established.

## Next phase
Automate direct S3-to-Snowflake ingestion after resolving AWS role authorization, expand batches and resources, and add scheduling, monitoring, and least-privilege access. The current completed analytics route uses an internal stage. No AWS policy or billing changes were made during the bounded troubleshooting session. The exact cause of the cross-account AssumeRole denial remains unresolved; FREE/ACTIVE account-plan metadata does not establish causation. Warehouse final state was not verified; automatic suspension was configured earlier.
