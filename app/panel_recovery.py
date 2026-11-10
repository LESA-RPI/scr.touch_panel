"""Ownership and read-first recovery on the existing panel event loop."""

from pathlib import Path
import json
import os
import signal
import subprocess
import time
import tkinter as tk

from lighting_recovery import LightingRecovery


class PanelRecovery:
    def init_recovery(self):
        path = getattr(self.args, "lighting_state", None)
        if self.args.live_lights and self.keep_switcher and not path:
            socket = getattr(self.args, "control_socket", None)
            path = (socket + ".lighting.json") if socket else str(Path.home() / ".cache/scr-panel/lighting-ownership.json")
        self.recovery = LightingRecovery(path, background=True)
        self.observing = False
        self.recovery_check_at = None
        self.legacy_probe = None
        self.legacy_target = None
        self.legacy_returning = False
        self.reconnect_after_exit = False
        if self.recovery.state["status"] == "legacy":
            self.mode = "original"

    def command_lost(self, reason):
        """The helper ended before confirming its request.

        An everyday command leaves the panel as owner, so a fresh helper reads
        the lights again. Only an unfinished Legacy handoff needs staff.
        """
        recovery = getattr(self, "recovery", None)
        if recovery is None or recovery.error:
            return
        status = recovery.state["status"]
        if status == "writing":
            recovery.finish_write(recovery.state["request_id"])
            self.reconnect_after_exit = True
        elif status == "recovering":
            recovery.mark_uncertain(reason)

    def ownership_blocked(self):
        recovery = getattr(self, "recovery", None)
        # The current write may finish, but no new actuator may start while it is pending.
        return bool(recovery and (recovery.error or recovery.pending or recovery.state["status"] not in ("normal", "writing")))

    def recovery_snapshot(self, ignore_touch=False):
        recovery = getattr(self, "recovery", None)
        if recovery is None:
            return {"status": "normal", "can_check": False, "write_blocked": False}
        result = recovery.public()
        if self.mode == "original":
            result.update(status="legacy", title="Legacy controls are open", detail="The original room app controls the lights. Return Home to use Beta.", can_check=False, write_blocked=True)
        elif self.recovery.pending and not self.recovery.error:
            result.update(status="writing", title="Saving lighting recovery", detail="Controls return after the recovery record is saved.", can_check=False, write_blocked=True)
        elif self.recovery.state["status"] == "legacy":
            result.update(status="needs_staff", title="Legacy still owns lighting", detail="Use Legacy for room controls. Before Beta reconnects, the room host must check that Legacy programmes and pending commands have stopped.", can_check=False, needs_staff=True, write_blocked=True)
        elif getattr(self, "legacy_returning", False) and result["status"] in ("recovering", "writing"):
            result.update(status="returning", title="Returning lighting control", detail="Finishing Legacy programmes and checking current settings. The room stays at its current light level.", can_check=False, write_blocked=True)
        elif self.observing or (self.light_state == "connecting" and not self.ownership_blocked()):
            result.update(status="checking", title="Checking lighting connection", detail="Reading current settings. The lights will stay as they are.", can_check=False)
        elif result["status"] == "recovering":
            result["status"] = "returning"
        elif result["status"] == "uncertain":
            result.update(status="needs_staff", title="Lighting result unconfirmed")
        elif result["status"] == "normal" and self.light_state not in ("ready", "applying"):
            result.update(status="offline", title="Lighting connection unavailable", detail="Check the connection without changing the lights.")
        if self.pending and self.pending.get("action") == "check":
            result.update(status="checking", title="Checking lighting", detail="Reading settings safely.", can_check=False)
        result["can_check"] = bool(result["can_check"] and self.args.live_lights and not self.pending and not self.queued_intent and not self.power_busy() and not self.release_target and not self.closing and (ignore_touch or not self.press_active) and self.mode != "original")
        if self.worker and (not getattr(self, "worker_ready", False) or self.worker.stdin.closed or self.worker.poll() is not None):
            result["can_check"] = False
        if self.recovery_check_at is not None and result["needs_staff"]:
            result["detail"] = "Current settings were read. Staff must confirm the previous controller has stopped and no lighting request remains pending."
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
                    "needs_staff": "Use Legacy for lighting, or ask the room host." if self.recovery.state["status"] == "legacy" else "Read settings safely, or ask the room host.",
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
        self.recovery_check_at = None
        if self.worker:
            if not self.request("check"):
                raise RuntimeError("The lighting connection could not be checked.")
            self.lighting_feedback("Checking current light settings. No lighting command is sent.")
        elif self.recovery.state["status"] == "normal":
            self.start_worker()  # Acquisition is read-only; no old command is replayed.
        else:
            self.start_worker(observe_only=True)
        self.update_light_buttons()

    def begin_legacy_return(self, mode, advanced_page):
        """Cover Legacy input, then wait for its unchanged callback loop to respond."""
        if self.legacy_probe is not None:
            return
        self.root.deiconify()
        self.root.lift()
        self.dock.withdraw()
        self.status_text.set("Checking Legacy has finished before returning to Beta…")
        try:
            original = []
            for proc in Path("/proc").iterdir():
                if not proc.name.isdigit():
                    continue
                try:
                    args = proc.joinpath("cmdline").read_bytes().decode().split("\0")
                    if any(a.endswith("/run_original.py") for a in args):
                        original.append(int(proc.name))
                except OSError:
                    pass
            pid, = original
            script = str(Path(__file__).with_name("original_idle.py"))
            self.legacy_probe = subprocess.Popen([self.args.adapter_python, "-B", script, "--pid", str(pid)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True)
            self.legacy_probe_started = time.monotonic()
            self.legacy_target = (mode, advanced_page)
            self.cover_legacy(force=True)  # Hide Legacy while its idle check runs.
        except (OSError, ValueError):
            self.legacy_return_failed()

    def legacy_pid(self):
        """Legacy that hides itself on request advertises its PID; older ones are never signalled."""
        try:
            pid = int((Path.home() / ".cache/scr-panel/original.pid").read_text().strip())
            arguments = Path("/proc", str(pid), "cmdline").read_bytes().split(b"\0")
        except (OSError, ValueError):
            return None
        return pid if any(a.endswith(b"/run_original.py") for a in arguments) else None

    def cover_legacy(self, force=False):
        """Keep the hidden Legacy window from taking taps while Beta is on screen."""
        now = time.monotonic()
        if not getattr(self, "keep_switcher", False) or (not force and now - getattr(self, "legacy_covered_at", 0) < 1):
            return
        self.legacy_covered_at = now
        pid = self.legacy_pid()
        if pid:
            try:
                show = self.mode == "original" and getattr(self, "legacy_probe", None) is None
                os.kill(pid, signal.SIGUSR1 if show else signal.SIGUSR2)
            except OSError:
                pass

    def original_log_position(self):
        try:
            value = (Path.home() / ".cache/scr-panel/original.log").stat()
            return dict(device=value.st_dev, inode=value.st_ino, size=value.st_size)
        except OSError:
            return None

    def legacy_callbacks_clean(self):
        checkpoint = self.recovery.state.get("legacy_log")
        current = self.original_log_position()
        if not checkpoint or not current or not 0 <= current["size"] - checkpoint["size"] <= 65536:
            return False
        try:
            with (Path.home() / ".cache/scr-panel/original.log").open("rb") as stream:
                stream.seek(checkpoint["size"])
                added = stream.read(65537)
            return self.recovery.legacy_log_unchanged(current, added)
        except OSError:
            return False

    def legacy_return_failed(self):
        # Failure of our read-only observer does not revoke the original owner's
        # control. Keep that owner available; Beta still cannot acquire lighting.
        self.legacy_target = None
        self.mode = "room"
        self.show("health", advanced_page="system")
        self.status_text.set("Legacy is still busy or unavailable. Ask the room host before reconnecting.")

    def poll_legacy_return(self):
        probe = getattr(self, "legacy_probe", None)
        if probe is None:
            return
        if probe.poll() is None:
            if time.monotonic() - self.legacy_probe_started > 5:
                probe.kill()  # Only this read-only probe; never the original app.
            return
        try:
            raw = probe.stdout.read(4097)
            reply = json.loads(raw)
            valid = probe.returncode == 0 and reply.get("idle") is True and len(raw) <= 4096
        except (OSError, ValueError):
            valid = False
        finally:
            probe.stdout.close()
            probe.stderr.close()
            self.legacy_probe = None
        if not valid:
            self.legacy_return_failed()
            return
        target, self.legacy_target = self.legacy_target, None
        if not self.legacy_callbacks_clean():
            self.legacy_return_failed()
            return
        self.recovery.leave_legacy(idle_confirmed=True, callback_clean=True)
        self.legacy_returning = True
        self.show(target[0], advanced_page=target[1])

    def recovery_result(self, request, response):
        action, state = request["action"], response["state"]
        if action == "return_legacy":
            self.legacy_returning = False
            if state == "ready" and response.get("fixtures") == 10 and not response.get("manual_blocked"):
                self.recovery.finish_write(request["request_id"])
            else:
                self.recovery.mark_uncertain("Legacy lighting control could not be returned. Ask the room host.")
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
            self.recovery_check_at = time.monotonic()
            detail = response["detail"] if response.get("programme") in ("Sun", "Circ") else "Current light settings checked."
            self.lighting_feedback(detail + " " + ("Staff must confirm the handoff before controls return." if self.ownership_blocked() else "No lighting command was sent."))
            if self.observing:
                self.request("release")
        elif state == "failed" and action in ("acquire", "check"):
            if not self.observing and self.recovery.state["status"] == "recovering":
                self.recovery.mark_uncertain("Lighting could not be read after a handoff.")
            self.lighting_feedback("Lighting could not be read. Press Check connection to try again.")
