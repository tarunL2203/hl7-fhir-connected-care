# Daily startup, pause and shutdown runbook

Clinical Data Reliability and Visit Readiness — updated October 5, 2026.

Use this file to resume existing work without rebuilding or repeating completed setup. Commands are for the original Mac, using Terminal/zsh. Examples of output are illustrative; timestamps, process IDs and session ARNs change. Run each step only after its preceding check succeeds. No credentials belong in chat or screenshots.

## 1. Choose today's work before starting services

| Today's work | What you need | What you can skip |
|---|---|---|
| Snowflake typed tables/reports over the saved RAW data | Existing Snowflake browser login and FIRELY_DEMO_WH | Docker, AWS renewal, RDS/viewer login and new export |
| Reviewer demonstration, fresh FHIR reads or document retrieval | Docker, AWS session, available RDS, allowed current IP, Firely/Auth/viewer | New Snowflake uploads/object creation |
| Read/edit saved code or reports | Project files and existing Python environment as needed | Cloud/service startup unless running live tests |

Current accepted RAW source: `CHATGPT_LAB.FIRELY_RAW_5DD08717.FHIR_RESOURCE_INTERNAL`.
Expected saved batch: 2 Patient + 3 Observation + 2 Appointment = 7 records.
The direct AWS S3 integration remains blocked. Do not make repairing it a daily prerequisite for internal-stage analytics.

## 2. Start of day — common first step

Open Terminal and enter:

```sh
cd ~/firely-learning
pwd
```

Expected:

```text
~/firely-learning
```

Read the most recent milestone report and continuation notes before deciding what to execute:

- `CURRENT-PROGRESS-2026-10-05.md`
- `LLM-CONTINUATION-INSTRUCTIONS-2026-10-05.md`
- `SNOWFLAKE-INTERNAL-RAW-MILESTONE-2026-10-05.md`
- Any newer report created since these files.

Use the installed executable `document-tools-venv/bin/python`. No daily package installation, virtual-environment recreation, migration, image build or fixture loading is needed.

## 3. Fast path — Snowflake analytics only

### 3A. Open the existing account

Open https://<SNOWFLAKE_ACCOUNT>.snowflakecomputing.com/ and sign in as your existing user if needed. Complete MFA yourself. Use an existing authorized role; do not add grants to make a routine session work.

In a project worksheet, run one statement at a time:

```sql
SELECT CURRENT_ACCOUNT(), CURRENT_USER(), CURRENT_ROLE();
```

Expected account locator: `<SNOWFLAKE_LOCATOR>`; user: `<SNOWFLAKE_USER>`. The role depends on your selection. Existing setup used `ACCOUNTADMIN`; do not assume a less privileged role has object access. A different account/user means stop and choose the correct account.

```sql
SHOW WAREHOUSES LIKE 'FIRELY_DEMO_WH';
```

Expected: one row for `FIRELY_DEMO_WH`, size `X-Small`, auto_suspend `60`, auto_resume `true`. State may be `SUSPENDED` or `STARTED`; suspended is healthy when idle.

```sql
USE WAREHOUSE FIRELY_DEMO_WH;
```

Expected: `Statement executed successfully.` Selecting a warehouse does not recreate it. A data query can resume it and consume credits.

```sql
SELECT CURRENT_WAREHOUSE() AS warehouse, resource_type,
       COUNT(*) AS records, COUNT(DISTINCT resource_id) AS distinct_ids
FROM CHATGPT_LAB.FIRELY_RAW_5DD08717.FHIR_RESOURCE_INTERNAL
WHERE batch_id = 'synthetic-20261004T225801Z-5dd08717'
GROUP BY resource_type ORDER BY resource_type;
```

Expected:

| WAREHOUSE | RESOURCE_TYPE | RECORDS | DISTINCT_IDS |
|---|---|---:|---:|
| FIRELY_DEMO_WH | Appointment | 2 | 2 |
| FIRELY_DEMO_WH | Observation | 3 | 3 |
| FIRELY_DEMO_WH | Patient | 2 | 2 |

You are ready for analytical work. Do not upload the batch again, rerun `00-setup.sql`, create a replacement warehouse, truncate RAW or use FORCE. If counts differ, inspect changes rather than fixing them by deletion.

Use the internal table explicitly. `FHIR_RESOURCE` and `FHIR_STAGE` belong to the preserved blocked external-S3 route; they are not the accepted alternative destination.

## 4. Full path — reviewer, FHIR and private documents

### 4A. Check Docker before launching it

```sh
docker context show
docker info --format '{{.ServerVersion}}'
```

Expected context: `desktop-linux`; second command returns a Docker server version.

If Docker is not running, launch the existing Desktop installation:

```sh
open -a Docker
```

Wait until Docker Desktop says the engine is running, then rerun the two checks. If the selected context is wrong and the expected context exists:

```sh
docker context ls
docker context use desktop-linux
```

Expected: `desktop-linux` selected. Do not invent socket paths or reinstall Docker. If an LLM tool reports permission denied but your Mac Terminal works, that may be its sandbox access restriction; the assistant must request the appropriate tool access rather than rebuild the environment.

Inventory existing containers:

```sh
docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
```

Expected to find:

- `firely-learning-aws`
- `firely-learning-auth`
- `firely-learning-mailpit`

They may be stopped at the start of day. This is normal. Keep the stopped `firely-learning-auth-before-ui-20261003T191031Z` rollback container stopped; it shares active Auth storage. No `docker run`, image rebuild, compose recreation or volume deletion is required.

### 4B. Verify the existing AWS login

```sh
aws sts get-caller-identity --profile firely-learning \
  --query '{Account:Account,Arn:Arn}' --output json --no-cli-pager
```

Expected account: `<AWS_ACCOUNT_ID>`; ARN contains `assumed-role/AccountFullAccessRole/` with a variable session suffix. This command prints identity, not credentials.

Only if expired or login is required:

```sh
aws login --profile firely-learning
```

Complete the opened browser sign-in, then repeat the identity command. Expected: renewed credentials and successful identity result. This profile uses AWS CLI login-session authentication; do not configure SSO or create access keys as a replacement.

Stop if the account is not `<AWS_ACCOUNT_ID>`. Management account `<AWS_MGMT_ACCOUNT_ID>` is not the account holding the project RDS resources.

### 4C. Check RDS and your network without changes

```sh
aws rds describe-db-instances --profile firely-learning --region us-east-2 \
  --db-instance-identifier firely-learning-db \
  --query 'DBInstances[0].{Status:DBInstanceStatus,Host:Endpoint.Address,Port:Endpoint.Port,Public:PubliclyAccessible}' \
  --output json --no-cli-pager
```

Expected:

```json
{
  "Status": "available",
  "Host": "<RDS_ENDPOINT>",
  "Port": 1433,
  "Public": true
}
```

If status is `stopped`, use the RDS console in account `<AWS_ACCOUNT_ID>`, region Ohio/us-east-2: select `firely-learning-db` → Actions → Start. This is an AWS state change; do it only when you intend to resume the full demonstration and accept runtime charges. Do not create or restore a replacement database. Wait for `available`, then repeat the check. If you do not want to start RDS, use the Snowflake-only path.

Check native IPv4 and TCP:

```sh
curl -4 --silent --show-error --max-time 10 https://checkip.amazonaws.com
nc -vz -G 5 <RDS_ENDPOINT> 1433
```

Expected: an IPv4 address, followed by a successful TCP connection. The IP can change on Wi-Fi/mobile networks. Do not reuse a historical IP blindly. TCP success alone does not prove database login or TLS negotiation.

### 4D. Run the project's consolidated preflight once

```sh
document-tools-venv/bin/python -B worklist/demo_check.py preflight
```

Expected:

```text
PASS existing Docker containers
PASS AWS login session
PASS stable native IPv4 egress
PASS RDS availability
PASS current IPv4 security-group access
PASS configured SQL TLS settings and IPv4 TCP
Evidence: .../worklist/evidence/repeatable-preflight-<timestamp>.json
```

This checks existing container configuration, SQL endpoint equality, preserved TLS options and TCP; it does not print the connection string. It does not start containers or edit AWS. The six PASS lines are the gate for full startup.

If current IPv4 access fails, stop here. Ask the assistant to compare the current verified /32 with SG `<SECURITY_GROUP_ID>`. Preserve the original rule and the existing added rule `<SG_RULE_ID>`; any correction must remain one /32 under the user's scoped authorization. Do not add 0.0.0.0/0 or accumulate a new rule every day.

### 4E. Start/reuse services with the existing command

In Terminal A:

```sh
document-tools-venv/bin/python -B worklist/demo_check.py start
```

Expected: the six preflight checks pass, existing containers start/reuse, FHIR and Auth become ready, then one of:

```text
Existing authenticated viewer ready at https://localhost:8082
```

or:

```text
Authenticated viewer: https://localhost:8082
Keep this terminal open. Ctrl+C stops the viewer.
```

The second outcome means Terminal A owns the foreground viewer. Leave it open and use Terminal B for other commands. The first means another existing process already serves the viewer; do not launch a duplicate.

If port ownership is unclear:

```sh
lsof -nP -iTCP:8082 -sTCP:LISTEN
```

Expected: one listener. No output means no viewer listener. If an unexpected program occupies the port, identify it before stopping anything. Do not use killall or kill a process merely because its name is Python.

### 4F. Verify readiness and signed-out protection

In Terminal B, first change to the project directory, then:

```sh
cd ~/firely-learning
document-tools-venv/bin/python -B worklist/demo_check.py smoke
```

Expected:

```text
PASS FHIR readiness
PASS FHIR anonymous Patient denial
PASS viewer health
PASS anonymous summary denial
PASS anonymous document denial
PASS Auth TLS and discovery issuer
Evidence: .../worklist/evidence/repeatable-smoke-<timestamp>.json
```

These checks are service/anonymous tests, not proof of a new authenticated reviewer session.

### 4G. Sign in only when your work requires it

Open https://localhost:8082/auth/login and sign in as Demo Reviewer. Keep credentials out of chat. If consent appears, review the existing identity/profile and Patient/Observation/Appointment/DocumentReference read/search permissions, then accept yourself if intended.

Expected viewer: `Signed in as Demo Reviewer`. Patient IDs: `demo-patient-002` and `fixture-v2-p02`. The latter has the synthetic PDF/PNG and resolved worklist history.

Viewer sessions expire after at most 15 minutes and are held in server memory. Restarting the viewer loses the session; a browser tab remaining open does not preserve it. A fresh login is normal and does not require environment reconfiguration.

## 5. Failure handling — stop repeating healthy setup

| Symptom | Meaning/action |
|---|---|
| Docker unavailable | Start Docker Desktop, verify context; do not rebuild |
| AWS login required | Renew the existing profile once, repeat identity/preflight |
| RDS starting | Wait for available; avoid repeated starts |
| TCP timeout/IP rule fails | Check native IPv4 and scoped ingress; no broad rules |
| Endpoint mismatch | Compare safe hostname/port only; preserve SQL TLS |
| Firely HTTP 402 / readiness fails after long uptime | Previously caused by evaluation max uptime; verify current structured cause before restart |
| Viewer URLError with no port listener | Start existing viewer through startup command |
| Browser certificate warning | Stop; inspect trusted local CA/cert expiry; never bypass or use curl -k |
| Reviewer signed out | Normal login; do not change identity mapping blindly |
| Snowflake object not authorized | Check account and selected existing role; do not add broad grants |
| External stage sts:AssumeRole denied | Known unresolved external route; use approved internal RAW table for analytics |

For a confirmed recurrence of the previously diagnosed evaluation uptime limit, restart only the affected existing containers under the existing service-recovery authorization:

```sh
docker restart firely-learning-aws firely-learning-auth
```

Then allow initialization and rerun smoke once. Restarting may require a fresh login. Do not infer every 402 has the same cause; do not change licensing or authentication. If the startup command stops before launching the viewer, retry `start` after service recovery.

## 6. End of session — save before stopping

1. Save edited files and Snowflake worksheet SQL.
2. Save actual query IDs/results in `analytics/evidence/`; distinguish live results from offline tests.
3. Update the milestone report and a short session note with the next concrete action.
4. If code/config changed, record the before/after checkpoint locations. Never copy credential files into a public report.
5. Sign out of the viewer using its logout action when finished. Closing the tab alone is not logout. Server shutdown clears its in-memory sessions.

Create a dated note if useful:

```sh
mkdir -p session-notes
```

Save a Markdown file there using this template, with a filename such as `2026-10-05-session-end.md`:

```markdown
# Session end — DATE, time America/New_York
- Completed:
- Live evidence/report paths:
- Offline tests:
- Changed files/cloud objects:
- Checkpoint locations:
- Viewer/container state:
- Snowflake warehouse state:
- RDS left available or explicitly stopped:
- Remaining blocker:
- Next exact action:
```

A local checkpoint is not a Git commit or off-device backup. Do not claim everything is backed up merely because it is saved locally.

## 7. End of day — Snowflake

Run:

```sql
SHOW WAREHOUSES LIKE 'FIRELY_DEMO_WH';
```

If already `SUSPENDED`, you are done. If `STARTED`, verify there are no running or queued queries/other users' work. The dedicated warehouse auto-suspends after 60 seconds idle; no need to keep a browser tab open.

Only if idle and still started:

```sql
ALTER WAREHOUSE FIRELY_DEMO_WH SUSPEND;
```

Expected: successful statement. If it reports `Invalid state ... cannot be suspended`, run SHOW again: auto-suspend may already have occurred. Verify rather than repeatedly retrying.

```sql
SHOW WAREHOUSES LIKE 'FIRELY_DEMO_WH';
```

Expected final state: `SUSPENDED`. Do not execute another data query afterward merely to check counts—it can resume the warehouse. Do not suspend/reconfigure `CHATGPT_WH` or unrelated warehouses.

Suspension stops warehouse compute, not storage costs. Exact credit usage may be reported with delay; do not claim zero cost. No daily warehouse recreation, resizing, paid-plan upgrade or grant change is needed.

## 8. End of day — local services

If Terminal A owns the foreground viewer, press **Ctrl+C** there. Expected: returns to the shell prompt. If another assistant/terminal owns it, ask that owner to stop its viewer gracefully rather than launching or killing unidentified processes.

For a full local shutdown:

```sh
docker stop firely-learning-aws firely-learning-auth firely-learning-mailpit
```

Expected: the three container names printed. Verify:

```sh
docker ps --format 'table {{.Names}}\t{{.Status}}'
lsof -nP -iTCP:8082 -sTCP:LISTEN
```

Expected: none of the three project containers in the running list; no viewer listener if you stopped it. Other unrelated containers may remain running.

Containers and volumes remain saved. You may quit Docker Desktop afterward if no other work uses it. Never use `docker rm`, `docker volume rm`, `docker system prune`, or `docker compose down -v` as daily shutdown.

Stopping Docker does not stop RDS. Closing Snowflake does not itself suspend a running warehouse.

## 9. End of day — AWS/RDS decision

Default: do not change AWS resources automatically. Record whether RDS is left available. An available RDS instance can incur costs even while your Mac is off.

If you intentionally choose to pause the database and no other work depends on it, use RDS console account `<AWS_ACCOUNT_ID>`, Ohio/us-east-2, instance `firely-learning-db` → Actions → Stop temporarily. This preserves the database but interrupts FHIR access. Follow the console's current duration/restart and charge notices; do not assume stopping removes storage/backup costs or lasts indefinitely.

Optional terminal equivalent, only after that explicit decision:

```sh
aws rds stop-db-instance --profile firely-learning --region us-east-2 \
  --db-instance-identifier firely-learning-db \
  --query 'DBInstance.{Id:DBInstanceIdentifier,Status:DBInstanceStatus}' \
  --output json --no-cli-pager
```

Expected initial state: `stopping`, later `stopped`. Verify with the read-only RDS query in step 4C. Do not stop RDS merely because an assistant reaches the end of a turn. The next full startup needs the instance available again; Snowflake analytics can still proceed independently.

## 10. Checklists

### Start — Snowflake-only work

- [ ] Read last session note/latest milestone.
- [ ] Correct Snowflake account/user/authorized role.
- [ ] Existing FIRELY_DEMO_WH verified; no recreation.
- [ ] Internal RAW table counts 2/3/2 verified once if needed.
- [ ] Next project task identified; skipped unrelated AWS/Docker setup.

### Start — full reviewer/FHIR work

- [ ] Correct project folder/Python environment.
- [ ] Docker engine ready; desktop-linux context.
- [ ] Expected containers exist; rollback Auth remains stopped.
- [ ] AWS login valid in account <AWS_ACCOUNT_ID>.
- [ ] RDS available; current native IPv4 allowed; TCP reachable.
- [ ] Preflight 6/6 PASS.
- [ ] Existing startup command completed; single viewer listener.
- [ ] Smoke 6/6 PASS.
- [ ] Demo Reviewer login completed only if needed.
- [ ] Begin project work; do not repeat passing checks without a new failure/change.

### End — all sessions

- [ ] Files, SQL, query IDs and actual evidence saved.
- [ ] Session note/next action recorded.
- [ ] Checkpoints identified for changes; no secret material published.
- [ ] Viewer signed out/stopped if finished.
- [ ] Dedicated warehouse confirmed SUSPENDED; no data query afterward.
- [ ] Project containers stopped if choosing full local shutdown; volumes preserved.
- [ ] RDS state/cost decision explicitly recorded.
- [ ] No new access rules, object recreation or environment rebuild performed as routine housekeeping.

## 11. Copy this into the next LLM session

> Continue the existing project at ~/firely-learning. Read DAILY-START-END-RUNBOOK.md, the latest session note, CURRENT-PROGRESS-2026-10-05.md and LLM-CONTINUATION-INSTRUCTIONS-2026-10-05.md. Start with only the dependencies needed for today's task. The internal-stage RAW milestone passed with 7 records in CHATGPT_LAB.FIRELY_RAW_5DD08717.FHIR_RESOURCE_INTERNAL using FIRELY_DEMO_WH. Do not repeat uploads/setup or treat the blocked external S3 integration as a prerequisite for internal analytics. Reuse existing services and sessions, preserve data/security, and never display credentials. Tell me the next concrete project action after the minimum checks pass. At the end, save evidence and a session note and report actual service/warehouse/RDS states. Respect my current request and ask only for necessary interactive login or a blocking decision.

## Reference identifiers

| Item | Value |
|---|---|
| AWS profile/region/project account | firely-learning / us-east-2 / <AWS_ACCOUNT_ID> |
| RDS | firely-learning-db |
| RDS endpoint | <RDS_ENDPOINT>:1433 |
| RDS SG / added rule | <SECURITY_GROUP_ID> / <SG_RULE_ID> |
| Viewer / login | https://localhost:8082/ / https://localhost:8082/auth/login |
| Auth / FHIR readiness | https://localhost:5001 / http://localhost:8081/$readiness |
| Snowflake account/user | <SNOWFLAKE_ACCOUNT> / <SNOWFLAKE_USER> |
| Dedicated warehouse | FIRELY_DEMO_WH |
| Active RAW table | CHATGPT_LAB.FIRELY_RAW_5DD08717.FHIR_RESOURCE_INTERNAL |
| Internal stage | CHATGPT_LAB.FIRELY_RAW_5DD08717.FHIR_INTERNAL_STAGE |
| Saved batch | analytics/batches/synthetic-20261004T225801Z-5dd08717/ |
| Saved private S3 batch | s3://<S3_BUCKET>/analytics-demo/synthetic-20261004T225801Z-5dd08717/ |

This runbook was checked against existing project scripts and saved evidence. Writing it did not start/stop services or change AWS/Snowflake resources. Routine copied commands should still be evaluated against the current observed state.
