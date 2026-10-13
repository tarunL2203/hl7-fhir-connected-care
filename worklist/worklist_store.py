"""SQLite worklist: deduplicated work items, guarded state transitions and an append-only history."""

import json
import sqlite3
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat()


class WorklistStore:
    def __init__(self, path):
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.executescript(
            """
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY,
            appointment_id TEXT NOT NULL,
            requirement_id TEXT NOT NULL,
            issue_type TEXT NOT NULL,
            payload TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(appointment_id, requirement_id, issue_type)
        );
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY,
            item_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            actor TEXT NOT NULL,
            reason TEXT NOT NULL,
            at TEXT NOT NULL
        );
        """
        )

    def event(self, item_id, action, actor, reason):
        self.db.execute(
            "INSERT INTO history(item_id,action,actor,reason,at) VALUES(?,?,?,?,?)",
            (item_id, action, actor, reason, now()),
        )

    def upsert(self, payload):
        required = (
            "patient_id",
            "appointment_id",
            "requirement_id",
            "issue_type",
            "policy_id",
            "evidence",
            "owner_role",
            "permitted_action",
            "due_at",
        )
        if any(key not in payload for key in required):
            raise ValueError("Work item is missing required fields")

        due = datetime.fromisoformat(payload["due_at"].replace("Z", "+00:00"))
        if due.tzinfo is None:
            raise ValueError("Due time requires timezone")

        key = tuple(payload[k] for k in ("appointment_id", "requirement_id", "issue_type"))
        encoded = json.dumps(payload, sort_keys=True)

        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            row = self.db.execute(
                """SELECT * FROM items
                   WHERE appointment_id=? AND requirement_id=? AND issue_type=?""",
                key,
            ).fetchone()

            if row is None:
                stamp = now()
                cursor = self.db.execute(
                    """INSERT INTO items(
                       appointment_id,requirement_id,issue_type,payload,
                       status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)""",
                    (*key, encoded, "open", stamp, stamp),
                )
                item_id = cursor.lastrowid
                self.event(item_id, "created", "assessment_engine", "Issue detected")
                return item_id, "created"

            if json.loads(row["payload"])["patient_id"] != payload["patient_id"]:
                raise ValueError("Patient mismatch for existing work-item key")

            item_id = row["id"]
            if row["status"] == "resolved":
                self.db.execute(
                    "UPDATE items SET payload=?,status='open',updated_at=? WHERE id=?",
                    (encoded, now(), item_id),
                )
                self.event(item_id, "reopened", "assessment_engine", "Issue detected again")
                return item_id, "reopened"

            if row["payload"] != encoded:
                self.db.execute(
                    "UPDATE items SET payload=?,updated_at=? WHERE id=?", (encoded, now(), item_id)
                )
                self.event(item_id, "evidence_updated", "assessment_engine", "Evidence changed")
                return item_id, "updated"

            return item_id, "unchanged"

    def transition(self, item_id, target, actor, role, reason, reassessment=None):
        if target not in ("in_review", "resolved"):
            raise ValueError("Unsupported transition")
        if not actor.strip() or not reason.strip():
            raise ValueError("Actor and reason are required")

        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            row = self.db.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
            if row is None:
                raise ValueError("Unknown work item")

            payload = json.loads(row["payload"])
            if role != payload["owner_role"]:
                raise PermissionError("Role is not permitted")

            if target == "in_review" and row["status"] != "open":
                raise ValueError("Only an open item can enter review")
            if target == "resolved":
                if row["status"] != "in_review":
                    raise ValueError("Review is required before resolution")
                if not reassessment:
                    raise ValueError("Fresh reassessment is required")
                if (
                    reassessment.get("patient_id") != payload["patient_id"]
                    or reassessment.get("appointment_id") != payload["appointment_id"]
                    or reassessment.get("policy_id") != payload["policy_id"]
                    or reassessment.get("outcome") != "information_complete"
                ):
                    raise ValueError("Reassessment does not prove resolution")
                assessed = datetime.fromisoformat(
                    reassessment["assessed_at"].replace("Z", "+00:00")
                )
                if assessed.tzinfo is None:
                    raise ValueError("Reassessment requires timezone")
                age = (datetime.now(timezone.utc) - assessed).total_seconds()
                if not 0 <= age <= 300:
                    raise ValueError("Reassessment must be within five minutes")

            self.db.execute(
                "UPDATE items SET status=?,updated_at=? WHERE id=?", (target, now(), item_id)
            )
            self.event(item_id, target, actor, reason)

    def close(self):
        self.db.close()
