"""Durable paid-submission guards. Never stores keys, prompts, or source media."""

import os
import sqlite3
from pathlib import Path

from .client import ApixlyError, UnknownSubmission


class SubmissionJournal:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.path.is_symlink():
            raise ApixlyError("Submission journal must not be a symlink.")
        descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(descriptor)
        os.chmod(self.path, 0o600)
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS submissions (fingerprint TEXT PRIMARY KEY, state TEXT NOT NULL, task_id TEXT, task_status TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)"
            )

    def _connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def submit_once(self, fingerprint, submit):
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT state, task_id, task_status FROM submissions WHERE fingerprint = ?",
                (fingerprint,),
            ).fetchone()
            if row:
                state, identifier, status = row
                if state == "accepted":
                    return {"id": identifier, "status": status}
                if state == "rejected":
                    raise ApixlyError(
                        "This request_nonce was rejected. Correct the request and explicitly select a new nonce for a new paid action."
                    )
                raise UnknownSubmission(
                    "An existing submission with this request_nonce may have reached Apixly. Do not submit again; check existing Apixly tasks before choosing a new nonce."
                )
            # Commit the claim before network I/O, including uncertain crashes.
            connection.execute(
                "INSERT INTO submissions(fingerprint, state) VALUES (?, 'submitting')",
                (fingerprint,),
            )
        try:
            job = submit()
        except BaseException as error:
            state = (
                "rejected"
                if isinstance(error, ApixlyError)
                and not isinstance(error, UnknownSubmission)
                else "unknown"
            )
            with self._connect() as connection:
                connection.execute(
                    "UPDATE submissions SET state = ? WHERE fingerprint = ?",
                    (state, fingerprint),
                )
            raise
        if not isinstance(job, dict) or not job.get("id"):
            with self._connect() as connection:
                connection.execute(
                    "UPDATE submissions SET state = 'unknown' WHERE fingerprint = ?",
                    (fingerprint,),
                )
            raise UnknownSubmission(
                "No task ID was returned. Do not submit again; check existing Apixly tasks."
            )
        identifier, status = str(job["id"]), str(job.get("status", "queued"))
        try:
            with self._connect() as connection:
                connection.execute(
                    "UPDATE submissions SET state = 'accepted', task_id = ?, task_status = ? WHERE fingerprint = ?",
                    (identifier, status, fingerprint),
                )
        except sqlite3.Error:
            raise UnknownSubmission(
                f"Apixly task {identifier} was accepted but its local receipt could not be saved. Resume that existing task ID; do not submit again."
            ) from None
        return {"id": identifier, "status": status}
