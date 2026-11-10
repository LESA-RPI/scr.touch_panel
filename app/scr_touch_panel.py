#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Independent SCR touchscreen. Author: Diyanko Bhowmik, with Codex assistance.

Python 3.11+, installed Tk and Pillow. A private UI journal works standalone.
An opt-in adapter uses existing ROS lights.
"""

from __future__ import print_function
import argparse
import base64
import datetime
import json
import math
import os
import select
import signal
import subprocess
import sys
import threading
import time
import traceback
import uuid
from io import BytesIO, FileIO
from scr_touch_panel_lights import PRESETS, setter_words
from event_journal import EventJournal
from preferences import Preferences, load as load_preferences
import weather as weather_data
import panel_icons
from design_tokens import THEMES
from touch_slider import TouchSlider
from room_controls import (
    PREVIOUS_ON,
    BLIND_ACTIONS,
    blind_readiness,
)
from panel_power import PowerActions
from panel_version import VERSION, BUILD_COMMIT

try:
    import Tkinter as tk
    from tkFont import Font
except ImportError:
    import tkinter as tk
    from tkinter.font import Font

from panel_common import (
    FONT,
    TIPS,
    boot_identity,
    clock_minutes,
    confirmation_age,
    confirmed_power,
    confirmed_scene,
    health,
    light_selection,
    monotonic,
    scheduled_theme,
    set_changed,
)


import ui_widgets
from ui_frame import PanelFrame
from page_home import HomePage
from page_lights import LightsPage
from page_guide import GuidePage
from page_settings import SettingsPage
from page_saver import SaverPage
from panel_recovery import PanelRecovery

RECONNECTING = "That change could not be confirmed. Reading the lights again…"


class Panel(PanelFrame, HomePage, LightsPage, GuidePage, SettingsPage, SaverPage, PanelRecovery):
    def __init__(self, args):
        self.args = args
        saved, preference_error = load_preferences(
            getattr(args, "preferences", None),
            {"light_at": args.light_at, "dark_at": args.dark_at},
        )
        for key, value in saved.items():
            setattr(args, key, value)
        self.preferences = (
            Preferences(args.preferences)
            if getattr(args, "preferences", None)
            else None
        )
        self.preference_error = preference_error
        self.weather_worker, self.weather_started = None, None
        self.weather_checked, self.weather_good, self.weather_last_text = (
            -900,
            None,
            None,
        )
        self.weather_reading, self.weather_rendered_minute = None, None
        self.settings_category = "appearance"
        self.advanced_page, self.last_advanced_page = None, "lighting"
        self.lighting_tab = "white"
        self.guide_page, self.support_page = -1, 0
        self.guide_section = "room"
        self.support_commands_visible = False
        self.support_step = 0
        self.started, self.run_id, self.sequence = monotonic(), uuid.uuid4().hex, 0
        self.control_sequence = 0
        self.boot_id, self.last_touch = boot_identity(), self.started
        self.idle_timeout = getattr(args, "idle_timeout", 300)
        self.blinds_display = getattr(args, "blinds_display", "disabled")
        self.blinds_enabled = getattr(args, "blinds_enabled", False)
        self.blind_controller = None
        self.blinds_connected = False
        self.light_capabilities = {}
        self.programme = None
        self.programme_buttons = []
        self.blind_buttons = []
        self.idle_active, self.press_active = False, False
        self.clock_24 = getattr(args, "clock_format", "24") == "24"
        self.temperature_unit = getattr(args, "temperature_unit", "f")
        self.help_on = getattr(args, "tips", "on") == "on"
        self.status_worker, self.status_started, self.room_status_at = None, None, -60
        self.room_status = "Room services: not checked"
        self.room_status_state = "unavailable"
        self.room_services = []
        self.room_status_observed = self.room_status_good_at = None
        self.closed, self.closing = False, None
        self.keep_switcher = getattr(args, "keep_switcher", False)
        self.mode, self.section, self.blank_return = (
            (getattr(args, "start_mode", "room") if self.keep_switcher else "room"),
            "basic",
            "room",
        )
        self.trial_deadline = (
            self.started + args.duration
            if args.duration and self.mode != "original"
            else None
        )
        self.hold = self.hold_origin = None
        self.theme_choice, self.theme = args.theme, None
        self.health_at, self.health_cache = -10, {}
        self.health_worker, self.health_pending = None, None
        self.worker, self.pending, self.worker_buffer = None, None, ""
        self.release_confirmed = self.light_changes_requested = False
        self.queued_intent, self.intent_timer, self.slider_drag = None, None, None
        self.view_generation = 0
        self.light_state, self.release_target = "disconnected", None
        self.confirmed_light = "Not checked"
        self.confirmed_at, self.light_message = None, "Lighting not connected"
        self.confirmed_power = None
        self.confirmed_scene = None
        self.home_power_buttons = []
        self.scene_buttons = []
        self.light_buttons = []
        self.power = PowerActions(
            enabled=sys.platform.startswith("linux")
            and not args.windowed
            and args.live_lights
            and bool(args.journal)
        )
        self.power_deadline = self.power_sequence = None
        self.power_cleanup_confirmed = self.power_checkpoint_saved = False
        self.power_dialog, self.power_buttons = None, []
        self.last_heartbeat, self.request_seq = -10, 0
        self.init_recovery()
        self.journal = EventJournal(args.journal, sys.stdout)
        self.root = tk.Tk()
        self.font_family = Font(root=self.root, font=(FONT, 19)).actual("family")
        self.icon_cache = {}
        self.body_cache, self.detail_cache = {}, {}
        self.body_key = self.advanced_detail_key = None
        self.root.title("LESA Smart Conference Room · Beta")
        if (self.root.winfo_screenwidth(), self.root.winfo_screenheight()) != (
            1280,
            800,
        ) and not args.windowed:
            self.root.destroy()
            self.journal.close()
            raise ValueError("Expected 1280x800; use --windowed for local review")
        self.root.geometry("1280x800+0+0")
        self.root.overrideredirect(not args.windowed)
        self.root.attributes("-topmost", True)
        self.root.bind("<Escape>", lambda event: self.close("escape"))
        self.root.protocol("WM_DELETE_WINDOW", lambda: self.close("window_close"))
        self.root.bind_all("<ButtonRelease-1>", self.slider_released, add="+")
        self.root.bind_all(
            "<ButtonPress-1>", lambda event: self.activity(True), add="+"
        )
        self.root.bind_all(
            "<ButtonRelease-1>", lambda event: self.activity(False), add="+"
        )
        self.root.bind_all("<KeyPress>", lambda event: self.activity(), add="+")
        self.root.bind_all("<KeyPress>", lambda event: self.button_focus(True), add="+")
        self.root.bind_all("<ButtonPress-1>", lambda event: self.button_focus(False), add="+")
        self.root.bind_class(
            "PanelWake", "<ButtonPress-1>", lambda event: self.wake_idle(True)
        )
        self.root.bind_class(
            "PanelWake", "<ButtonRelease-1>", lambda event: self.wake_idle(False)
        )
        self.root.bind_class(
            "PanelWake",
            "<B1-Motion>",
            lambda event: "break" if self.idle_active else None,
        )
        self.root.bind_class(
            "PanelWake", "<KeyPress>", lambda event: self.wake_idle(False)
        )
        self.cct, self.intensity = tk.IntVar(value=5800), tk.IntVar(value=0)
        self.controls_known = {"white": False, "channels": False}
        self.channel_values = [tk.IntVar(value=0) for _ in range(8)]
        self.status_text = tk.StringVar(
            value="Use Lights on or Lights off. Fine adjustments are in Lights."
        )
        self.light_text = tk.StringVar(
            value="Lighting not connected - controls are unavailable"
        )
        self.connection_text = tk.StringVar()
        self.visitor_time, self.visitor_date = tk.StringVar(), tk.StringVar()
        self.idle_digits, self.idle_period = tk.StringVar(), tk.StringVar()
        self.visitor_time.trace_add("write", self.sync_idle_clock)
        self.preference_text = tk.StringVar(value=self.preference_summary())
        self.weather_text = tk.StringVar(value="Not configured. A location is needed.")
        self.home_weather_text = tk.StringVar(value="Weather not configured")
        self.weather_temperature = tk.StringVar(value="—")
        self.weather_condition = tk.StringVar(value="Weather unavailable")
        self.power_text = tk.StringVar(value=self.power.message)
        self.artwork = None
        if args.logo:
            from PIL import Image

            artwork = Image.open(args.logo)
            # Viewport of the supplied 900-square logo. Keep its original pixels and colours.
            if artwork.size == (900, 900):
                artwork = artwork.crop((55, 160, 780, 578))
            resampling = getattr(Image, "Resampling", Image)
            artwork.thumbnail((116, 66), resampling.LANCZOS)
            buffer = BytesIO()
            artwork.save(buffer, format="PNG")
            self.artwork = tk.PhotoImage(
                data=base64.b64encode(buffer.getvalue()).decode("ascii")
            )
        self.dock = tk.Toplevel(self.root)
        self.dock.overrideredirect(True)
        self.dock.attributes("-topmost", True)
        self.dock.withdraw()
        self.set_theme()
        self.startup_lighting()
        self.repeat(self.tick, 1000)
        self.root.after(100, self.poll_worker)
        self.emit(
            "panel_opened",
            duration_s=args.duration,
            author="Diyanko Bhowmik",
        )
        self.control_bridge = None
        if getattr(args, "control_socket", None):
            from panel_control import Bridge

            try:
                self.control_bridge = Bridge(args.control_socket)
            except (OSError, ValueError) as error:
                self.status_text.set(
                    "Browser controls unavailable. The touch panel still works."
                )
                self.emit("browser_bridge_unavailable", detail=str(error))
            else:
                self.repeat(self.poll_control, 80)

    def repeat(self, step, delay, due=None):
        """Run one loop step, then schedule the next unless it returned False or the
        panel closed. An unexpected error is logged once per step; the loop goes on."""
        again = True
        started = monotonic()
        try:
            again = step() is not False
        except Exception:
            failed = self.__dict__.setdefault("loop_failures", set())
            if step.__name__ not in failed:
                failed.add(step.__name__)
                traceback.print_exc()
        if again and not self.closed:
            self.note_slow_ui(step.__name__, started, due)
            next_due = monotonic() + delay / 1000
            self.root.after(delay, lambda: self.repeat(step, delay, next_due))

    def note_slow_ui(self, step, started, due=None):
        now = monotonic()
        duration, lateness = now - started, max(0, started - due) if due else 0
        previous = self.__dict__.setdefault("slow_ui_reported", {})
        if max(duration, lateness) >= 0.2 and now - previous.get(step, -30) >= 30:
            previous[step] = now
            try:
                self.emit("slow_ui_callback", callback=step,
                          duration_ms=round(duration * 1000, 1), delay_ms=round(lateness * 1000, 1))
            except Exception:
                pass  # Optional timing diagnostics must never end a UI loop.

    def poll_control(self):
        if self.closed or self.closing or self.control_bridge is None:
            return False
        import panel_remote

        self.refresh_resources()
        self.control_bridge.drain(
            lambda: panel_remote.snapshot(self),
            lambda request: panel_remote.execute(self, request),
        )

    def emit(self, event, **values):
        self.sequence += 1
        # Timing logs must not invalidate an otherwise current control command.
        if event != "slow_ui_callback":
            self.control_sequence += 1
        values.update(
            version=1,
            event=event,
            mode=self.mode,
            panel_run_id=self.run_id,
            boot_id=self.boot_id,
            sequence=self.sequence,
            utc=datetime.datetime.now(datetime.timezone.utc)
            .replace(tzinfo=None)
            .isoformat()
            + "Z",
            elapsed_s=round(monotonic() - self.started, 3),
            recording=False,
        )
        line = json.dumps(values, sort_keys=True) + "\n"
        try:
            self.journal.append(
                line, self.sequence, durable=event == "power_requested"
            )
        except (IOError, OSError) as error:
            if event == "power_requested":
                raise
            self.status_text.set("Panel journal unavailable: " + str(error))
        return self.sequence

    def label(self, parent, text="", size=20, muted=False):
        return ui_widgets.label(self, parent, text, size, muted)

    def wrap_label(self, label):
        """Wrap to allocated width, including narrower settings/weather cards."""
        label.config(wraplength=600)

        def fit(event):
            width = max(
                1, event.width - 2 * label.winfo_pixels(str(label.cget("padx"))) - 8
            )
            if label.winfo_pixels(str(label.cget("wraplength"))) != width:
                label.config(wraplength=width)

        label.bind("<Configure>", fit)
        return label

    def lighting_feedback(self, message):
        self.light_message = message
        self.refresh_confirmation_age()

    def refresh_confirmation_age(self):
        age = confirmation_age(monotonic(), getattr(self, "confirmed_at", None))
        suffix = " / " + age if age else ""
        text = (
            self.light_message
            + "\nLast confirmed drive: "
            + getattr(self, "confirmed_light", "Not checked")
            + suffix
        )
        if not hasattr(self.light_text, "get") or self.light_text.get() != text:
            self.light_text.set(text)
        if hasattr(self, "feedback_message"):
            recovery = self.recovery_snapshot() if self.args.live_lights else {"status": "normal"}
            set_changed(
                self.feedback_message,
                recovery["title"] if recovery["status"] not in ("normal", "writing") else self.light_message.replace(" input / level ", " · level "),
            )
            recent = self.confirmed_light.replace(" input / level ", " · level ")
            if age:
                recent = "Last confirmed: " + {
                    "on": "Lights on · ", "off": "Lights off · "
                }.get(getattr(self, "confirmed_power", None), "") + recent + suffix
            elif recent == "Not checked":
                recent = "Lighting not checked yet."
            set_changed(self.feedback_detail, recent)
            card = getattr(self, "light_feedback_card", None)
            if card is not None and card.winfo_exists():
                routine = (
                    self.light_message in ("Light settings confirmed.", "Lighting ready.")
                    and self.light_state == "ready"
                    and recovery["status"] == "normal"
                    and not any(getattr(self, name, None) for name in (
                        "pending", "queued_intent", "release_target", "closing"
                    ))
                )
                message = card._message
                if routine and message.winfo_manager():
                    message.pack_forget()
                elif not routine and not message.winfo_manager():
                    message.pack(fill="x", before=card._detail)
                colour = self.warning if self.light_state == "failed" or recovery.get("needs_staff") else self.ink
                if message.cget("fg") != colour:
                    message.config(fg=colour)
        self.update_power_highlights()


    def update_power_highlights(self):
        if not (getattr(self, "home_power_buttons", []) or getattr(self, "scene_buttons", [])):
            self.update_readback_labels()
            return
        intent = getattr(self, "pending", None)
        queued = getattr(self, "queued_intent", None)
        action = intent.get("action") if intent else queued[0] if queued else None
        args = intent.get("arguments", {}) if intent else queued[1] if queued else {}
        values = args.get("values") if action == "channels" else None
        sending = ("off" if not any(values) else "on") if values is not None else None
        for button, power, title in getattr(self, "home_power_buttons", []):
            if button.winfo_exists():
                active = self.light_state == "applying" and power == sending
                button.config(text=title + ("\nSending…" if active else ""))
                button.style(sending=active)
                if self.light_state == "applying" and not active:
                    button.config(bg=self.surface, fg=self.muted, image=self.icon(power, self.muted, 38), highlightbackground=self.border)
                    for edge in button._edges:
                        edge.config(bg=self.border)
                else:
                    button.config(image=self.icon(power, self.bg, 38))
        for button, name in getattr(self, "scene_buttons", []):
            if button.winfo_exists():
                current = self.light_state == "ready" and self.confirmed_scene == name and not self.ownership_blocked()
                button._current.config(text="Current" if current else "")
        self.update_readback_labels()

    def activity(self, pressed=None):
        self.last_touch = monotonic()
        if pressed is not None:
            self.press_active = pressed

    def idle_eligible(self):
        return (
            self.idle_timeout > 0
            and self.mode
            in ("room", "advanced", "settings", "health", "guide", "support", "about")
            and self.light_state in ("ready", "disconnected")
            and not self.power_busy()
            and not self.ownership_blocked()
            and not any(
                (
                    self.pending,
                    self.queued_intent,
                    self.intent_timer,
                    self.slider_drag,
                    self.release_target,
                    self.closing,
                    self.press_active,
                )
            )
        )

    def update_idle(self):
        if self.idle_active:
            if self.light_state == "failed":
                self.return_from_idle()
            return
        if self.idle_eligible() and monotonic() - self.last_touch >= self.idle_timeout:
            self.idle_active = True
            self.show("visitor")
            self.status_text.set("Touch anywhere for Home and light controls.")
            self.root.focus_set()

    def install_wake_bindings(self):
        def visit(widget):
            if widget == self.dock:
                return
            tags = widget.bindtags()
            if "PanelWake" not in tags:
                widget.bindtags(("PanelWake",) + tags)
            for child in widget.winfo_children():
                visit(child)

        visit(self.root)

    def wake_idle(self, pressed):
        if not self.idle_active:
            return None
        self.activity(pressed)
        if not pressed:
            self.root.after_idle(self.return_from_idle)
        return "break"

    def return_from_idle(self):
        if not self.idle_active:
            return
        self.activity(False)
        self.show("room")

    def pressed_colour(self):
        return THEMES[getattr(self, "theme", None) or "light"]["pressed"]

    def button_focus(self, keyboard):
        """Show a neutral focus outline for keyboard use, without a touch halo."""
        self.keyboard_navigation = keyboard
        if getattr(self, "closed", False):
            return
        widget = self.root.focus_get()
        if isinstance(widget, tk.Button):
            widget.config(highlightcolor=self.ink if keyboard else widget.cget("bg"))

    def button(self, parent, text, action, accent=False):
        return ui_widgets.Button(self, parent, text, action, "primary" if accent else "secondary")

    def show_tip(self, text):
        if (
            self.help_on
            and not self.pending
            and not self.release_target
            and not self.closing
            and self.light_state != "failed"
        ):
            tip = TIPS.get(text)
            if text in ("Fid", "Sat", "Dul"):
                tip = (
                    "Applies the room's "
                    + text
                    + " spectral scene to all lights. The name matches Legacy."
                )
            if tip:
                self.status_text.set(tip)

    def photo(self, key, image):
        if key not in self.icon_cache:
            buffer = BytesIO()
            image.save(buffer, format="PNG")
            self.icon_cache[key] = tk.PhotoImage(
                data=base64.b64encode(buffer.getvalue()).decode("ascii")
            )
        return self.icon_cache[key]

    def icon(self, kind, colour, size=32):
        key = (kind, colour, size)
        if key not in self.icon_cache:
            self.photo(key, panel_icons.control(kind, colour, size))
        return self.icon_cache[key]

    def row_buttons(self, parent, items, height=64):
        row = tk.Frame(parent, bg=parent.cget("bg"), height=height)
        row.pack(fill="x", pady=6)
        row.grid_propagate(False)
        row.rowconfigure(0, weight=1)
        buttons = []
        for index, (text, action, accent) in enumerate(items):
            button = self.button(row, text, action, accent)
            # Spacer columns keep the actual button widths equal, including the last.
            row.columnconfigure(index * 2, weight=1, uniform="buttons")
            if index:
                row.columnconfigure(index * 2 - 1, minsize=12)
            button.grid(row=0, column=index * 2, sticky="nsew")
            buttons.append(button)
        return buttons





    def show(self, mode, advanced_page=None):
        if self.release_target is not None or self.closing or self.power_busy():
            return
        if getattr(self, "legacy_stopping_at", None) is not None:
            return
        recovery = getattr(self, "recovery", None)
        if mode == "original" and recovery is not None and (recovery.error or recovery.pending):
            self.status_text.set(self.recovery_snapshot()["detail"])
            return
        if self.mode == "original" and mode != "original" and self.args.live_lights:
            self.stop_legacy()
            return
        if mode == "advanced":
            self.open_advanced()
            return
        self.idle_active = mode == "visitor"
        self.cancel_intent()
        if mode == "original":
            self.close_sheet()
            self.trial_deadline = None
            if self.light_state == "failed" and getattr(self, "light_changes_requested", False) and (recovery is None or recovery.state["status"] == "normal"):
                self.status_text.set(
                    "Light result unconfirmed. Check the receipt before switching controllers."
                )
                return
        if mode == "original" and self.worker:
            self.release_target = "original"
            self.status_text.set("Finishing lighting control before opening Original fallback...")
            if self.light_state not in ("ready", "applying", "connecting"):
                if not self.worker.stdin.closed:
                    self.worker.stdin.close()
            elif not self.pending:
                self.request("release")
            self.update_light_buttons()
            return
        if mode == "original" and self.args.live_lights and recovery is not None and self.worker is None:
            if recovery.state["status"] != "legacy":
                recovery.enter_legacy()
            if recovery.pending:
                self.release_target = "legacy_save"
                self.legacy_save_started = monotonic()
                self.status_text.set("Saving lighting handoff before opening Legacy…")
                self.update_light_buttons()
                return
            if not self.start_legacy():
                return
        if self.mode == "original" and mode != "original" and self.keep_switcher:
            self.trial_deadline = (
                monotonic() + self.args.duration if self.args.duration else None
            )
        if mode == "black":
            self.blank_return = (
                self.mode if self.mode not in ("black", "original") else "room"
            )
            self.blank_advanced_return = self.advanced_page
        self.cancel_hold()
        self.mode, self.section = mode, (
            "lighting"
            if advanced_page in ("white", "lighting")
            else "channels" if advanced_page == "scenes" else "basic"
        )
        self.advanced_page = advanced_page
        if self.light_state != "failed" and not self.pending:
            messages = {
                "health": "Live panel readings. No system settings change.",
                "room": "",
                "advanced": "Fine adjustments and room tools. Opening a page does not operate devices.",
                "visitor": "Visitor view does not change lighting. Recording status is unavailable here.",
                "settings": "Appearance settings belong to this device; they do not change room lighting.",
                "about": "Panel credits and source repository. No room settings change.",
            }
            messages.update(
                guide="",
                support="Instructions only. Commands are not executed by this panel.",
            )
            if mode in messages:
                self.status_text.set(messages[mode])
        render_started = monotonic()
        self.render()
        self.update_navigation_buttons()
        self.emit("mode_changed", target=mode, render_ms=round(1000 * (monotonic() - render_started), 1))








    def blind_state(self):
        controller = getattr(self, "blind_controller", None)
        busy = bool(
            self.pending
            or self.queued_intent
            or self.release_target
            or self.closing
            or self.mode == "original"
            or self.ownership_blocked()
        )
        return blind_readiness(
            getattr(self, "blinds_enabled", False),
            bool(controller and controller.connected) or bool(
                getattr(self, "blinds_connected", False)
                and getattr(self, "worker_ready", False)
                and self.worker and self.worker.poll() is None
            ),
            busy,
        )

    def blind_command(self, name):
        if name not in dict(BLIND_ACTIONS):
            raise ValueError("Unknown blind action")
        readiness = self.blind_state()
        if not readiness["available"]:
            self.status_text.set("Blinds · " + readiness["detail"])
            return False
        if self.blind_controller is not None:
            self.blind_controller.submit(name)
            return True
        if not self.request("blind", {"name": name}):
            return False
        self.light_state = "applying"
        self.lighting_feedback("Blind movement requested. Waiting for controller response.")
        self.update_light_buttons()
        return True

    def programme_available(self):
        return bool(
            getattr(self, "light_capabilities", {}).get("programmes")
            and getattr(self, "worker_ready", False)
            and self.worker and self.worker.poll() is None
            and not self.pending and not self.release_target and not self.closing
            and self.mode not in ("original", "black")
            and not self.ownership_blocked()
            and self.light_state != "disconnected"
            and (self.light_state != "failed" or not self.light_changes_requested)
        )

    def programme_command(self, name):
        if name not in ("Sun", "Circ", "Stop"):
            raise ValueError("Unknown programme")
        if not self.programme_available() or (self.light_state == "failed" and name != "Stop"):
            return False
        self.cancel_intent()
        if not self.request("programme", {"name": name}):
            return False
        self.light_state = "applying"
        self.lighting_feedback("Programme request sent. Waiting for the original service.")
        self.update_light_buttons()
        return True

    def update_blind_buttons(self):
        self.refresh_home_blinds()
        readiness = self.blind_state()
        for button in getattr(self, "blind_buttons", []):
            if button.winfo_exists():
                style = "normal" if readiness["available"] else "disabled"
                if button.cget("state") != style:
                    button.config(state=style)
        text = readiness["detail"] if readiness["available"] else readiness["reason"]
        for name, caption in (("blind_status_label", text),
                              ("system_blind_status_label", "Blinds · " + text)):
            label = getattr(self, name, None)
            if label is not None and label.winfo_exists() and label.cget("text") != caption:
                label.config(text=caption)

    def adapter_metadata(self, response):
        previous = getattr(self, "blinds_connected", False)
        previous_caps = dict(getattr(self, "light_capabilities", {}))
        self.light_capabilities = response.get("capabilities", getattr(self, "light_capabilities", {}))
        self.blinds_connected = response.get("blinds_connected", previous) is True
        self.programme = response.get("programme", getattr(self, "programme", None))
        if previous_caps != self.light_capabilities and getattr(self, "advanced_page", None) == "lighting":
            self.render()
        self.refresh_home_blinds()

    def start_weather(self):
        now = monotonic()
        if (
            self.weather_worker
            or now - self.weather_checked < 900
            or getattr(self.args, "weather_latitude", None) is None
        ):
            return
        self.weather_checked, self.weather_started = now, now
        if not self.weather_last_text:
            self.weather_text.set("Loading weather...")
        command = [
            sys.executable,
            "-B",
            os.path.join(os.path.dirname(__file__), "weather.py"),
            str(self.args.weather_latitude),
            str(self.args.weather_longitude),
            self.args.timezone,
        ]
        try:
            self.weather_worker = subprocess.Popen(
                command, close_fds=True, stdout=subprocess.PIPE
            )
        except OSError:
            self.weather_text.set("Weather unavailable. Room controls still work.")

    def poll_weather(self):
        worker = getattr(self, "weather_worker", None)
        if not worker:
            return
        if worker.poll() is None:
            if monotonic() - self.weather_started > 8:
                worker.kill()
            return
        try:
            reply = json.loads(worker.stdout.read(4097).decode("utf-8"))
            data = weather_data.validate(reply)
            text = "Open-Meteo · model " + data["model_time"].replace("T", " ")
            self.weather_reading = data
            self.weather_last_text, self.weather_good = text, monotonic()
            self.weather_text.set(text)
            self.update_weather(force=True)
        except (ValueError, KeyError, TypeError, IOError):
            self.weather_text.set(
                ("Last available weather (refresh failed):\n" + self.weather_last_text)
                if self.weather_last_text
                else "Weather unavailable. Room controls still work."
            )
        finally:
            worker.stdout.close()
            if worker.stderr:
                worker.stderr.close()
            self.weather_worker = None

    def step_slider(self, variable, low, high, step):
        variable.set(max(low, min(high, variable.get() + step)))
        self.cct_apply()

    def bind_slider(self, scale, action):
        # Read the live generation on press. Recovery can cancel without rebuilding.
        scale._action = action
        scale.on_start = lambda: self.slider_pressed(scale, action, self.view_generation)
        scale.on_end = lambda: self.slider_released(None)
        # TouchSlider updates the variable itself; room writes start on release.
        scale.config(command=lambda value: None)

    def slider_pressed(self, scale, action, generation):
        if generation == self.view_generation and scale.cget("state") != "disabled":
            self.slider_drag = (scale, action, generation)
            if self.help_on:
                self.status_text.set(
                    "Warm to cool white: kelvin and controller light-level input."
                    if action == "cct"
                    else "Eight channel percentages. Changes send automatically."
                )

    def slider_changed(self, scale, action, generation):
        if (
            self.slider_drag == (scale, action, generation)
            and generation == self.view_generation
        ):
            self.cct_apply() if action == "cct" else self.channels_apply()

    def slider_released(self, event):
        drag, self.slider_drag = self.slider_drag, None
        if drag and drag[2] == self.view_generation and self.mode == "room":
            self.cct_apply() if drag[1] == "cct" else self.channels_apply()

    def preset(self, name):
        if name == "Gradient":
            self.apply("gradient", immediate=True)
            return
        for variable, value in zip(self.channel_values, PRESETS[name]):
            variable.set(value)
        self.apply("channels", immediate=True, values=list(PRESETS[name]))

    def lights_on(self):
        self.preset("Fid")

    def previous_on(self):
        arguments = PREVIOUS_ON["arguments"]
        self.cct.set(arguments["cct"])
        self.intensity.set(arguments["intensity"])
        self.apply("cct", immediate=True, **arguments)

    def cct_apply(self):
        self.apply("cct", cct=self.cct.get(), intensity=self.intensity.get())

    def channels_apply(self):
        self.apply("channels", values=[item.get() for item in self.channel_values])

    def apply(self, action, immediate=False, **arguments):
        if (
            self.mode in ("original", "black")
            or self.ownership_blocked()
            or self.light_state not in ("ready", "applying")
            or self.release_target
            or self.closing
        ):
            self.status_text.set("Lighting unavailable. Check System & help.")
            return
        # Immutable complete intent, one unsent selection shared by all light controls.
        arguments = json.loads(json.dumps(arguments))
        self.queued_intent = (action, arguments, self.view_generation)
        if self.intent_timer is not None:
            self.root.after_cancel(self.intent_timer)
        self.intent_timer = None
        if immediate:
            if self.pending:
                self.lighting_feedback(
                    "Selected: "
                    + light_selection(action, arguments)
                    + " / waiting for current request"
                )
            self.dispatch_intent()
            return
        self.intent_timer = self.root.after(250, self.dispatch_intent)
        self.lighting_feedback(
            "Selected: " + light_selection(action, arguments) + " / waiting to send"
        )

    def cancel_intent(self):
        cancelled = self.queued_intent is not None
        if self.intent_timer is not None:
            self.root.after_cancel(self.intent_timer)
        self.intent_timer, self.queued_intent, self.slider_drag = None, None, None
        self.view_generation += 1
        if (
            cancelled and not self.pending and self.light_state == "ready"
            and not self.ownership_blocked()
            and getattr(self, "light_message", "").endswith(" / waiting to send")
        ):
            self.lighting_feedback("Unsent selection cancelled.")

    def dispatch_intent(self):
        self.intent_timer = None
        if self.pending or getattr(getattr(self, "recovery", None), "pending", False):
            return
        intent, self.queued_intent = self.queued_intent, None
        if (
            not intent
            or intent[2] != self.view_generation
            or self.mode in ("original", "black")
            or self.light_state != "ready"
            or self.ownership_blocked()
            or self.release_target
            or self.closing
        ):
            return
        action, arguments = intent[:2]
        self.light_state = "applying"
        self.lighting_feedback(
            "Sending: "
            + light_selection(action, arguments)
            + " / awaiting confirmation"
        )
        self.status_text.set("Updating lights. Waiting for confirmation…")
        if not self.request(action, arguments):
            self.light_state = "failed"
            self.cancel_intent()
            self.lighting_feedback(
                "Lighting adapter unavailable. Check System & help."
            )
        self.update_light_buttons()

    def update_light_buttons(self):
        self.update_navigation_buttons()
        self.update_recovery_view()
        if hasattr(self, "connection_badges"):
            self.update_connection_badges()
        for button in self.light_buttons:
            if button.winfo_exists():
                style = (
                    "normal"
                    if self.light_state == "ready"
                    and not self.pending
                    and (not getattr(button, "_gradient", False)
                         or getattr(self, "light_capabilities", {}).get("gradient"))
                    and not self.ownership_blocked()
                    and not self.release_target
                    and not self.closing
                    else "disabled"
                )
                if button.cget("state") != style:
                    button.config(state=style)
        self.update_power_highlights()
        self.update_blind_buttons()
        for button in getattr(self, "programme_buttons", []):
            if button.winfo_exists():
                allowed = self.programme_available() and (
                    self.light_state != "failed" or getattr(button, "_programme", None) == "Stop"
                )
                style = "normal" if allowed else "disabled"
                if button.cget("state") != style:
                    button.config(state=style)

    def power_busy(self):
        return bool(getattr(self, "power", None) and self.power.busy)

    def power_snapshot(self):
        power = getattr(self, "power", None)
        if power is None:
            return {
                "available": False,
                "actions": {"reboot": False, "shutdown": False},
                "phase": "unavailable",
                "message": "Power controls unavailable.",
            }
        actions = {
            name: bool(power and name in power.commands)
            for name in ("reboot", "shutdown")
        }
        clear = (
            self.mode != "original"
            and self.light_state == "ready"
            and not self.ownership_blocked()
            and self.worker is not None
            and not any(
                (
                    self.pending,
                    self.queued_intent,
                    self.intent_timer,
                    self.slider_drag,
                    self.release_target,
                    self.closing,
                )
            )
        )
        available = bool(power and power.phase == "ready" and clear)
        message = power.message if power else "Power controls unavailable."
        if power and power.phase == "ready" and not clear:
            message = "Wait for confirmed lighting before restarting or shutting down."
        if power and power.phase == "failed":
            message += " Power controls stay off until the panel restarts."
            if self.light_state == "disconnected" and self.worker is None:
                message += " Open Legacy, then Home, to reconnect lighting."
        return {
            "available": available,
            "actions": actions,
            "phase": power.phase if power else "unavailable",
            "message": message,
        }

    def confirm_power(self, operation):
        state = self.power_snapshot()
        if not state["available"] or not state["actions"].get(operation):
            self.status_text.set(state["message"])
            return
        if self.power_dialog is not None and self.power_dialog.winfo_exists():
            return
        dialog = self.power_dialog = tk.Toplevel(self.root)
        dialog.title("Restart panel" if operation == "reboot" else "Shut down panel")
        dialog.geometry("860x440+210+180")
        dialog.overrideredirect(True)
        dialog.configure(
            bg=self.bg, highlightthickness=1, highlightbackground=self.border
        )
        dialog.transient(self.root)
        dialog.grab_set()
        content = tk.Frame(dialog, bg=self.bg)
        content.pack(fill="both", expand=True, padx=32, pady=28)
        self.label(
            content,
            "Restart this Pi?" if operation == "reboot" else "Shut down this Pi?",
            27,
        ).pack(anchor="w", pady=(0, 16))
        note = self.label(
            content,
            "This interrupts the touch panel and website. The room computer and its recorders are separate. Stop any recording or experiment first.",
            20,
        )
        self.wrap_label(note).pack(fill="x")
        acknowledged = tk.BooleanVar(value=False)
        acknowledgement = tk.Checkbutton(
            content,
            text="I have stopped any recording or experiment",
            variable=acknowledged,
            font=ui_widgets.font("text"),
            bg=self.bg,
            fg=self.ink,
            disabledforeground=self.muted,
            selectcolor=self.control,
            activebackground=self.bg,
            activeforeground=self.ink,
            highlightthickness=0,
            anchor="w",
            pady=14,
        )
        acknowledgement.pack(fill="x", pady=(12, 0))
        message = self.label(content, size=17, muted=True)
        message.config(textvariable=self.power_text)
        self.wrap_label(message).pack(fill="x", pady=8)

        def cancel():
            if not self.power_busy():
                dialog.grab_release()
                dialog.destroy()
                self.power_dialog = None

        def confirm():
            if not acknowledged.get():
                return
            try:
                self.request_power(operation, confirmed=True)
            except (ValueError, RuntimeError) as error:
                self.power_text.set(str(error))
                return
            acknowledgement.config(state="disabled")
            buttons[0].config(state="disabled")
            buttons[1].config(state="disabled", disabledforeground=self.muted)

        buttons = self.row_buttons(
            content,
            [
                ("Close", cancel, False),
                (
                    "Restart panel" if operation == "reboot" else "Shut down panel",
                    confirm,
                    True,
                ),
            ],
            height=ui_widgets.S["tap"],
        )
        self.power_dialog_close = buttons[0]

        def update_confirmation():
            checked = acknowledged.get()
            buttons[1].config(
                state="normal" if checked else "disabled",
            )

        update_confirmation()
        acknowledgement.config(command=update_confirmation)
        dialog.protocol("WM_DELETE_WINDOW", cancel)

    def request_power(self, operation, confirmed=False):
        state = self.power_snapshot()
        if confirmed is not True or operation not in ("reboot", "shutdown"):
            raise ValueError("Explicit power confirmation is required.")
        if not state["available"] or not state["actions"][operation]:
            raise RuntimeError(state["message"])
        if self.idle_active:
            self.return_from_idle()
        self.power.prepare(operation)
        self.power_deadline = monotonic() + 45
        self.power_cleanup_confirmed = self.power_checkpoint_saved = False
        self.power_sequence = None
        self.release_target = "power"
        self.emit("power_selected", operation=operation)
        if not self.request("release"):
            self.release_target = None
            self.power.fail("Lighting cleanup could not start. Power action cancelled.")
        self.poll_power()

    def poll_power(self):
        power = getattr(self, "power", None)
        if power is None:
            return
        if (
            power.busy
            and power.phase != "executing"
            and monotonic() >= self.power_deadline
        ):
            power.fail(
                "Cleanup did not finish. Power action cancelled; check the panel."
            )
        if power.phase == "saving":
            preferences = getattr(self, "preferences", None)
            recovery = getattr(self, "recovery", None)
            if self.journal.error or (preferences and preferences.error) or (recovery and recovery.error):
                power.fail("Local state could not be saved. Power action cancelled.")
            elif self.power_checkpoint_saved and not (recovery and recovery.pending) and (
                preferences is None or preferences.settled.is_set()
            ):
                power.execute()
        set_changed(self.power_text, self.power_snapshot()["message"])
        state = self.power_snapshot()
        if (
            power.busy
            or power.phase == "failed"
            or (self.mode == "health" and self.advanced_page == "system")
        ):
            set_changed(self.status_text, state["message"])
        for button, operation in getattr(self, "power_buttons", []):
            if button.winfo_exists():
                style = (
                    "normal"
                    if state["available"] and state["actions"][operation]
                    else "disabled"
                )
                if button.cget("state") != style:
                    button.config(state=style)
        close_button = getattr(self, "power_dialog_close", None)
        if close_button is not None and close_button.winfo_exists():
            style = "disabled" if power.busy else "normal"
            if close_button.cget("state") != style:
                close_button.config(state=style)

    def power_after_release(self, returncode):
        if self.power.phase != "restoring":
            return
        if not self.power_cleanup_confirmed or returncode != 0:
            self.power.fail("Lighting cleanup is unconfirmed. Power action cancelled.")
            return
        self.power.phase = "saving"
        self.power.message = "Saving local state before " + (
            "restart…" if self.power.operation == "reboot" else "shutdown…"
        )
        try:
            self.power_sequence = self.emit(
                "power_requested", operation=self.power.operation
            )
        except (IOError, OSError):
            self.power.fail("Power request could not be saved. Power action cancelled.")

    def refresh_resources(self):
        now = monotonic()
        pending = getattr(self, "health_pending", None)
        if pending is not None:
            self.health_cache, self.health_pending = pending, None
        worker = getattr(self, "health_worker", None)
        if now - self.health_at >= 5 and (worker is None or not worker.is_alive()):
            self.health_at = now

            def read_resources():
                # No Tk calls on this thread; a slow SD or power query cannot hold a touch.
                try:
                    self.health_pending = health()
                except Exception as error:
                    self.health_pending = {"error": str(error)}

            self.health_worker = threading.Thread(
                target=read_resources, name="scr-panel-resources"
            )
            self.health_worker.daemon = True
            self.health_worker.start()
        # Room service discovery runs only from Check now, never from navigation.

    def update_health(self):
        if self.mode != "health":
            return
        self.refresh_resources()
        if getattr(self, "system_diagnostics_visible", False):
            self.update_room_diagnostics()
            return
        key = (tuple(sorted(self.health_cache.items())), self.room_status, self.theme)
        if key == getattr(self, "health_rendered", None):
            return
        self.health_rendered = key
        self.services_label.config(text=self.room_status)
        self.refresh_system_facts()
        self.update_room_diagnostics()

    def room_diagnostics(self):
        configured = bool(
            getattr(self.args, "expected_master", None)
            and sys.platform.startswith("linux")
        )
        checking = getattr(self, "status_worker", None) is not None
        state = getattr(self, "room_status_state", "unavailable") if configured else "unconfigured"
        observed = getattr(self, "room_status_good_at", None)
        detail = (
            "Checking advertised room services. No sensor data is queried."
            if checking
            else "Room service checks are not configured on this panel."
            if not configured
            else "The latest service check failed. Previous results retain their age."
            if state == "unavailable" and observed is not None
            else "Room services have not been checked successfully."
            if state == "unavailable"
            else "Service registrations only. They do not confirm live sensor data or recording."
        )
        return {
            "state": state,
            "services": [dict(row) for row in getattr(self, "room_services", [])],
            "observed_at": getattr(self, "room_status_observed", None),
            "age_s": None if observed is None else max(0, monotonic() - observed),
            "checking": checking,
            "can_check": bool(configured and not checking
                              and not getattr(self, "closed", False)
                              and not getattr(self, "closing", None)
                              and not self.power_busy()),
            "detail": detail,
        }

    def refresh_status(self):
        """An explicit metadata read reuses the normal worker and its cache."""
        if not self.room_diagnostics()["can_check"]:
            return False
        return self.start_status()

    def start_status(self):
        if getattr(self, "status_worker", None) is not None:
            return False
        self.room_status_at = monotonic()
        master = getattr(self.args, "expected_master", None)
        if not master or not sys.platform.startswith("linux"):
            self.room_status_state = "unconfigured"
            self.room_status = (
                "Room service availability: no approved master configured."
            )
            return False
        path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "scr_touch_panel_lights.py"
        )
        try:
            self.status_worker = subprocess.Popen(
                [sys.executable, "-B", path, "--status-only", "--expected-master", master],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                close_fds=True,
            )
        except OSError:
            self.status_worker = None
            self.room_status_state = "unavailable"
            self.room_status = "Room service availability could not be checked. No sensor data was queried."
            return False
        self.status_started = monotonic()
        self.room_status = "Checking advertised room services..."
        return True

    def poll_status(self):
        worker = self.status_worker
        if not worker:
            return
        age = monotonic() - self.status_started
        returncode = worker.poll()
        if returncode is None:
            if age > 7:
                worker.kill()
            elif age > 5:
                worker.terminate()
            return
        try:
            raw = worker.stdout.read(4097)
            if len(raw) > 4096 or returncode != 0:
                raise ValueError("Status probe failed or reply too large")
            result = json.loads(raw.decode("utf-8"))
            if not isinstance(result, dict) or type(result.get("version")) is not int or result["version"] != 1:
                raise ValueError("Invalid service availability version")
            services = result["services"]
            if not isinstance(services, list) or len(services) > 20 or any(
                not isinstance(item, (list, tuple))
                or len(item) != 2
                or not isinstance(item[0], str)
                or not 1 <= len(item[0]) <= 60
                or not isinstance(item[1], bool)
                for item in services
            ):
                raise ValueError("Invalid service availability reply")
            if len({name for name, present in services}) != len(services):
                raise ValueError("Duplicate service availability rows")
            self.room_services = [
                {"name": name, "state": "listed" if present else "missing"}
                for name, present in services
            ]
            self.room_status_good_at = monotonic()
            self.room_status_observed = datetime.datetime.now(datetime.timezone.utc).isoformat()
            self.room_status_state = "available"
            self.room_status = (
                "ROS master reachable / advertised services at "
                + time.strftime("%H:%M:%S")
                + "\n"
            )
            self.room_status += "   |   ".join(
                name + ": " + ("present" if present else "missing")
                for name, present in services
            )
        except (IOError, OSError, ValueError, KeyError, TypeError, RecursionError):
            self.room_status_state = "unavailable"
            self.room_status = "Room service availability could not be checked. No sensor data was queried."
        worker.stdout.close()
        worker.stderr.close()
        self.status_worker = None

    def choose_blinds_display(self, choice):
        if choice not in ("disabled", "hidden") or choice == self.blinds_display:
            return
        self.blinds_display = choice
        self.save_preferences()
        self.render()
        self.emit("blinds_display_selected", choice=choice)

    def choose_blinds_enabled(self, enabled):
        if type(enabled) is not bool:
            raise ValueError("Expected a blind movement setting")
        if enabled == self.blinds_enabled:
            return
        self.blinds_enabled = enabled
        self.save_preferences()
        self.render()
        self.emit("blinds_enabled_selected", enabled=enabled)

    def choose_clock(self, format):
        if self.clock_24 == (format == "24"):
            return
        self.clock_24 = format == "24"
        self.save_preferences()
        self.render()
        self.emit("clock_format_selected", format=format)

    def choose_temperature(self, unit):
        if unit == self.temperature_unit:
            return
        self.temperature_unit = unit
        self.save_preferences()
        self.render()
        self.emit("temperature_unit_selected", unit=unit)

    def choose_idle(self, seconds):
        if seconds == self.idle_timeout:
            return
        self.idle_timeout = seconds
        self.activity()
        self.save_preferences()
        self.render()
        self.emit("idle_timeout_selected", seconds=seconds)

    def open_lighting_help(self):
        if self.release_target or self.closing or self.power_busy() or getattr(self, "legacy_stopping_at", None):
            return
        changed = (getattr(self, "system_diagnostics_visible", False)
                   or self.support_commands_visible or self.support_page != 0 or self.support_step != 0)
        self.support_page = 0
        self.support_step = 0
        self.support_commands_visible = self.system_diagnostics_visible = False
        if self.mode == "health" and self.advanced_page == "system" and changed:
            self.rebuild_advanced_detail()
        else:
            self.open_advanced("system")

    def choose_tips(self, enabled):
        if enabled == self.help_on:
            return
        self.help_on = enabled
        self.save_preferences()
        self.render()
        self.emit("help_selected", enabled=self.help_on)

    def choose_theme(self, choice):
        if choice == self.theme_choice:
            return
        self.theme_choice, self.theme = choice, None
        self.save_preferences()
        self.set_theme()
        self.emit("theme_selected", choice=choice, resolved=self.theme)

    def adjust_schedule(self, key, delta):
        value = (getattr(self.args, key) + delta) % 1440
        if value != (self.args.dark_at if key == "light_at" else self.args.light_at):
            setattr(self.args, key, value)
            self.save_preferences()
            self.emit(
                "theme_schedule_changed",
                light_at=self.args.light_at,
                dark_at=self.args.dark_at,
            )
            self.set_theme()
            self.render()

    def preference_summary(self):
        error = (
            self.preferences.error if self.preferences else None
        ) or self.preference_error
        if error:
            return "Appearance settings could not be saved or loaded; current choices still work."
        return (
            "Appearance choices save automatically on this device."
            if self.preferences
            else "Preview preferences last for this session. No room settings are saved."
        )

    def save_preferences(self):
        if self.preferences:
            self.preference_error = None
            self.preferences.save(
                {
                    "theme": self.theme_choice,
                    "clock_format": "24" if self.clock_24 else "12",
                    "temperature_unit": self.temperature_unit,
                    "idle_timeout": self.idle_timeout,
                    "blinds_display": self.blinds_display,
                    "blinds_enabled": self.blinds_enabled,
                    "tips": "on" if self.help_on else "off",
                    "light_at": self.args.light_at,
                    "dark_at": self.args.dark_at,
                }
            )

    def start_worker(self, legacy_return=False):
        if self.legacy_alive() or getattr(self, "legacy_stopping_at", None) is not None or getattr(self, "worker", None) is not None:
            return
        if self.ownership_blocked() and not legacy_return:
            self.lighting_feedback(self.recovery_snapshot().get("detail", "Lighting needs staff attention."))
            return
        self.legacy_returning = legacy_return
        path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "scr_touch_panel_lights.py"
        )
        receipt = self.args.journal + ".lights-" + uuid.uuid4().hex[:8] + ".jsonl"
        command = [
            getattr(self.args, "adapter_python", "/usr/bin/python2.7"),
            "-u",
            "-B",
            path,
            "--receipt",
            receipt,
            "--parent-pid",
            str(os.getpid()),
            "--expected-master",
            self.args.expected_master,
        ]
        if self.keep_switcher:
            command.append("--keep-settings")
        if getattr(self.args, "status_url", None):
            command.extend(["--status-url", self.args.status_url])
        self.release_confirmed = self.light_changes_requested = False
        self.worker_started = monotonic()
        try:
            self.worker = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=sys.stderr,
                close_fds=True,
                bufsize=0,
            )
            if isinstance(self.worker.stdin, FileIO) and sys.platform.startswith("linux"):
                os.set_blocking(self.worker.stdin.fileno(), False)
        except OSError:
            if self.worker is not None:
                self.worker.stdin.close()
                self.worker.terminate()  # No acquire or hardware command was sent.
            self.worker = None
            self.light_state = "failed"
            recovery = getattr(self, "recovery", None)
            if recovery is not None and legacy_return:
                self.legacy_returning = False
                recovery.mark_uncertain("The lighting helper could not start. Press Check connection to try again.")
            self.status_text.set("Lighting helper could not start. Check System & help.")
            self.lighting_feedback("Lighting unavailable; helper could not start.")
            return
        self.light_state = "connecting"
        self.confirmed_light = "Not checked"
        self.confirmed_at = None
        self.confirmed_power = None
        self.confirmed_scene = None
        self.lighting_feedback("Checking the current light settings…")
        self.worker_buffer = ""
        self.worker_ready = False
        self.light_capabilities = {}
        self.blinds_connected = False

    def request(self, action, arguments=None):
        recovery = getattr(self, "recovery", None)
        if (
            self.pending
            or (recovery is not None and recovery.error)
            or not self.worker
            or self.worker.poll() is not None
            or not getattr(self, "worker_ready", False)
        ):
            return False
        if self.legacy_alive() or getattr(self, "legacy_stopping_at", None) is not None:
            return False
        self.request_seq += 1
        item = {
            "version": 1,
            "request_id": self.run_id + ":" + str(self.request_seq),
            "action": action,
            "arguments": arguments or {},
            "sent_monotonic_s": monotonic(),
        }
        self.emit("light_requested", request=item)
        if action in ("cct", "channels", "gradient", "programme", "blind", "return_legacy"):
            if recovery is not None:
                try:
                    recovery.begin_write(item["request_id"], returning=action == "return_legacy")
                except (RuntimeError, ValueError) as error:
                    self.status_text.set(str(error))
                    return False
            # A lost pipe response must never permit an unverified controller handoff.
            self.light_changes_requested = True
        elif action == "release":
            self.release_confirmed = False
        self.pending = item
        if recovery is not None and recovery.pending:
            self.unsent_request = item
            self.unsent_request_at = monotonic()
            return True
        return self.send_request(item)

    def write_helper(self, value):
        raw = (json.dumps(value) + "\n").encode("utf-8")
        # One small atomic pipe write; a stuck helper must never block Tk.
        if len(raw) > 4096 or self.worker.stdin.write(raw) != len(raw):
            raise OSError("Lighting helper pipe is busy")
        self.worker.stdin.flush()

    def send_request(self, item):
        item["sent_monotonic_s"] = monotonic()
        try:
            self.write_helper(item)
        except (IOError, OSError) as error:
            self.light_state = "failed"
            if hasattr(self, "recovery"):
                self.command_lost("The controller response was lost. Check the previous operation.")
            self.cancel_intent()
            self.status_text.set("Light adapter disconnected: " + str(error))
            self.pending = None
            return False
        return True

    def poll_journal(self):
        journal = getattr(self, "journal", None)
        if journal is None:
            return
        for sequence in journal.poll():
            if sequence == getattr(self, "power_sequence", None):
                self.power_checkpoint_saved = True
        error = journal.error or (
            journal.output_error if not self.args.journal else None
        )
        if error:
            self.status_text.set("Panel journal unavailable: " + error)

    def fail_worker(self, message):
        if hasattr(self, "recovery"):
            self.command_lost("Lighting confirmation was lost. Check the previous controller.")
        self.cancel_intent()
        self.pending = None
        self.unsent_request = None
        self.light_state = "failed"
        self.worker_ready = False
        self.worker_buffer = ""
        self.status_text.set(message)
        self.lighting_feedback(RECONNECTING if getattr(self, "reconnect_after_exit", False) else "Lighting unavailable. Press Check connection to try again.")
        if self.worker and not self.worker.stdin.closed:
            try:
                self.worker.stdin.close()
            except (IOError, OSError):
                pass
        self.update_light_buttons()

    def poll_worker(self):
        if self.closed:
            return
        started = monotonic()
        try:
            self.poll_worker_once()
        except Exception as error:
            self.light_state = "failed"
            self.pending = None
            self.unsent_request = None
            if hasattr(self, "recovery"):
                try:
                    self.command_lost("Lighting recovery could not be confirmed. Ask the room host.")
                except (RuntimeError, ValueError):
                    pass
            self.status_text.set("Lighting stopped responding. No command will be repeated.")
            worker = self.worker
            if worker and not worker.stdin.closed:
                try:
                    worker.stdin.close()
                except (IOError, OSError):
                    pass
            self.emit("lighting_recovery_error", detail=str(error)[:240])
        finally:
            if not self.closed:
                self.note_slow_ui("poll_worker", started, getattr(self, "worker_poll_due", None))
                self.worker_poll_due = monotonic() + 0.1
                self.root.after(100, self.poll_worker)

    def poll_worker_once(self):
        if self.closed:
            return
        self.poll_legacy()
        if self.closed:
            return
        if (
            getattr(self, "mode", None) == "health"
            and getattr(self, "health_pending", None) is not None
        ):
            self.update_health()
        self.poll_journal()
        self.poll_power()
        self.poll_status()
        self.poll_weather()
        recovery = getattr(self, "recovery", None)
        if recovery is not None:
            if self.release_target == "legacy_save" and recovery.pending and monotonic() - self.legacy_save_started > 10:
                self.release_target = None
                recovery.mark_uncertain("Legacy handoff could not be saved in time. Ask the room host.")
                self.fail_worker("Lighting handoff save did not finish. Legacy has not started. Press Check connection to try again.")
            if self.release_target == "legacy_save" and not recovery.pending:
                self.release_target = None
                if recovery.error:
                    self.fail_worker("Lighting handoff could not be saved. Ask the room host.")
                else:
                    self.show("original")
            unsent = getattr(self, "unsent_request", None)
            if unsent is not None:
                if recovery.error or monotonic() - self.unsent_request_at > 10:
                    self.fail_worker("Lighting save did not finish. No command was sent.")
                elif not recovery.pending:
                    self.unsent_request = None
                    self.send_request(unsent)
        worker = self.worker
        if worker:
            if (
                self.light_state == "connecting"
                and not self.worker_ready
                and monotonic() - getattr(self, "worker_started", monotonic()) > 30
            ):
                # No acquire or setter has been sent before initialization.
                worker.terminate()
                self.fail_worker("Lighting helper startup timed out. Original fallback remains available.")
                self.lighting_feedback("Lighting unavailable; helper startup timed out.")
            if self.pending and monotonic() - self.pending.get("sent_monotonic_s", monotonic()) > 35:
                self.fail_worker("Lighting response timed out. Result unconfirmed; no retry.")
            if (
                worker.poll() is None
                and not worker.stdin.closed
                and monotonic() - self.last_heartbeat >= 2
            ):
                try:
                    self.write_helper({
                        "version": 1,
                        "action": "heartbeat",
                        "sent_monotonic_s": monotonic(),
                    })
                    self.last_heartbeat = monotonic()
                except (IOError, OSError):
                    pass
            try:
                while select.select([worker.stdout], [], [], 0)[0]:
                    chunk = os.read(worker.stdout.fileno(), 8192)
                    if not chunk:
                        break
                    self.worker_buffer += chunk.decode("utf-8")
                    if len(self.worker_buffer) > 8192:
                        raise ValueError("Adapter reply too large")
            except (IOError, OSError, ValueError, UnicodeError):
                self.fail_worker("Unreadable lighting reply.")
            while "\n" in self.worker_buffer:
                line, self.worker_buffer = self.worker_buffer.split("\n", 1)
                try:
                    response = json.loads(line)
                except (ValueError, RecursionError):
                    self.fail_worker("Invalid lighting reply.")
                    break
                if not isinstance(response, dict) or (
                    "detail" in response and not isinstance(response["detail"], str)
                ) or (
                    response.get("baseline") is not None
                    and not isinstance(response["baseline"], str)
                ) or (
                    "capabilities" in response and (
                        not isinstance(response["capabilities"], dict)
                        or any(type(value) is not bool for value in response["capabilities"].values())
                    )
                ) or (
                    "programme" in response and response["programme"] not in (None, "Sun", "Circ")
                ) or (
                    "blinds_connected" in response and type(response["blinds_connected"]) is not bool
                ):
                    self.fail_worker("Invalid lighting reply.")
                    break
                if (
                    response.get("version") == 1
                    and response.get("state") == "initialized"
                    and not self.worker_ready
                    and self.light_state == "connecting"
                ):
                    self.worker_ready = True
                    self.adapter_metadata(response)
                    if self.release_target or self.closing:
                        action = "release"
                    elif getattr(self, "legacy_returning", False):
                        action = "return_legacy"
                    else:
                        action = "acquire"
                    self.request(action)
                    continue
                if (
                    not self.pending
                    or response.get("request_id") != self.pending["request_id"]
                ):
                    continue
                expected = {
                    "acquire": ("ready", "failed"),
                    "return_legacy": ("ready", "failed"),
                    "check": ("checked", "failed"),
                    "release": ("released", "failed"),
                    "cct": ("completed", "failed"),
                    "channels": ("completed", "failed"),
                    "gradient": ("completed", "failed"),
                    "programme": ("completed", "failed"),
                    "blind": ("completed", "failed"),
                }.get(self.pending["action"], ())
                if response.get("version") != 1 or response.get("state") not in expected:
                    self.fail_worker("Invalid lighting reply.")
                    continue
                completed_request, self.pending = self.pending, None
                action = completed_request["action"]
                self.emit("light_result", result=response)
                state = response["state"]
                self.adapter_metadata(response)
                self.light_state = {
                    "completed": "ready",
                    "released": "disconnected",
                    "checked": "failed" if self.ownership_blocked() else "ready",
                }.get(state, state)
                detail = response.get("detail", "Lighting ready.")
                if state == "failed":
                    # Full exception text remains in the emitted result/receipt.
                    # Keep the touch feedback bounded, even for verbose ROS errors.
                    detail = "That change could not be confirmed." if action in ("cct", "channels", "gradient", "programme", "blind") else "Lighting could not be read."
                if state == "completed" and action not in ("programme", "blind"):
                    self.confirmed_light = light_selection(
                        action, completed_request["arguments"]
                    )
                    self.confirmed_at = monotonic()
                    self.confirmed_power = confirmed_power(response)
                    self.confirmed_scene = confirmed_scene(response)
                    detail = "Light settings confirmed."
                elif state == "completed" and action == "programme":
                    self.confirmed_light = "Programme request accepted; live state unavailable"
                    self.confirmed_at = self.confirmed_power = self.confirmed_scene = None
                elif state == "ready":
                    detail = "Lighting ready."
                    baseline = response.get("baseline")
                    self.confirmed_light = (
                        baseline + " scene" if baseline in PRESETS else "Current room settings"
                    )
                    self.confirmed_at = monotonic()
                    self.confirmed_power = confirmed_power(response)
                    self.confirmed_scene = confirmed_scene(response)
                elif state == "released":
                    self.confirmed_light = "Session ended"
                    self.confirmed_at = None
                    self.confirmed_power = None
                    self.confirmed_scene = None
                if state in ("ready", "checked") or (state == "completed" and action not in ("programme", "blind") and not self.queued_intent):
                    self.seed_controls(response, completed_request)
                self.lighting_feedback(detail)
                if hasattr(self, "recovery"):
                    self.recovery_result(completed_request, response)
                self.status_text.set("" if state in ("ready", "completed", "checked") else detail)
                if action == "release":
                    self.release_confirmed = state == "released" and (
                        response.get("preserved") is True
                        if self.keep_switcher
                        else response.get("restored") is True
                    )
                    if getattr(self, "power", None) and self.power.phase == "restoring":
                        if self.release_confirmed:
                            self.power_cleanup_confirmed = True
                        else:
                            self.power.fail(
                                "Lighting cleanup is unconfirmed. Power action cancelled."
                            )
                    if not self.release_confirmed:
                        self.light_state = "failed"
                        self.release_target = None
                        self.status_text.set(
                            "Lighting release unconfirmed. Stay here; inspect the receipt before further control."
                        )
                elif self.release_target and state != "failed":
                    self.request("release")
                elif state == "failed":
                    self.release_target = None
                    self.cancel_intent()
                    self.status_text.set(detail + (" " + RECONNECTING if getattr(self, "reconnect_after_exit", False) else " Press Check connection to try again."))
                elif self.queued_intent and self.intent_timer is None:
                    self.dispatch_intent()
                self.update_light_buttons()
            if worker.poll() is not None:
                if hasattr(self, "recovery"):
                    self.command_lost("The lighting helper stopped before ownership or a command was confirmed.")
                if self.pending or self.light_state != "disconnected":
                    self.cancel_intent()
                    self.pending = None
                    self.light_state = "failed"
                    reconnect = getattr(self, "reconnect_after_exit", False)
                    self.status_text.set(RECONNECTING if reconnect else "Lighting helper stopped. Press Check connection to try again.")
                    self.lighting_feedback(RECONNECTING if reconnect else "Lighting unavailable. Press Check connection to try again.")
                self.worker = None
                self.unsent_request = None
                target, self.release_target = self.release_target, None
                if self.closing:
                    self.finish_close()
                    return
                if getattr(self, "reconnect_after_exit", False):
                    self.reconnect_after_exit = False
                    if target is None and not self.ownership_blocked():
                        self.start_worker()  # Read-only acquire; the failed command is never repeated.
                if target == "original":
                    safe = (
                        worker.returncode == 0 and getattr(self, "release_confirmed", False)
                    )
                    if safe:
                        self.show("original")
                    else:
                        self.status_text.set(
                            "Lighting release unconfirmed. Check the receipt before switching controllers."
                        )
                elif target == "power":
                    self.power_after_release(worker.returncode)
                elif target == "check_connection":
                    self.start_worker(legacy_return=True)
                self.update_light_buttons()
        if not self.pending and getattr(self, "queued_intent", None) and self.intent_timer is None:
            self.dispatch_intent()
        if recovery is not None:
            saved = (recovery.pending, recovery.error, recovery.state["revision"])
            if saved != getattr(self, "recovery_displayed", None):
                self.recovery_displayed = saved
                if recovery.error:
                    self.fail_worker("Lighting state could not be saved. Ask the room host.")
                else:
                    self.update_light_buttons()

    def begin_hold(self, event):
        self.cancel_hold()
        self.hold_origin = (event.x_root, event.y_root)
        self.hold = self.root.after(2000, self.return_from_blank)

    def return_from_blank(self):
        page = getattr(self, "blank_advanced_return", None)
        if page:
            self.open_advanced(page)
        else:
            self.show(self.blank_return)

    def move_hold(self, event):
        if self.hold_origin and (
            (event.x_root - self.hold_origin[0]) ** 2
            + (event.y_root - self.hold_origin[1]) ** 2
            > 40**2
        ):
            self.cancel_hold()

    def cancel_hold(self):
        if self.hold is not None:
            self.root.after_cancel(self.hold)
        self.hold = self.hold_origin = None

    def tick(self):
        if self.closed:
            return False
        remaining = (
            self.trial_deadline - monotonic()
            if self.trial_deadline is not None
            else None
        )
        if remaining is not None and remaining <= 0 and not self.closing:
            self.close("timeout")
        if self.closed:
            return False
        self.set_theme()
        set_changed(
            self.visitor_time,
            (
                time.strftime("%H:%M")
                if self.clock_24
                else time.strftime("%I:%M %p").lstrip("0")
            ),
        )
        set_changed(self.visitor_date, time.strftime("%A, %d %B").replace(" 0", " "))
        set_changed(self.preference_text, self.preference_summary())
        self.update_connection_badges()
        self.update_blind_buttons()
        self.update_recovery_view()
        self.update_navigation_buttons()
        self.refresh_confirmation_age()
        self.update_idle()
        if self.weather_reading:
            old = self.weather_is_earlier()
            caption = weather_data.details(
                self.weather_reading, self.temperature_unit, earlier=old
            )
        else:
            caption = (
                "Weather not configured"
                if self.args.weather_latitude is None
                else "Weather unavailable"
            )
        set_changed(self.home_weather_text, caption)
        if self.mode == "visitor" or self.mode == "room" and self.section == "basic":
            self.start_weather()
            self.update_weather()
            if self.weather_good is not None and monotonic() - self.weather_good > 1800:
                self.weather_text.set(
                    "Weather older than 30 minutes:\n" + self.weather_last_text
                )
        self.update_health()

    def close(self, reason):
        if self.closed or self.closing:
            return
        if self.keep_switcher and reason in (
            "exit",
            "timeout",
            "escape",
            "window_close",
        ):
            self.show("original")
            return
        if self.power_busy() and self.power.phase != "executing":
            self.power.fail("Power action cancelled while the panel is closing.")
        self.closing = reason
        if getattr(self, "control_bridge", None):
            self.control_bridge.close()
            self.control_bridge = None
        if getattr(self, "weather_worker", None) and self.weather_worker.poll() is None:
            self.weather_worker.kill()
        if self.status_worker and self.status_worker.poll() is None:
            self.status_worker.terminate()
        self.cancel_intent()
        if self.worker and self.light_state in ("ready", "applying", "connecting"):
            self.release_target = "close"
            self.status_text.set(
                "Closing panel. Keeping current light settings..."
                if self.keep_switcher
                else "Ending trial. Restoring starting light settings..."
            )
            if not self.pending:
                self.request("release")
        elif self.worker:
            self.worker.stdin.close()
        else:
            self.finish_close()

    def finish_close(self):
        if not self.closed:
            if getattr(getattr(self, "recovery", None), "pending", False):
                self.root.after(50, self.finish_close)
                return
            if getattr(self, "legacy_process", None) is not None or getattr(self, "legacy_previous_pid", None) is not None:
                self.stop_legacy()
                self.root.after(50, self.finish_close)
                return
            if getattr(self, "preferences", None):
                self.preferences.close()
                if not self.preferences.done.is_set():
                    self.root.after(50, self.finish_close)
                    return
            if getattr(self, "weather_worker", None):
                if self.weather_worker.poll() is None:
                    self.weather_worker.kill()
                    self.root.after(50, self.finish_close)
                    return
                self.weather_worker.stdout.close()
                if self.weather_worker.stderr:
                    self.weather_worker.stderr.close()
                self.weather_worker = None
            if not self.journal.closing:
                self.emit(
                    "panel_closed",
                    reason=self.closing or "mainloop_exit",
                    light_state=self.light_state,
                )
                self.journal.close()
            if not self.journal.done.is_set():
                self.root.after(50, self.finish_close)
                return
            self.poll_journal()
            try:
                if sys.stderr is not None:
                    if self.journal.error:
                        sys.stderr.write(
                            "Panel journal shutdown failed: " + self.journal.error + "\n"
                        )
                    if getattr(self, "preferences", None) and self.preferences.error:
                        sys.stderr.write(
                            "Appearance settings shutdown failed: "
                            + self.preferences.error
                            + "\n"
                        )
                    sys.stderr.flush()
            except (IOError, OSError, ValueError):
                pass  # A broken diagnostic stream must not interrupt completed cleanup.
            self.closed = True
            if self.worker:
                self.worker.stdin.close()
            if hasattr(self.root, "tk"):
                for timer in self.root.tk.call("after", "info"):
                    self.root.after_cancel(timer)
            self.root.destroy()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--duration",
        type=float,
        default=600,
        help="Trial lifetime: 1..1800 s; 0 requires --keep-switcher",
    )
    parser.add_argument(
        "--keep-switcher",
        action="store_true",
        help="Keep touch navigation above Original after leaving the new interface",
    )
    parser.add_argument(
        "--start-mode",
        choices=["room", "original"],
        default="room",
        help="Initial view with --keep-switcher",
    )
    parser.add_argument(
        "--control-socket",
        help="Private local socket for the optional trusted-network browser gateway",
    )
    parser.add_argument(
        "--journal",
        help="New private JSONL UI journal; never an existing recording context file",
    )
    parser.add_argument(
        "--preferences",
        help="Private appearance JSON file; saved choices override appearance CLI defaults",
    )
    parser.add_argument(
        "--weather-latitude",
        type=float,
        help="Optional model weather location, -90..90 degrees",
    )
    parser.add_argument(
        "--weather-longitude",
        type=float,
        help="Optional model weather location, -180..180 degrees",
    )
    parser.add_argument(
        "--weather-name",
        default="Local area",
        help="Short display name for the configured weather location",
    )
    parser.add_argument(
        "--logo",
        default=os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "assets",
            "lesa-logo.jpeg",
        ),
        help="Original local logo; no asset is modified",
    )
    parser.add_argument("--theme", choices=["auto", "light", "dark"], default="auto")
    parser.add_argument(
        "--light-at", type=clock_minutes, default=420, help="Local HH:MM, default 07:00"
    )
    parser.add_argument(
        "--dark-at", type=clock_minutes, default=1140, help="Local HH:MM, default 19:00"
    )
    parser.add_argument(
        "--timezone",
        default="America/New_York",
        help="Process-local timezone for schedule and clock",
    )
    parser.add_argument(
        "--clock-format",
        choices=["12", "24"],
        default="24",
        help="Clock style; also adjustable in Settings",
    )
    parser.add_argument(
        "--temperature-unit",
        choices=["c", "f"],
        default="f",
        help="Weather display unit; also adjustable in Settings",
    )
    parser.add_argument(
        "--idle-timeout",
        type=int,
        choices=[0, 60, 300, 900],
        default=300,
        help="Idle clock/weather after seconds; 0 disables. Default 300; adjustable in Screen settings",
    )
    parser.add_argument(
        "--font",
        default="Cantarell",
        help="An installed font family; default Cantarell",
    )
    parser.add_argument(
        "--tips",
        choices=["on", "off"],
        default="on",
        help="Short touch explanations; also switchable in the header",
    )
    parser.add_argument(
        "--dark-brand",
        choices=["wordmark", "original"],
        default="original",
        help="Compatibility option; the original logo is retained in both themes",
    )
    parser.add_argument(
        "--adapter-python",
        default="/usr/bin/python2.7",
        help="Installed ROS interpreter, independent of the UI",
    )
    parser.add_argument(
        "--status-url",
        default=os.environ.get("SCR_STATUS_URL"),
        help="Existing Legacy programme service, from private deployment configuration",
    )
    parser.add_argument(
        "--expected-master",
        default=os.environ.get("SCR_PANEL_MASTER"),
        help="Approved ROS_MASTER_URI, or private SCR_PANEL_MASTER environment setting",
    )
    parser.add_argument(
        "--live-lights",
        action="store_true",
        help="Existing ROS environment; requires --journal and fresh owner check",
    )
    parser.add_argument(
        "--windowed",
        action="store_true",
        help="Local 1280x800 review without screen-size enforcement",
    )
    parser.add_argument("--classic-dir", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        help="Preserved original main.py directory")
    parser.add_argument("--classic-python", default="/usr/bin/python2.7",
                        help="Installed interpreter for the original app")
    parser.add_argument("--lighting-state", help="Private persistent lighting ownership state; separate from appearance")
    args = parser.parse_args(argv)
    if (
        (args.weather_latitude is None) != (args.weather_longitude is None)
        or args.weather_latitude is not None
        and not (
            -90 <= args.weather_latitude <= 90 and -180 <= args.weather_longitude <= 180
        )
    ):
        parser.error("Weather needs both valid latitude and longitude")
    global FONT
    FONT = args.font
    ui_widgets.FONT = args.font
    if (
        math.isnan(args.duration)
        or math.isinf(args.duration)
        or not (1 <= args.duration <= 1800 or args.keep_switcher and args.duration == 0)
    ):
        parser.error(
            "Duration must be finite in 1..1800 seconds, or 0 with --keep-switcher"
        )
    if args.light_at == args.dark_at:
        parser.error("Light and dark start times must differ")
    if args.live_lights and (not args.journal or not sys.platform.startswith("linux")):
        parser.error(
            "Live lights require Linux, a new journal and the existing ROS environment"
        )
    if args.live_lights and not args.expected_master:
        parser.error("Live lights require --expected-master or SCR_PANEL_MASTER")
    os.environ["TZ"] = args.timezone
    if hasattr(time, "tzset"):
        time.tzset()
    panel = Panel(args)
    signal.signal(
        signal.SIGTERM, lambda signum, frame: panel.close("signal_%d" % signum)
    )
    signal.signal(
        signal.SIGINT, lambda signum, frame: panel.close("signal_%d" % signum)
    )
    try:
        panel.root.mainloop()
    finally:
        if not panel.closed:
            if panel.worker:
                panel.worker.stdin.close()
                panel.worker.wait()
            panel.journal.close()
            panel.journal.thread.join(timeout=2)
            panel.finish_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
