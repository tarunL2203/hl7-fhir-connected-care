"""Offline workflow tests for the worklist: create, deduplicate, transition, resolve and reopen."""

import tempfile
from datetime import datetime, timezone
from pathlib import Path
from worklist_store import WorklistStore

ROOT = Path(__file__).resolve().parent


def expect_rejection(label, error_type, action):
    try:
        action()
    except error_type:
        print(label + ": PASS")
    else:
        raise AssertionError(label + ": action was incorrectly allowed")


with tempfile.TemporaryDirectory() as directory:
    store = WorklistStore(Path(directory) / "workflow-test.sqlite")

    payload = {
        "patient_id": "fixture-v2-p02",
        "appointment_id": "fixture-v2-a02",
        "requirement_id": "glucose-result",
        "issue_type": "missing_expected_record",
        "policy_id": "demo-previsit-v2",
        "evidence": {"retrieval_complete": True, "qualifying_records": 0},
        "owner_role": "records_staff",
        "permitted_action": "Investigate availability and request records",
        "due_at": "2026-10-05T12:00:00Z",
    }

    item_id, action = store.upsert(payload)
    assert action == "created"
    print("Create work item: PASS")

    replay_id, action = store.upsert(payload)
    assert replay_id == item_id and action == "unchanged"
    assert store.db.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 1
    assert store.db.execute("SELECT COUNT(*) FROM history").fetchone()[0] == 1
    print("Replay without duplicates: PASS")

    expect_rejection(
        "Unauthorized role rejected",
        PermissionError,
        lambda: store.transition(item_id, "in_review", "test-user", "viewer", "Review"),
    )

    store.transition(
        item_id,
        "in_review",
        "test-records-user",
        "records_staff",
        "Investigating missing information",
    )
    print("Authorized review: PASS")

    expect_rejection(
        "Resolution without reassessment rejected",
        ValueError,
        lambda: store.transition(
            item_id, "resolved", "test-records-user", "records_staff", "Attempted resolution"
        ),
    )

    reassessment = {
        "patient_id": payload["patient_id"],
        "appointment_id": payload["appointment_id"],
        "policy_id": payload["policy_id"],
        "outcome": "information_complete",
        "assessed_at": datetime.now(timezone.utc).isoformat(),
    }

    wrong = dict(reassessment, patient_id="another-patient")
    expect_rejection(
        "Wrong-patient reassessment rejected",
        ValueError,
        lambda: store.transition(
            item_id, "resolved", "test-records-user", "records_staff", "Attempted resolution", wrong
        ),
    )

    store.transition(
        item_id,
        "resolved",
        "test-records-user",
        "records_staff",
        "Fresh assessment confirms information complete",
        reassessment,
    )
    print("Resolution with reassessment: PASS")

    reopened_id, action = store.upsert(payload)
    assert reopened_id == item_id and action == "reopened"
    print("Reappearing issue reopens original item: PASS")

    actions = [row["action"] for row in store.db.execute("SELECT action FROM history ORDER BY id")]
    assert actions == ["created", "in_review", "resolved", "reopened"]
    print("Resolution history: PASS")
    store.close()

print("Workflow tests passed: 9/9")
print("Live Firely records changed: 0")
