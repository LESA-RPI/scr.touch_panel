"""Shared presentation/state and actions, always called on the panel's Tk thread."""

from panel_guides import DEMO, SUPPORT
from command_reference import command_tokens
from help_reference import reference
import time
from panel_version import VERSION, BUILD_COMMIT


def snapshot(panel):
    busy = bool(
        panel.pending
        or panel.queued_intent
        or panel.release_target
        or panel.closing
        or panel.press_active
        or getattr(panel, "power_busy", lambda: False)()
    )
    lighting = bool(
        panel.args.live_lights
        and panel.light_state == "ready"
        and not busy
        and not panel.running
        and panel.mode not in ("original", "black")
    )
    elapsed = panel.elapsed + (
        time.monotonic() - panel.run_started if panel.running else 0
    )
    return {
        "version": 1,
        "app_version": VERSION,
        "build_commit": BUILD_COMMIT,
        "power": getattr(panel, "power_snapshot", lambda: None)(),
        "session": panel.run_id,
        "timezone": panel.args.timezone,
        "revision": "%s:%s:%s" % (panel.run_id, panel.sequence, panel.view_generation),
        "mode": panel.mode,
        "busy": busy,
        "can_control": lighting,
        "can_programme": getattr(panel, "programme_available", lambda: False)(),
        "can_session": not busy and panel.mode != "original",
        "lights": {
            "capabilities": getattr(panel, "light_capabilities", {}),
            "programme": getattr(panel, "programme", None),
            "programme_confirmed": False,
            "state": panel.light_state,
            "power": panel.confirmed_power if lighting else None,
            "scene": panel.confirmed_scene if lighting else None,
            "cct": panel.cct.get(),
            "intensity": panel.intensity.get(),
            "channels": [v.get() for v in panel.channel_values],
            "message": panel.light_message.replace(" input / level ", " · level "),
            "recent": panel.confirmed_light.replace(" input / level ", " · level "),
            "confirmed_age_s": (
                None
                if panel.confirmed_at is None
                else max(0, time.monotonic() - panel.confirmed_at)
            ),
        },
        "preferences": {
            "theme": panel.theme_choice,
            "resolved_theme": panel.theme,
            "clock": "24" if panel.clock_24 else "12",
            "temperature": panel.temperature_unit,
            "idle": panel.idle_timeout,
            "tips": panel.help_on,
            "blinds_display": panel.blinds_display,
            "blinds_enabled": panel.blinds_enabled,
            "light_at": panel.args.light_at,
            "dark_at": panel.args.dark_at,
        },
        "palette": {
            key: getattr(panel, key)
            for key in (
                "bg",
                "surface",
                "ink",
                "muted",
                "control",
                "border",
                "accent",
                "selected_ink",
                "icon_colour",
                "accent_pressed",
                "pressed",
                "good",
                "warning",
                "weather_warm",
                "weather_cool",
            )
        },
        "experiment": {
            "profile": panel.profile,
            "running": panel.running,
            "stage": panel.stage,
            "elapsed_s": int(elapsed),
            "annotation": panel.annotation_text.get(),
            "recording": False,
        },
        "guide": [
            {"title": title, "icon": kind, "text": text} for title, kind, text in DEMO
        ],
        "help": [
            {
                "title": title,
                "text": text,
                "commands": commands,
                "command_tokens": command_tokens(commands),
                "reference": reference(title),
            }
            for title, kind, text, commands in SUPPORT
        ],
        "weather": panel.weather_reading,
        "weather_age_s": (
            None
            if not panel.weather_good
            else max(0, time.monotonic() - panel.weather_good)
        ),
        "health": panel.health_cache,
        "room_status": panel.room_status,
        "blinds_enabled": panel.blinds_enabled,
        "blinds": panel.blind_state(),
    }


def execute(panel, request):
    action, args = request["action"], request["arguments"]
    state = snapshot(panel)
    if state["busy"]:
        raise RuntimeError(
            "The panel is busy. Wait for the current touch or command to finish."
        )
    if action in ("on", "off", "preset", "cct", "channels", "gradient"):
        if not state["can_control"]:
            raise RuntimeError(
                "Lighting is unavailable, uncertain, in Legacy or held by an experiment. Check the panel."
            )
        if panel.idle_active:
            panel.return_from_idle()
        if action == "on":
            panel.lights_on()
        elif action == "off":
            panel.preset("Off")
        elif action == "preset":
            panel.preset(args["name"])
        elif action == "cct":
            panel.cct.set(args["cct"])
            panel.intensity.set(args["intensity"])
            panel.apply("cct", immediate=True, **args)
        elif action == "gradient":
            if not state["lights"]["capabilities"].get("gradient"):
                raise RuntimeError("Gradient is unavailable from this controller.")
            panel.apply("gradient", immediate=True)
        else:
            for var, value in zip(panel.channel_values, args["values"]):
                var.set(value)
            panel.apply("channels", immediate=True, **args)
    elif action == "programme":
        if not panel.programme_command(args["name"]):
            raise RuntimeError("Programme controls are unavailable. Check the panel.")
    elif action == "blind":
        if not state["blinds"]["available"]:
            raise RuntimeError("Blinds · " + state["blinds"]["detail"])
        if not panel.blind_command(args["name"]):
            raise RuntimeError("Blind command was not accepted")
    elif action in ("start", "pause", "previous", "next", "mark"):
        if not state["can_session"]:
            raise RuntimeError("Return from Legacy before using instructions.")
        if action == "mark" and args["label"] not in panel.profile["annotations"]:
            raise ValueError("Unknown annotation label")
        panel.open_advanced("experiment")
        if action == "start":
            panel.start_preview()
        elif action == "pause":
            panel.stop_preview()
        elif action == "previous":
            panel.previous_stage()
        elif action == "next":
            panel.next_stage()
        else:
            panel.mark(args["label"])
    elif action in ("home", "legacy", "original_fallback", "blank", "clock_view"):
        if panel.running and action not in ("home", "legacy"):
            raise RuntimeError("Pause the instructions before switching the panel.")
        if action == "home":
            panel.open_home()
        else:
            panel.show(
                {"legacy": "classic", "original_fallback": "original", "blank": "black", "clock_view": "visitor"}[
                    action
                ]
            )
    elif action == "power":
        panel.request_power(args["operation"], confirmed=args["confirmed"])
    elif action == "schedule":
        panel.adjust_schedule(args["which"], args["delta"])
    else:
        methods = {
            "theme": panel.choose_theme,
            "clock": panel.choose_clock,
            "temperature": panel.choose_temperature,
            "idle": panel.choose_idle,
            "blinds_display": panel.choose_blinds_display,
            "blinds_enabled": panel.choose_blinds_enabled,
            "tips": panel.choose_tips,
        }
        methods[action](args["value"])
    panel.emit(
        "browser_command",
        command_id=request["id"],
        action=action,
        helper_request_id=panel.pending.get("request_id") if panel.pending else None,
    )
    panel.activity(False)
    return {
        "ok": True,
        "code": 202,
        "detail": "Accepted by the panel. Lighting changes still need controller confirmation.",
    }
