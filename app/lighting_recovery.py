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

    STATUSES = ("normal", "uncertain", "legacy")

    def __init__(self, path=None, clock=time.time, background=False):
        self.path, self.clock, self.error = os.fspath(path) if path else None, clock, None
        self.saves = None
        self.settled = threading.Event()
        self.settled.set()
        self.state = {"version": 1, "status": "normal", "revision": 0,
                      "reason": "", "updated_at": clock()}
        if self.path is None:
            return
        try:
            with open(self.path, encoding="utf-8") as stream:
                raw = stream.read(8193)
            value = json.loads(raw)
            if isinstance(value, dict):
                # Keep existing Legacy checkpoints readable; new saves omit retired metadata.
                for retired in ("token_hash", "label", "heartbeat_at", "legacy_log", "request_id", "acknowledged_at", "recovered_at"):
                    value.pop(retired, None)
                if value.get("status") == "writing":
                    value["status"] = "normal"  # Old everyday command: fresh acquisition.
                if value.get("status") in ("releasing", "reserved", "recovering"):
                    # Retired experiment handoff: someone else may have changed the lights.
                    value.update(status="uncertain", reason="An earlier experiment handoff did not finish.")
            if len(raw) > 8192 or not self._valid(value):
                raise ValueError("Invalid lighting recovery state")
            self.state = value
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
        keys = {"version", "status", "revision", "reason", "updated_at"}
        if not isinstance(value, dict) or set(value) != keys:
            return False
        if type(value["version"]) is not int or value["version"] != 1:
            return False
        if value["status"] not in cls.STATUSES or type(value["revision"]) is not int or value["revision"] < 0:
            return False
        if not isinstance(value["reason"], str) or len(value["reason"]) > 240:
            return False
        return type(value["updated_at"]) in (float, int) and 0 <= value["updated_at"] < 1e15

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
        if self.error:
            raise RuntimeError("Lighting recovery storage needs staff attention")
        if self.state["status"] != "normal" and not returning:
            raise RuntimeError("Lighting ownership or an earlier command is unresolved")
        if getattr(self, "request_id", None):
            raise RuntimeError("A lighting command is already pending")
        request_id = self._text(request_id, 160, "request ID")
        self.returning = returning
        # Save uncertainty before a bounded return; everyday writes stay in memory.
        if returning:
            self.mark_uncertain("Lighting connection check did not finish.")
        self.request_id = request_id

    def finish_write(self, request_id):
        if request_id != getattr(self, "request_id", None):
            raise ValueError("Lighting command result does not match")
        if self.returning:
            self._save(status="normal", reason="")
        self.request_id = None

    def mark_uncertain(self, reason):
        self.request_id = None
        self._save(status="uncertain", reason=self._text(reason, 240, "recovery reason"))

    def enter_legacy(self):
        if self.state["status"] not in ("normal", "uncertain") or getattr(self, "request_id", None):
            raise RuntimeError("Lighting ownership must be resolved before opening Legacy")
        self._save(status="legacy")

    def ready(self, stable=False):
        if stable is not True or self.state["status"] != "normal":
            raise RuntimeError("A bounded lighting connection check is required")

    def public(self):
        status = "uncertain" if self.error else self.state["status"]
        if self.pending and not self.error:
            status = "writing"
        elif getattr(self, "request_id", None):
            status = "returning" if self.returning else "writing"
        titles = {"normal": "Lighting ready", "writing": "Changing lighting",
                  "uncertain": "Lighting needs a check", "returning": "Checking lighting connection",
                  "legacy": "Legacy controls are open"}
        details = {"normal": "Current lighting is preserved.", "writing": "Waiting for lighting to finish saving or changing.",
                   "uncertain": "Press Check connection to stop Sun/Circ and confirm current light settings.",
                   "returning": "Stopping Sun/Circ and checking current settings. Light levels are kept.",
                   "legacy": "The original room app controls the lights. Return Home to use Beta."}
        return {"status": status, "title": titles[status], "detail": details[status],
                "can_check": not self.error and not self.pending and status in ("normal", "uncertain", "legacy"),
                "needs_staff": bool(self.error),
                "write_blocked": bool(self.error) or self.pending or status != "normal"}
