"""Durable lighting handoff guard for Legacy.

Everyday commands are tracked in memory only: the panel stays the owner, so an
unconfirmed command is followed by a fresh read rather than a staff lock.
"""

import json
import os
import queue
import tempfile
import threading
import time

from preferences import sync_directory


class LightingRecovery:
    """Called only by the panel owner."""

    STATUSES = ("normal", "writing", "uncertain", "recovering", "legacy")

    def __init__(self, path=None, clock=time.time, background=False):
        self.path, self.clock, self.error = os.fspath(path) if path else None, clock, None
        self.saves = None
        self.settled = threading.Event()
        self.settled.set()
        self.state = {"version": 1, "status": "normal", "revision": 0,
                      "request_id": "", "acknowledged_at": None,
                      "recovered_at": None, "reason": "", "updated_at": clock(),
                      "legacy_log": None}
        if self.path is None:
            return
        try:
            with open(self.path, encoding="utf-8") as stream:
                raw = stream.read(8193)
            value = json.loads(raw)
            if isinstance(value, dict):
                # Keep existing Legacy checkpoints readable; new saves omit retired metadata.
                for retired in ("token_hash", "label", "heartbeat_at"):
                    value.pop(retired, None)
                value.setdefault("legacy_log", None)  # Older records cannot authorize an automatic return.
                if value.get("status") in ("releasing", "reserved"):
                    # Retired experiment handoff: someone else may have changed the lights.
                    value.update(status="uncertain", reason="An earlier experiment handoff did not finish.")
            if len(raw) > 8192 or not self._valid(value):
                raise ValueError("Invalid lighting recovery state")
            self.state = value
            if value["status"] == "writing":
                value["status"] = "normal"  # Older records; the next acquire re-reads the lights.
            if value["status"] == "recovering":
                self.mark_uncertain("Panel stopped before the previous operation was confirmed.")
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError, RecursionError, RuntimeError) as error:
            self.error = str(error) or "Lighting recovery state could not be read"
            self.state["status"] = "uncertain"
        if background and self.path and not self.error:
            self.saves = queue.Queue(maxsize=16)
            self.save_lock = threading.Lock()
            self.save_count = 0
            threading.Thread(target=self._write_saves, name="scr-lighting-recovery", daemon=True).start()

    @property
    def pending(self):
        return not self.settled.is_set()

    def _write_saves(self):
        # FIFO: never coalesce away an unresolved-write or ownership checkpoint.
        while True:
            value = self.saves.get()
            try:
                if not self.error:
                    self._persist(value)
            except Exception as error:
                self.error = str(error) or "Lighting recovery state could not be saved"
            finally:
                with self.save_lock:
                    self.save_count -= 1
                    if not self.save_count:
                        self.settled.set()

    @classmethod
    def _valid(cls, value):
        keys = {"version", "status", "revision", "request_id", "acknowledged_at", "recovered_at", "reason", "updated_at", "legacy_log"}
        if not isinstance(value, dict) or set(value) != keys:
            return False
        if type(value["version"]) is not int or value["version"] != 1:
            return False
        if value["status"] not in cls.STATUSES or type(value["revision"]) is not int or value["revision"] < 0:
            return False
        if any(not isinstance(value[key], str) or len(value[key]) > limit
               for key, limit in (("request_id", 160), ("reason", 240))):
            return False
        if value["status"] == "writing" and not value["request_id"]:
            return False
        if value["status"] == "recovering" and value["acknowledged_at"] is None:
            return False
        if value["updated_at"] is None:
            return False
        if value["legacy_log"] is not None and not cls._valid_log_position(value["legacy_log"]):
            return False
        return all(value[key] is None or (type(value[key]) in (float, int) and 0 <= value[key] < 1e15)
                   for key in ("acknowledged_at", "recovered_at", "updated_at"))

    def _save(self, persist=True, **changes):
        if self.error:
            raise RuntimeError("Lighting recovery storage needs staff attention")
        value = dict(self.state, **changes)
        value.update(revision=self.state["revision"] + 1, updated_at=self.clock())
        if self.path is None or not persist:
            self.state = value
            return
        if self.saves is not None:
            with self.save_lock:
                try:
                    self.saves.put_nowait(value)
                except queue.Full:
                    self.error = "Lighting recovery save queue is full"
                    raise RuntimeError(self.error)
                self.save_count += 1
                self.settled.clear()
            self.state = value
            return
        try:
            self._persist(value)
            self.state = value
        except (OSError, ValueError) as error:
            self.error = str(error) or "Lighting recovery state could not be saved"
            self.state["status"] = "uncertain"
            raise RuntimeError("Lighting recovery state could not be saved") from error

    def _persist(self, value):
        temporary = None
        try:
            directory = os.path.dirname(os.path.abspath(self.path))
            os.makedirs(directory, mode=0o700, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(prefix=".lighting-", dir=directory)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(value, stream, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            temporary = None
            sync_directory(directory)
        finally:
            if temporary:
                try:
                    os.unlink(temporary)
                except OSError:
                    pass

    @staticmethod
    def _text(value, limit, name):
        if not isinstance(value, str) or not 1 <= len(value) <= limit or not value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError("Invalid " + name)
        return value

    def begin_write(self, request_id, returning=False):
        if self.state["status"] != "normal" and not (returning is True and self.state["status"] == "recovering"):
            raise RuntimeError("Lighting ownership or an earlier command is unresolved")
        # Kept in memory: a restart then still shows the saved "normal" (re-read on
        # acquire) or, for a Legacy return, "recovering" (staff check).
        self.returning = returning is True and self.state["status"] == "recovering"
        self._save(persist=False, status="writing",
                   request_id=self._text(request_id, 160, "request ID"))

    def finish_write(self, request_id):
        """The command finished, confirmed or not; the panel still owns the lights."""
        if self.state["status"] != "writing" or request_id != self.state["request_id"]:
            raise ValueError("Lighting command result does not match")
        self._save(persist=getattr(self, "returning", False), status="normal")

    def mark_uncertain(self, reason):
        self._save(status="uncertain", reason=self._text(reason, 240, "recovery reason"))

    @staticmethod
    def _valid_log_position(value):
        return (isinstance(value, dict) and set(value) == {"device", "inode", "size"}
                and all(type(v) is int and v >= 0 for v in value.values()))

    def enter_legacy(self, log_position=None):
        if self.state["status"] != "normal":
            raise RuntimeError("Lighting ownership must be resolved before opening Legacy")
        if log_position is not None and not self._valid_log_position(log_position):
            raise ValueError("Invalid Legacy log checkpoint")
        self._save(status="legacy", legacy_log=dict(log_position) if log_position is not None else None)

    def legacy_log_unchanged(self, log_position, current_new_bytes):
        saved = self.state["legacy_log"]
        if not self._valid_log_position(saved) or not self._valid_log_position(log_position):
            return False
        if not isinstance(current_new_bytes, bytes):
            return False
        if any(saved[key] != log_position[key] for key in ("device", "inode")) or log_position["size"] - saved["size"] != len(current_new_bytes):
            return False
        return not any(marker in current_new_bytes for marker in (
            b"Exception in Tkinter callback", b"Traceback", b"ROSException", b"ServiceException",
            b"Service call failed:"))

    def leave_legacy(self, idle_confirmed=False, callback_clean=False):
        if (self.state["status"] != "legacy" or idle_confirmed is not True
                or callback_clean is not True or not self._valid_log_position(self.state["legacy_log"])):
            raise RuntimeError("Confirm the original controller is idle and its callback log is clean")
        self._save(status="recovering", acknowledged_at=self.clock())

    def acknowledge(self, owner_closed=False, pending_clear=False):
        """Local staff must confirm process/handler checks outside this guard."""
        if owner_closed is not True or pending_clear is not True:
            raise RuntimeError("Confirm the previous owner is closed and no command is pending")
        if self.state["status"] not in ("uncertain", "legacy"):
            raise RuntimeError("There is no blocked ownership to reconcile")
        self._save(status="recovering", acknowledged_at=self.clock())

    def ready(self, stable=False):
        if stable is not True or self.state["status"] not in ("normal", "recovering"):
            raise RuntimeError("Confirmed ownership and a stable read-only acquisition are required")
        if self.state["status"] == "recovering":
            self._save(status="normal", recovered_at=self.clock())

    def public(self):
        status = "uncertain" if self.error else self.state["status"]
        # No client may treat an optimistic in-memory transition as durable.
        if self.pending and not self.error:
            status = {"normal": "writing", "legacy": "writing"}.get(status, status)
        titles = {"normal": "Lighting ready", "writing": "Changing lighting",
                  "uncertain": "Lighting needs a check", "recovering": "Checking lighting connection",
                  "legacy": "Legacy controls are open"}
        details = {"normal": "Current lighting is preserved.", "writing": "Waiting for the lighting command to finish.",
                   "uncertain": "A Legacy handoff did not finish cleanly. Staff must check it before controls return.",
                   "recovering": "Reading current settings before everyday controls return.",
                   "legacy": "The original room app controls the lights. Return Home to use Beta."}
        return {"status": status, "title": titles[status], "detail": details[status],
                "can_check": not self.error and not self.pending and status in ("normal", "uncertain", "recovering"),
                "needs_staff": bool(self.error) or status == "uncertain",
                "write_blocked": bool(self.error) or self.pending or status != "normal"}
