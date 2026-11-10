"""Ownership and read-first recovery on the existing panel event loop."""

from pathlib import Path
import os
import signal
import subprocess
import time
import tkinter as tk

from lighting_recovery import LightingRecovery
from preferences import sync_directory


class PanelRecovery:
    def init_recovery(self):
        path = getattr(self.args, "lighting_state", None)
        if self.args.live_lights and self.keep_switcher and not path:
            socket = getattr(self.args, "control_socket", None)
            path = (socket + ".lighting.json") if socket else str(Path.home() / ".cache/scr-panel/lighting-ownership.json")
        self.recovery = LightingRecovery(path, background=True)
        self.legacy_process = None
        self.legacy_previous_pid = None
        self.legacy_stopping_at = None
        self.legacy_killed = False
        self.legacy_returning = False
        self.reconnect_after_exit = False
        self.legacy_start_requested = self.mode == "original"
        if self.args.live_lights and (self.mode == "original" or self.recovery.state["status"] == "legacy"):
            self.mode = "room"

    def startup_lighting(self):
        if not self.args.live_lights:
            return
        self.legacy_previous_pid = self.previous_legacy_pid()
        if self.recovery.state["status"] == "legacy" or self.legacy_previous_pid is not None:
            self.stop_legacy()
        elif self.legacy_start_requested:
            self.show("original")
        elif not self.ownership_blocked():
            self.start_worker()

    def command_lost(self, reason):
        recovery = getattr(self, "recovery", None)
        if recovery is None or recovery.error:
            return
        if getattr(self, "legacy_returning", False):
            self.legacy_returning = False
            recovery.mark_uncertain(reason)
        elif getattr(recovery, "request_id", None):
            recovery.finish_write(recovery.request_id)
            self.reconnect_after_exit = True

    def ownership_blocked(self):
        recovery = getattr(self, "recovery", None)
        # The current write may finish, but no new actuator may start while it is pending.
        return bool(recovery and (recovery.error or recovery.pending or recovery.state["status"] != "normal"))

    def recovery_snapshot(self, ignore_touch=False):
        recovery = getattr(self, "recovery", None)
        if recovery is None:
            return {"status": "normal", "can_check": False, "write_blocked": False}
        result = recovery.public()
        if self.mode == "original":
            result.update(status="legacy", title="Legacy controls are open", detail="The original room app controls the lights. Return Home to use Beta.", can_check=False, write_blocked=True)
        elif self.recovery.pending and not self.recovery.error:
            result.update(status="writing", title="Saving lighting recovery", detail="Controls return after the recovery record is saved.", can_check=False, write_blocked=True)
        elif getattr(self, "legacy_returning", False):
            result.update(status="returning", title="Returning lighting control", detail="Stopping Sun/Circ and checking current settings. Light levels are kept.", can_check=False, write_blocked=True)
        elif self.light_state == "connecting" and not self.ownership_blocked():
            result.update(status="checking", title="Checking lighting connection", detail="Reading current settings. The lights will stay as they are.", can_check=False)
        elif result["status"] == "normal" and self.light_state not in ("ready", "applying"):
            result.update(status="offline", title="Lighting connection unavailable", detail="Check the connection without changing the lights.")
        if self.pending and self.pending.get("action") == "check":
            result.update(status="checking", title="Checking lighting", detail="Reading settings safely.", can_check=False)
        result["can_check"] = bool(result["can_check"] and self.args.live_lights and not self.pending and not self.queued_intent and not self.power_busy() and not self.release_target and not self.closing and (ignore_touch or not self.press_active) and self.mode != "original" and not self.legacy_alive() and getattr(self, "legacy_stopping_at", None) is None)
        if self.worker and (not getattr(self, "worker_ready", False) or self.worker.stdin.closed or self.worker.poll() is not None):
            result["can_check"] = False
        return result

    def recovery_contents(self, parent):
        card = tk.Frame(parent, bg=self.bg)
        card.pack(fill="x", pady=(6, 0))
        card._system = self.mode == "health"
        self.recovery_label = self.label(card, size=14, muted=True)
        self.recovery_label._card = card
        self.wrap_label(self.recovery_label).pack(fill="x")
        self.recovery_button = self.button(card, "Check connection", self.check_connection_after_release)
        self.recovery_button.config(font=(self.font_family, 15), pady=10)
        self.recovery_button.pack(anchor="w", pady=(6, 0))
        self.update_recovery_view()

    def update_recovery_view(self):
        # Keep the button in place during its own press; dispatch still checks
        # normal readiness after Tk's global release handler clears the touch.
        state = self.recovery_snapshot(ignore_touch=True)
        label = getattr(self, "recovery_label", None)
        if label is not None and label.winfo_exists():
            card = label._card
            detail = state.get("detail", "")
            if not card._system:
                detail = {
                    "returning": "Reading current settings before everyday controls return.",
                }.get(state["status"], detail)
            text = (state.get("title", "") + ". " if card._system else "") + detail
            if label.cget("text") != text:
                label.config(text=text)
            if not card._system and (not self.args.live_lights or state["status"] in ("normal", "writing")):
                if card.winfo_manager():
                    card.pack_forget()
            elif not card.winfo_manager():
                card.pack(fill="x", pady=(6, 0))
        button = getattr(self, "recovery_button", None)
        if button is not None and button.winfo_exists():
            checking = state["status"] == "checking"
            text = "Checking…" if checking else "Check connection"
            if button.cget("text") != text:
                button.config(text=text)
            style = "normal" if state["can_check"] else "disabled"
            if button.cget("state") != style:
                button.config(state=style)
            if state["can_check"] or checking:
                if not button.winfo_manager():
                    button.pack(anchor="w", pady=(6, 0))
            elif button.winfo_manager():
                button.pack_forget()

    def check_connection_after_release(self):
        def check_if_available():
            if self.recovery_snapshot()["can_check"]:
                self.check_connection()

        self.root.after_idle(check_if_available)

    def check_connection(self):
        if not self.recovery_snapshot()["can_check"]:
            raise RuntimeError("Wait for the current controller or ask the room host.")
        self.cancel_intent()
        if self.recovery.state["status"] != "normal":
            self.legacy_returning = True
            if self.worker:
                # return_legacy needs a fresh helper, never an already acquired one.
                self.release_target = "check_connection"
                if not self.request("release"):
                    self.release_target = None
                    self.legacy_returning = False
                    raise RuntimeError("The lighting connection could not be checked.")
            else:
                self.start_worker(legacy_return=True)
        elif self.worker:
            if not self.request("check"):
                raise RuntimeError("The lighting connection could not be checked.")
        else:
            self.start_worker()
        self.update_light_buttons()

    def legacy_paths(self):
        cache = Path.home() / ".cache/scr-panel"
        return cache / "original.pid", cache / "original.log"

    def previous_legacy_pid(self):
        """Trust only our PID file and the exact wrapper/classic-dir arguments."""
        try:
            pid = int(self.legacy_paths()[0].read_text().strip())
            if pid <= 1:
                return None
            args = Path("/proc", str(pid), "cmdline").read_bytes().split(b"\0")
            decoded = [os.fsdecode(arg) for arg in args if arg]
            directory = str(Path(self.args.classic_dir).resolve())
            index = decoded.index("--classic-dir")
            if (any(arg.endswith("/run_original.py") for arg in decoded)
                    and decoded[index + 1] == directory):
                return pid
        except (OSError, ValueError, IndexError):
            pass
        return None

    def legacy_alive(self):
        process = getattr(self, "legacy_process", None)
        if process is not None:
            return process.poll() is None
        pid = getattr(self, "legacy_previous_pid", None)
        return pid is not None and self.previous_legacy_pid() == pid

    def start_legacy(self):
        if self.worker is not None:
            raise RuntimeError("The lighting helper must exit before Legacy starts")
        if getattr(self, "legacy_process", None) is not None:
            return True
        pid_path, log_path = self.legacy_paths()
        try:
            pid_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            directory = str(Path(self.args.classic_dir).resolve())
            command = [self.args.classic_python, "-u", "-B",
                       str(Path(__file__).with_name("run_original.py").resolve()),
                       "--classic-dir", directory]
            with log_path.open("ab") as log:
                self.legacy_process = subprocess.Popen(command, cwd=directory, stdout=log,
                                                       stderr=subprocess.STDOUT, close_fds=True,
                                                       start_new_session=True)
            with pid_path.open("w") as stream:
                stream.write(str(self.legacy_process.pid) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            sync_directory(pid_path.parent)
            return True
        except OSError:
            if self.legacy_process is not None:
                self.stop_legacy()
            else:
                self.recovery.mark_uncertain("Legacy could not start. Press Check connection to return control.")
            self.status_text.set("Legacy could not start. Press Check connection to return control.")
            return False

    def signal_legacy(self, signum):
        process = getattr(self, "legacy_process", None)
        pid = process.pid if process is not None else getattr(self, "legacy_previous_pid", None)
        if pid is not None:
            try:
                os.killpg(pid, signum)
            except ProcessLookupError:
                # The retired boot launcher did not give Legacy its own group.
                # Its validated PID may still be present during the first upgrade.
                if process is None and self.previous_legacy_pid() == pid:
                    try:
                        os.kill(pid, signum)
                    except ProcessLookupError:
                        pass

    def stop_legacy(self):
        """Poll the child exit without blocking Tk; never acquire alongside Legacy."""
        if getattr(self, "legacy_stopping_at", None) is not None:
            return
        self.legacy_stopping_at = time.monotonic()
        self.legacy_killed = False
        self.signal_legacy(signal.SIGTERM)
        self.status_text.set("Closing Legacy before returning lighting control…")

    def poll_legacy(self):
        process = getattr(self, "legacy_process", None)
        if getattr(self, "legacy_stopping_at", None) is None:
            if process is not None and process.poll() is not None:
                self.stop_legacy()  # Window close and crash use exactly the Home path.
            else:
                return
        if self.legacy_alive():
            if not self.legacy_killed and time.monotonic() - self.legacy_stopping_at >= 3:
                self.signal_legacy(signal.SIGKILL)
                self.legacy_killed = True
            return
        # Also remove any remaining members after the leader exits.
        if not self.legacy_killed:
            self.signal_legacy(signal.SIGKILL)
        if process is not None:
            process.wait()  # poll already proved exit; reap without waiting on Tk.
        self.legacy_process = self.legacy_previous_pid = None
        self.legacy_stopping_at = None
        self.legacy_paths()[0].unlink(missing_ok=True)
        self.mode = "room"
        self.advanced_page = None
        self.render()
        self.update_navigation_buttons()
        if self.closing:
            self.finish_close()
        elif self.args.live_lights:
            self.start_worker(legacy_return=True)

    def recovery_result(self, request, response):
        action, state = request["action"], response["state"]
        if action == "return_legacy":
            self.legacy_returning = False
            if state == "ready" and response.get("fixtures") == 10 and not response.get("manual_blocked"):
                self.recovery.finish_write(request["request_id"])
            else:
                self.recovery.mark_uncertain("Lighting control could not be returned. Press Check connection to try again.")
        elif action in ("cct", "channels", "gradient", "programme", "blind"):
            # Confirmed or not, the panel still owns the lights. A failed result
            # ends the helper; a fresh one reads the lights before the next change.
            self.recovery.finish_write(request["request_id"])
            if state != "completed":
                self.reconnect_after_exit = True
        elif action == "acquire" and state == "ready":
            if response.get("fixtures") != 10:
                self.recovery.mark_uncertain("Installed lights differ from the expected ten.")
                self.fail_worker("Installed lights differ from the expected ten. Ask the room host.")
            else:
                self.recovery.ready(stable=True)
                if response.get("manual_blocked") is True:
                    self.lighting_feedback("Lights are changing, probably a programme. Press Stop before choosing a setting.")
        elif action == "check" and state == "checked":
            detail = response["detail"] if response.get("programme") in ("Sun", "Circ") else "Current light settings checked."
            self.lighting_feedback(detail)
        elif state == "failed" and action in ("acquire", "check"):
            self.lighting_feedback("Lighting could not be read. Press Check connection to try again.")
