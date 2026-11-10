"""Small appearance preferences; atomic writes stay off the Tk thread."""

import json
import os
import tempfile
import threading


def sync_directory(directory):
    """Persist the renamed filename on POSIX, after the file itself is synced."""
    if os.name != "posix":
        return  # Windows does not expose a portable directory fsync through os.
    descriptor = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def validated(value):
    if not isinstance(value, dict):
        raise ValueError("Expected an appearance settings object")
    allowed = {
        "theme": ("auto", "light", "dark"),
        "clock_format": ("12", "24"),
        "tips": ("on", "off"),
        "temperature_unit": ("c", "f"),
        "blinds_display": ("disabled", "hidden"),
    }
    result = {}
    if "blinds_enabled" in value:
        if type(value["blinds_enabled"]) is not bool:
            raise ValueError("Invalid blinds_enabled")
        result["blinds_enabled"] = value["blinds_enabled"]
    for key, choices in allowed.items():
        if key in value:
            if value[key] not in choices:
                raise ValueError("Invalid " + key)
            result[key] = value[key]
    for key in ("light_at", "dark_at"):
        if key in value:
            if type(value[key]) is not int or not 0 <= value[key] < 1440:
                raise ValueError("Invalid " + key)
            result[key] = value[key]
    if "idle_timeout" in value:
        if type(value["idle_timeout"]) is not int or value["idle_timeout"] not in (
            0,
            60,
            300,
            900,
        ):
            raise ValueError("Invalid idle_timeout")
        result["idle_timeout"] = value["idle_timeout"]
    if result.get("light_at", 420) == result.get("dark_at", 1140):
        raise ValueError("Theme schedule times must differ")
    return result


def load(path, defaults=None):
    if not path or not os.path.exists(path):
        return {}, None
    try:
        with open(path) as stream:
            text = stream.read(4097)
        if len(text) > 4096:
            raise ValueError("Appearance settings are too large")
        value = validated(json.loads(text))
        if defaults:
            merged = dict(defaults)
            merged.update(value)
            validated(merged)
        return value, None
    except (IOError, OSError, ValueError, RecursionError) as error:
        return {}, str(error)


class Preferences(object):
    """One worker, one pending snapshot; keep only the latest selection."""

    def __init__(self, path):
        self.path = path
        self.condition = threading.Condition()
        self.pending = None
        self.writing = False
        self.error = None
        self.closing = False
        self.done = threading.Event()
        self.settled = threading.Event()
        self.settled.set()
        self.thread = threading.Thread(target=self._run, name="scr-panel-preferences")
        self.thread.daemon = True
        self.thread.start()

    def save(self, value):
        value = validated(value)
        with self.condition:
            if self.closing:
                return
            if self.done.is_set():
                self.error = self.error or "Appearance settings writer stopped"
                return
            self.pending = value
            self.settled.clear()
            self.condition.notify()

    def close(self):
        with self.condition:
            self.closing = True
            self.condition.notify()

    def _run(self):
        finished = False
        try:
            while True:
                with self.condition:
                    while self.pending is None and not self.closing:
                        self.condition.wait()
                    if self.pending is None:
                        finished = True
                        return
                    value, self.pending = self.pending, None
                    self.writing = True
                temporary = None
                try:
                    directory = os.path.dirname(os.path.abspath(self.path))
                    if not os.path.isdir(directory):
                        os.makedirs(directory)
                    descriptor, temporary = tempfile.mkstemp(
                        prefix=".appearance-", dir=directory
                    )
                    with os.fdopen(descriptor, "w") as stream:
                        json.dump(value, stream, sort_keys=True)
                        stream.write("\n")
                        stream.flush()
                        os.fsync(stream.fileno())
                    getattr(os, "replace", os.rename)(temporary, self.path)
                    temporary = None
                    sync_directory(directory)
                    self.error = None
                except (IOError, OSError, ValueError) as error:
                    self.error = str(error) or "Appearance settings write failed"
                finally:
                    if temporary:
                        try:
                            os.unlink(temporary)
                        except OSError as error:
                            self.error = (
                                self.error or str(error)
                                or "Appearance temporary file cleanup failed"
                            )
                    with self.condition:
                        self.writing = False
                        if self.pending is None:
                            self.settled.set()
        finally:
            if not finished and not self.error:
                self.error = "Appearance settings writer stopped before shutdown"
            self.settled.set()
            self.done.set()
