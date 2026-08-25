"""Durable, append-only storage for one field sampling session.

A field session is a sequence of physical acts, spread over however long it
takes to walk a field. The storage has to survive that: the operator may power
the unit down between samples, the battery may fail on sample 4, and the
session that comes back afterwards must be the same session, missing at most
the sample that was in flight.

    artifacts/sessions/<session_id>/
        session.json     manifest, rewritten atomically on every change
        samples.jsonl    append-only, one JSON object per line, fsynced

Two shapes, for two different failure modes:

APPEND-ONLY for the samples. Sample 2 is a new line; it does not rewrite the
file that holds sample 1, so no crash during sample 2 can damage sample 1. A
process killed mid-write leaves a torn final line, which fails to parse and is
skipped with a warning — the one sample in flight is lost and every earlier one
is intact. Rewriting a whole samples array on each capture, which is the
obvious alternative, puts every sample in the session at risk on every write.

ATOMIC REPLACE for the manifest, which genuinely must be rewritten: write to a
sibling temp file, fsync it, rename over the target. rename(2) within a
directory is atomic, so a reader sees the old manifest or the new one, never a
half-written one.

`session_id` is stamped into every record. A power cut therefore cannot silently
merge two field sessions into one dataset: resuming re-opens the session that
was in progress, and starting fresh makes a new directory rather than appending
to somebody else's samples.
"""

import json
import os
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional

DEFAULT_SESSION_ROOT = os.path.join("artifacts", "sessions")

#: Bumped when the on-disk record shape changes incompatibly. Present in every
#: record so a later audit knows how to read it.
RECORD_VERSION = 1


def utc_now_iso() -> str:
    """Current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def new_session_id(now: Optional[datetime] = None) -> str:
    """Build a sortable, filesystem-safe session id.

    Time-based rather than random so a directory listing reads chronologically,
    which is what an operator inspecting a day's work actually wants.
    """
    moment = now or datetime.now(timezone.utc)
    return "session_" + moment.strftime("%Y%m%dT%H%M%SZ")


def _fsync_dir(path: str) -> None:
    """Flush a directory entry, so a rename survives power loss.

    Best effort: not every filesystem supports opening a directory this way,
    and failing to fsync must never fail a capture.
    """
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def atomic_write_json(path: str, payload: Dict[str, Any]) -> None:
    """Write JSON so a reader never sees a partial file.

    Raises:
        OSError: The write or rename failed. The caller decides whether that is
            fatal; the previous file is still intact either way.
    """
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=directory,
        prefix=".tmp-", suffix=".json", delete=False)
    try:
        json.dump(payload, handle, indent=2, default=str)
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()
        os.replace(handle.name, path)
    except BaseException:
        try:
            os.unlink(handle.name)
        except OSError:
            pass
        raise
    _fsync_dir(directory)


class FieldSessionStore:
    """The on-disk record of one field sampling session."""

    def __init__(
        self,
        session_id: Optional[str] = None,
        root: str = DEFAULT_SESSION_ROOT,
        planned_samples: int = 5,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Open or create a session directory.

        Args:
            session_id: Existing id to resume, or None to start a new session.
            root: Directory holding all sessions.
            planned_samples: How many samples this session intends to take.
            metadata: Free-form context stamped into the manifest (provenance,
                sensor port, firmware notes).
        """
        self.session_id = session_id or new_session_id()
        self.root = root
        self.directory = os.path.join(root, self.session_id)
        self.manifest_path = os.path.join(self.directory, "session.json")
        self.samples_path = os.path.join(self.directory, "samples.jsonl")
        self.planned_samples = int(planned_samples)
        os.makedirs(self.directory, exist_ok=True)

        existing = self._load_manifest()
        if existing:
            self.created_at = existing.get("created_at", utc_now_iso())
            self.metadata = dict(existing.get("metadata") or {})
            self.planned_samples = int(existing.get("planned_samples", self.planned_samples))
        else:
            self.created_at = utc_now_iso()
            self.metadata = dict(metadata or {})
        if metadata:
            self.metadata.update(metadata)
        self.write_manifest()

    # ------------------------------------------------------------- manifest

    def _load_manifest(self) -> Optional[Dict[str, Any]]:
        """Read the manifest, or None when absent or unreadable."""
        try:
            with open(self.manifest_path, encoding="utf-8") as handle:
                data = json.load(handle)
            return data if isinstance(data, dict) else None
        except (OSError, ValueError):
            return None

    def write_manifest(self, **extra: Any) -> None:
        """Rewrite the manifest atomically, folding in any extra fields."""
        records = self.records()
        payload: Dict[str, Any] = {
            "record_version": RECORD_VERSION,
            "session_id": self.session_id,
            "created_at": self.created_at,
            "updated_at": utc_now_iso(),
            "planned_samples": self.planned_samples,
            "stored_samples": len(records),
            "quality_counts": self.quality_counts(records),
            "metadata": self.metadata,
        }
        payload.update(extra)
        try:
            atomic_write_json(self.manifest_path, payload)
        except OSError:
            # A manifest that cannot be written is a diagnostic loss, not a data
            # loss: samples.jsonl is the record of truth and is already on disk.
            pass

    # -------------------------------------------------------------- samples

    def append_sample(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Append one sample record and return it as stored.

        The record is stamped with the session id and a write timestamp here
        rather than by the caller, so no code path can store a sample that does
        not say which session it belongs to.

        Raises:
            OSError: The append failed. Deliberately not swallowed — losing a
                sample silently is the one outcome this module exists to
                prevent, and the workflow must be able to tell the operator.
        """
        stored = dict(record)
        stored["record_version"] = RECORD_VERSION
        stored["session_id"] = self.session_id
        stored.setdefault("stored_at", utc_now_iso())

        line = json.dumps(stored, default=str, sort_keys=False)
        with open(self.samples_path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        self.write_manifest()
        return stored

    def iter_records(self) -> Iterator[Dict[str, Any]]:
        """Yield every intact sample record, skipping any torn trailing line."""
        try:
            with open(self.samples_path, encoding="utf-8") as handle:
                for line in handle:
                    text = line.strip()
                    if not text:
                        continue
                    try:
                        parsed = json.loads(text)
                    except ValueError:
                        # A partial final line is the expected shape of a crash
                        # during a write. Everything before it is still good.
                        continue
                    if isinstance(parsed, dict):
                        yield parsed
        except OSError:
            return

    def records(self) -> List[Dict[str, Any]]:
        """Every intact sample record, in capture order."""
        return list(self.iter_records())

    def stored_count(self) -> int:
        """How many samples are on disk for this session."""
        return sum(1 for _ in self.iter_records())

    def next_index(self) -> int:
        """The 1-based index the next sample should be stored under.

        Derived from the highest index already on disk rather than from a
        counter in memory, so resuming after a power cut cannot overwrite a
        stored sample.
        """
        highest = 0
        for record in self.iter_records():
            try:
                index = int(record.get("sample_index", 0))
            except (TypeError, ValueError):
                continue
            if index > highest:
                highest = index
        return highest + 1

    def last_reading(self) -> Optional[Dict[str, Any]]:
        """The soil channels of the most recent stored sample, if any."""
        last = None
        for record in self.iter_records():
            reading = record.get("soil")
            if isinstance(reading, dict):
                last = reading
        return last

    def last_position(self) -> Optional[Dict[str, Any]]:
        """The GPS block of the most recent stored sample carrying a fix."""
        last = None
        for record in self.iter_records():
            gps = record.get("gps")
            if isinstance(gps, dict) and gps.get("fix_valid"):
                last = gps
        return last

    @staticmethod
    def quality_counts(records: List[Dict[str, Any]]) -> Dict[str, int]:
        """Tally stored samples by field quality verdict."""
        counts: Dict[str, int] = {}
        for record in records:
            quality = str(record.get("quality", "UNKNOWN"))
            counts[quality] = counts.get(quality, 0) + 1
        return counts

    def close(self, status: str, **extra: Any) -> None:
        """Stamp a terminal status into the manifest."""
        self.write_manifest(status=status, closed_at=utc_now_iso(), **extra)


def list_sessions(root: str = DEFAULT_SESSION_ROOT) -> List[str]:
    """Return every session id under `root`, oldest first."""
    try:
        names = [
            name for name in os.listdir(root)
            if os.path.isdir(os.path.join(root, name))
        ]
    except OSError:
        return []
    return sorted(names)


def latest_session(root: str = DEFAULT_SESSION_ROOT) -> Optional[str]:
    """The most recent session id under `root`, or None."""
    sessions = list_sessions(root)
    return sessions[-1] if sessions else None
