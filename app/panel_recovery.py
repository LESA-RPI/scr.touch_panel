"""Ownership and read-first recovery on the existing panel event loop."""

from pathlib import Path
import json
import os
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
        self.recovery = LightingRecovery(path)
        self.observing = False
        self.recovery_check_at = None
        self.reservation_token = None
        self.reservation_label = None
        self.legacy_probe = None
        self.legacy_target = None
        self.legacy_returning = False
        if self.recovery.state["status"] == "legacy":
            self.mode = "original"

    def ownership_blocked(self):
        recovery = getattr(self, "recovery", None)
        # The current write may finish, but no new actuator may start while it is pending.
        return bool(recovery and recovery.state["status"] not in ("normal", "writing"))

    def recovery_snapshot(self):
        recovery = getattr(self, "recovery", None)
        if recovery is None:
            return {"status": "normal", "can_check": False, "write_blocked": False}
        result = recovery.public()
        if self.mode == "original":
            result.update(status="legacy", title="Legacy controls are open", detail="The original room app controls the lights. Return Home to use Beta.", can_check=False, write_blocked=True)
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
        result["can_check"] = bool(result["can_check"] and self.args.live_lights and not self.pending and not self.queued_intent and not self.power_busy() and not self.release_target and not self.closing and not self.running and not self.press_active and self.mode != "original")
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
        self.recovery_button = self.button(card, "Check connection", self.check_connection)
        self.recovery_button.config(font=(self.font_family, 15), pady=10)
        self.recovery_button.pack(anchor="w", pady=(6, 0))
        self.update_recovery_view()

    def update_recovery_view(self):
        state = self.recovery_snapshot()
        label = getattr(self, "recovery_label", None)
        if label is not None and label.winfo_exists():
            card = label._card
            detail = state.get("detail", "")
            if not card._system:
                detail = {
                    "needs_staff": "Use Legacy for lighting, or ask the room host." if self.recovery.state["status"] == "legacy" else "Read settings safely, or ask the room host.",
                    "reserved": "Controls return after the experiment completes its cleanup.",
                    "releasing": "Waiting for the panel controller to finish and stop.",
                    "returning": "Reading current settings before everyday controls return.",
                }.get(state["status"], detail)
            label.config(text=(state.get("title", "") + ". " if card._system else "") + detail)
            if not card._system and (not self.args.live_lights or state["status"] in ("normal", "writing")):
                card.pack_forget()
            else:
                card.pack(fill="x", pady=(6, 0))
        button = getattr(self, "recovery_button", None)
        if button is not None and button.winfo_exists():
            button.config(state="normal" if state["can_check"] else "disabled")
            if state["can_check"]:
                button.pack(anchor="w", pady=(6, 0))
            else:
                button.pack_forget()

    def check_connection(self):
        if not self.recovery_snapshot()["can_check"]:
            raise RuntimeError("Wait for the current controller or ask the room host.")
        self.cancel_intent()
        self.recovery_check_at = None
        if self.worker:
            if not self.request("check"):
                raise RuntimeError("The lighting connection could not be checked.")
        elif self.recovery.state["status"] == "normal":
            self.start_worker()  # Acquisition is read-only; no old command is replayed.
        else:
            self.start_worker(observe_only=True)
        self.update_recovery_view()

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
        except (OSError, ValueError):
            self.legacy_return_failed()

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

    def handoff(self, action, args):
        if self.closing or self.release_target or self.pending or self.queued_intent or self.press_active or self.running or self.power_busy() or self.mode == "original" or self.legacy_probe is not None:
            raise RuntimeError("Finish the current panel action before changing lighting ownership.")
        if action == "reserve":
            if not self.keep_switcher or not self.worker or self.light_state != "ready" or self.programme:
                raise RuntimeError("Lighting must be ready with no programme before an experiment.")
            self.recovery.begin_reservation(args["token"], args["label"])
            self.reservation_token, self.reservation_label = args["token"], args["label"]
            self.cancel_intent()
            self.release_target = "experiment"
            if not self.request("release"):
                self.release_target = None
                self.recovery.mark_uncertain("Panel lighting release could not be confirmed.")
                raise RuntimeError("Experiment handoff failed. Do not start lighting control.")
        elif action == "heartbeat":
            self.recovery.heartbeat(args["token"])
        elif action in ("finish", "recover"):
            if self.worker:
                raise RuntimeError("Wait for the previous lighting helper to stop.")
            if action == "finish":
                self.recovery.finish(**args)
            else:
                self.recovery.acknowledge(**args)
            self.start_worker()
        else:
            raise ValueError("Unsupported handoff action")
        self.emit("lighting_ownership", action=action, status=self.recovery.state["status"])
        self.update_light_buttons()
        return {"ok": True, "code": 202, "detail": "Ownership request accepted. Check lighting_recovery before proceeding."}

    def recovery_result(self, request, response):
        action, state = request["action"], response["state"]
        if action == "return_legacy":
            self.legacy_returning = False
            if state == "ready" and response.get("fixtures") == 10 and not response.get("manual_blocked"):
                self.recovery.confirm_write(request["request_id"])
            else:
                self.recovery.mark_uncertain("Legacy lighting control could not be returned. Ask the room host.")
        elif action in ("cct", "channels", "gradient", "programme", "blind"):
            if state == "completed":
                self.recovery.confirm_write(request["request_id"])
            else:
                self.recovery.mark_uncertain("A lighting or blind command result was not confirmed.")
        elif action == "acquire" and state == "ready":
            if response.get("manual_blocked") is True or response.get("fixtures") != 10:
                self.recovery.mark_uncertain("Current lighting is changing or incomplete. Check the room controller.")
                self.fail_worker("Lighting is changing. Ask the room host before taking control.")
            else:
                self.recovery.ready(stable=True)
        elif action == "check" and state == "checked":
            self.recovery_check_at = time.monotonic()
            self.lighting_feedback("Current light settings checked. " + ("Staff must confirm ownership before controls return." if self.ownership_blocked() else "No lighting command was sent."))
            if self.observing:
                self.request("release")
        elif state == "failed" and action in ("acquire", "check"):
            if not self.observing and (self.recovery.state["status"] == "recovering" or response.get("outcome_unknown") is True):
                self.recovery.mark_uncertain("Lighting readback or ownership could not be confirmed.")
            self.lighting_feedback("Lighting could not be checked. Ask the room host; no command was repeated.")

    def recovery_exit(self, target, returncode=0):
        if target == "experiment":
            if self.release_confirmed and returncode == 0:
                self.recovery.reserve(self.reservation_token, self.reservation_label, released=True, helper_exited=True)
                self.light_state = "disconnected"
                self.lighting_feedback("Lighting reserved for an experiment. Everyday controls return after verified cleanup.")
            else:
                self.recovery.mark_uncertain("Experiment handoff did not confirm a preserved release.")
        self.observing = False
