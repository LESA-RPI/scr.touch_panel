"""Private same-user client for the panel's existing lighting ownership bridge."""

import argparse
import json
import socket
import time
import uuid


def exchange(path, value):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(4)
        client.connect(path)
        client.sendall(json.dumps(value).encode() + b"\n")
        with client.makefile("rb") as stream:
            raw = stream.readline(65537)
    if len(raw) > 65536 or not raw.endswith(b"\n"):
        raise RuntimeError("Invalid panel reply; do not repeat an ownership request")
    return json.loads(raw)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", required=True, help="Existing private panel control socket")
    parser.add_argument("action", choices=("status", "reserve", "heartbeat", "finish", "recover"))
    parser.add_argument("--token", help="Fresh private token chosen by the experiment; retain until finish")
    parser.add_argument("--label", default="Experiment", help="Public room label; no participant details")
    parser.add_argument("--owner-closed", action="store_true", help="Verified previous experiment/controller and all its workers have stopped")
    parser.add_argument("--pending-clear", action="store_true", help="Verified no server lighting request remains pending")
    args = parser.parse_args(argv)
    state = exchange(args.socket, {"op": "read"})
    if not state.get("available"):
        raise RuntimeError("Panel unavailable; no ownership has been granted")
    if args.action == "status":
        print(json.dumps({"lighting_recovery": state.get("lighting_recovery"), "can_control": state.get("can_control"), "lights": state.get("lights")}))
        return 0
    if args.action in ("reserve", "heartbeat", "finish") and not args.token:
        parser.error("This action requires the retained private --token")
    arguments = {}
    if args.action in ("reserve", "heartbeat", "finish"):
        arguments["token"] = args.token
    if args.action == "reserve":
        arguments["label"] = args.label
    if args.action in ("finish", "recover"):
        if not args.owner_closed or not args.pending_clear:
            parser.error("Confirm --owner-closed and --pending-clear after checking actual processes and handlers")
        arguments.update(owner_closed=True, pending_clear=True)
    reply = exchange(args.socket, dict(op="lighting_handoff", id=uuid.uuid4().hex, revision=state["revision"], action=args.action, arguments=arguments))
    if not reply.get("ok"):
        raise RuntimeError(reply.get("detail", "Ownership was not accepted"))
    deadline = time.monotonic() + 45
    while True:
        state = exchange(args.socket, {"op": "read"})
        recovery = state.get("lighting_recovery", {})
        if not state.get("available"):
            raise RuntimeError("Panel connection lost; ownership is unconfirmed. Do not retry or start control.")
        status = recovery.get("status")
        done = status == "reserved" if args.action in ("reserve", "heartbeat") else (status == "normal" and state.get("can_control") and state.get("lights", {}).get("state") == "ready")
        if done:
            if args.action in ("reserve", "heartbeat"):
                # Confirm this caller's reservation, not another experiment's
                # subsequently observed public 'reserved' state.
                proof = exchange(args.socket, dict(op="lighting_handoff", id=uuid.uuid4().hex, revision=state["revision"], action="heartbeat", arguments={"token": args.token}))
                if not proof.get("ok"):
                    raise RuntimeError("The current reservation does not confirm this experiment's ownership")
            print(json.dumps({"ok": True, "lighting_recovery": recovery, "can_control": state.get("can_control")}))
            return 0
        if status in ("needs_staff", "uncertain") or time.monotonic() >= deadline:
            raise RuntimeError("Ownership handoff remains unconfirmed. Check the panel; do not repeat the request.")
        time.sleep(.2)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as error:
        print(json.dumps({"ok": False, "detail": str(error)}))
        raise SystemExit(2)
