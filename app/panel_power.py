"""Fixed, noninteractive Pi power actions; no shell, new grants or Tk calls."""

import subprocess
import threading

SYSTEMCTL = "/usr/bin/systemctl"
VERBS = {"reboot": "reboot", "shutdown": "poweroff"}


def run(arguments):
    return subprocess.run(
        arguments,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=8,
        check=False,
    )


class PowerActions:
    def __init__(self, enabled=False, runner=run):
        self.runner = runner
        self.commands = {}
        self.phase = "checking" if enabled else "unavailable"
        self.message = (
            "Checking power controls…"
            if enabled
            else "Power controls are available on the installed Pi."
        )
        self.operation = None
        self.worker = None
        if enabled:
            self._start(self._probe)

    @property
    def busy(self):
        return self.phase in ("restoring", "saving", "executing")

    def _start(self, function):
        self.worker = threading.Thread(
            target=function, name="scr-panel-power", daemon=True
        )
        self.worker.start()

    def _probe(self):
        try:
            help_text = self.runner([SYSTEMCTL, "--help"]).stdout
            if "--check-inhibitors" not in help_text:
                raise RuntimeError(
                    "Safe power controls are unavailable on this system."
                )
            commands = {}
            for operation, verb in VERBS.items():
                command = [
                    SYSTEMCTL,
                    "--check-inhibitors=yes",
                    "--no-ask-password",
                    verb,
                ]
                method = "CanReboot" if operation == "reboot" else "CanPowerOff"
                reply = self.runner(
                    [
                        "/usr/bin/busctl",
                        "call",
                        "org.freedesktop.login1",
                        "/org/freedesktop/login1",
                        "org.freedesktop.login1.Manager",
                        method,
                    ]
                )
                if reply.returncode == 0 and reply.stdout.strip() == 's "yes"':
                    commands[operation] = command
                else:
                    # Use an existing noninteractive grant only; never install sudoers
                    # rules, prompt for a password or accept arbitrary commands.
                    reply = self.runner(["/usr/bin/sudo", "-n", "-l", "--"] + command)
                    if reply.returncode == 0:
                        commands[operation] = ["/usr/bin/sudo", "-n", "--"] + command
            self.commands = commands
            self.phase = "ready" if commands else "unavailable"
            self.message = (
                "Restart or shut down this Pi after confirmed cleanup."
                if commands
                else "Power controls need permission on this Pi. Ask its maintainer."
            )
        except (OSError, subprocess.TimeoutExpired, RuntimeError):
            self.phase = "unavailable"
            self.message = "Power controls could not be checked. Use the Pi’s normal shutdown controls."

    def prepare(self, operation):
        if self.phase != "ready" or operation not in self.commands:
            raise RuntimeError("This power action is unavailable. Check the panel.")
        self.operation = operation
        self.phase = "restoring"
        self.message = "Finishing lighting control before " + (
            "restart…" if operation == "reboot" else "shutdown…"
        )

    def fail(self, message):
        self.phase = "failed"
        self.message = message

    def execute(self):
        if self.phase != "saving":
            raise RuntimeError("Confirmed cleanup and saved state are required.")
        command = tuple(self.commands[self.operation])
        self.phase = "executing"
        self.message = (
            "Restarting panel…"
            if self.operation == "reboot"
            else "Shutting down panel…"
        )

        def execute_once():
            try:
                result = self.runner(list(command))
                if result.returncode:
                    self.fail(
                        "Power action was refused. Check the Pi; no retry was sent."
                    )
            except (OSError, subprocess.TimeoutExpired):
                self.fail(
                    "Power result is unconfirmed. Check the Pi before trying again."
                )

        self._start(execute_once)
