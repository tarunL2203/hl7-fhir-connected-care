
import json
import subprocess
import sys
from pathlib import Path
from worklist_bridge import synchronize
from worklist_store import WorklistStore

ROOT = Path(__file__).resolve().parent

def main():
    before = set((ROOT / "evidence").glob("ravi-assessment-*.json"))

    completed = subprocess.run(
        [sys.executable, str(ROOT / "assess_ravi.py")]
    )
    if completed.returncode != 0:
        raise RuntimeError("Live assessment failed; worklist was not updated")

    after = set((ROOT / "evidence").glob("ravi-assessment-*.json"))
    new_reports = after - before
    if len(new_reports) != 1:
        raise RuntimeError("Could not identify exactly one fresh assessment")

    report_path = new_reports.pop()
    report = json.loads(report_path.read_text())
    policy = json.loads((ROOT / "spec/v2/policy.json").read_text())

    store = WorklistStore(ROOT / "data/worklist.sqlite")
    try:
        changes = synchronize(
            store, report["input"], report["result"], policy
        )
        for change in changes:
            print("Work item:", change["item_id"], change["action"])

        print("Work items created or updated:", len(changes))
        pending = store.db.execute(
            """SELECT COUNT(*) FROM items
               WHERE appointment_id=? AND status!='resolved'""",
            (report["result"]["appointment_id"],)
        ).fetchone()[0]
        print("Pending items for this appointment:", pending)

        if report["result"]["outcome"] == "requirements_not_configured":
            print("Configuration review required; completeness was not assessed")
        if report["result"]["outcome"] == "information_complete" and pending:
            print("Information now complete; pending items require reviewed resolution")
    finally:
        store.close()

if __name__ == "__main__":
    main()
