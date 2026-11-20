"""Optional SQLite persistence so athlete histories build up across uploads.

The store keeps only *inputs*: the uploaded workbook files (keyed by SHA-256) and
manual include/exclude decisions. The dataset is always recomputed from them with
the pure pipeline, so logic lives in one place and results stay deterministic.
Re-uploading a file that is already stored is a no-op.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import sqlite3
from typing import Dict, List, Optional, Tuple

from .config import LoadWiseInputError

SCHEMA = """
CREATE TABLE IF NOT EXISTS imports (
    sha256 TEXT PRIMARY KEY,
    seq INTEGER NOT NULL,
    filename TEXT NOT NULL,
    season_start_year INTEGER,
    uploaded_at TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    file_blob BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS overrides (
    record_id TEXT PRIMARY KEY,
    action TEXT NOT NULL CHECK (action IN ('include', 'exclude')),
    reason TEXT NOT NULL,
    decided_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS plan_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    athlete_id TEXT NOT NULL,
    athlete_label TEXT NOT NULL,
    start TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('accepted', 'rejected', 'modified')),
    rating INTEGER CHECK (rating BETWEEN 1 AND 5),
    rating_scale TEXT CHECK (rating_scale IN ('acceptance', 'rejection')),
    comment TEXT,
    config_json TEXT NOT NULL,
    proposal_json TEXT NOT NULL,
    modified_json TEXT
);
"""

DECISIONS = ("accepted", "rejected", "modified")
RATING_SCALE = {"accepted": "acceptance", "rejected": "rejection"}
FEEDBACK_COLUMNS = ("id", "created_at", "athlete_id", "athlete_label", "start", "decision", "rating",
                    "rating_scale", "comment", "config_json", "proposal_json", "modified_json")
COMMENT_LIMIT = 2000


class Store:
    def __init__(self, path: str):
        self.path = path
        if os.path.dirname(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)

    def _conn(self):
        return sqlite3.connect(self.path)

    # -- imports ------------------------------------------------------------
    def season_start_year(self) -> Optional[int]:
        with self._conn() as c:
            row = c.execute("SELECT season_start_year FROM imports ORDER BY seq LIMIT 1").fetchone()
        return row[0] if row else None

    def add_import(self, filename: str, data: bytes, season_start_year: Optional[int]) -> Tuple[str, str]:
        """-> (status, sha256). status is 'imported' or 'already_imported'."""
        sha = hashlib.sha256(data).hexdigest()
        existing_year = self.season_start_year()
        with self._conn() as c:
            if c.execute("SELECT 1 FROM imports WHERE sha256 = ?", (sha,)).fetchone():
                return "already_imported", sha
            if existing_year is not None and season_start_year != existing_year:
                raise LoadWiseInputError(
                    f"The stored history uses season start year {existing_year}, but this upload "
                    f"uses {season_start_year}. Upload with {existing_year}, or reset the stored "
                    "history to start a different season.")
            seq = (c.execute("SELECT COALESCE(MAX(seq), 0) FROM imports").fetchone()[0]) + 1
            c.execute("INSERT INTO imports VALUES (?, ?, ?, ?, ?, ?, ?)",
                      (sha, seq, filename, season_start_year,
                       dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
                       len(data), data))
        return "imported", sha

    def imports(self) -> List[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT sha256, seq, filename, season_start_year, uploaded_at, size_bytes "
                             "FROM imports ORDER BY seq").fetchall()
        return [dict(zip(("sha256", "seq", "filename", "season_start_year", "uploaded_at",
                          "size_bytes"), r)) for r in rows]

    def sources(self) -> List[Tuple[str, bytes]]:
        with self._conn() as c:
            return [(n, bytes(b)) for n, b in
                    c.execute("SELECT filename, file_blob FROM imports ORDER BY seq").fetchall()]

    def remove_import(self, sha256: str) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM imports WHERE sha256 = ?", (sha256,))

    # -- overrides ----------------------------------------------------------
    def overrides(self) -> Dict[str, dict]:
        with self._conn() as c:
            rows = c.execute("SELECT record_id, action, reason, decided_at FROM overrides").fetchall()
        return {r[0]: {"action": r[1], "reason": r[2], "decided_at": r[3]} for r in rows}

    def set_override(self, record_id: str, action: str, reason: str) -> None:
        if action not in ("include", "exclude"):
            raise LoadWiseInputError("Action must be 'include' or 'exclude'.")
        if not reason or not reason.strip():
            raise LoadWiseInputError("Please give a short reason for the decision.")
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO overrides VALUES (?, ?, ?, ?)",
                      (record_id, action, reason.strip(),
                       dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()))

    def clear_override(self, record_id: str) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM overrides WHERE record_id = ?", (record_id,))

    # -- coach feedback on proposed plans ------------------------------------
    # Kept on reset: it is evaluation data about the models, not part of the imported dataset.
    def add_feedback(self, *, athlete_id: str, athlete_label: str, start: str, decision: str,
                     rating: Optional[int], comment: Optional[str], config: dict, proposal: dict,
                     modified: Optional[dict] = None) -> dict:
        """Append one coach decision. Ratings are stored with their own scale, never pooled."""
        if decision not in DECISIONS:
            raise LoadWiseInputError("Decision must be accepted, rejected or modified.")
        if decision == "modified":
            if rating is not None:
                raise LoadWiseInputError("A modified plan is not rated.")
            if not modified:
                raise LoadWiseInputError("A modified plan needs the edited days.")
        else:
            if type(rating) is not int or not 1 <= rating <= 5:
                raise LoadWiseInputError("Choose a rating from 1 to 5.")
            if modified is not None:
                raise LoadWiseInputError("Only a modified plan carries edited days.")
        comment = (comment or "").strip() or None
        if comment and len(comment) > COMMENT_LIMIT:
            raise LoadWiseInputError(f"Keep the comment under {COMMENT_LIMIT} characters.")
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO plan_feedback (created_at, athlete_id, athlete_label, start, decision, rating, "
                "rating_scale, comment, config_json, proposal_json, modified_json) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(), athlete_id,
                 athlete_label, start, decision, rating, RATING_SCALE.get(decision), comment,
                 json.dumps(config), json.dumps(proposal),
                 json.dumps(modified) if modified is not None else None))
            new_id = cur.lastrowid
        return self.feedback_record(new_id)

    @staticmethod
    def _feedback_row(row) -> dict:
        d = dict(zip(FEEDBACK_COLUMNS, row))
        for k in ("config", "proposal", "modified"):
            raw = d.pop(k + "_json")
            d[k] = json.loads(raw) if raw is not None else None
        return d

    def feedback(self, athlete_id: Optional[str] = None) -> List[dict]:
        sql = f"SELECT {', '.join(FEEDBACK_COLUMNS)} FROM plan_feedback"
        args: tuple = ()
        if athlete_id:
            sql, args = sql + " WHERE athlete_id = ?", (athlete_id,)
        with self._conn() as c:
            rows = c.execute(sql + " ORDER BY id DESC", args).fetchall()
        return [self._feedback_row(r) for r in rows]

    def feedback_record(self, feedback_id: int) -> Optional[dict]:
        with self._conn() as c:
            row = c.execute(f"SELECT {', '.join(FEEDBACK_COLUMNS)} FROM plan_feedback WHERE id = ?",
                            (feedback_id,)).fetchone()
        return self._feedback_row(row) if row else None

    def reset(self) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM imports")
            c.execute("DELETE FROM overrides")
