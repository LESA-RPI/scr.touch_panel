#!/usr/bin/env python
"""Read-only original Tk response check, bounded by the caller's subprocess timeout.

The caller must cover Legacy first so it cannot accept further input, and verify
the expected process identity before and after this check. A response means its
current Tk callback has returned; it does not prove a remote hardware handler has
finished. No original application code, widgets or variables are changed.
"""

from __future__ import print_function

import argparse
import json
import sys


QUERY = "list [pid] [winfo exists .] [wm title .]"


def process_identity(pid):
    """Require flushed original logs and retain this exact process across the query."""
    with open("/proc/%d/cmdline" % pid, "rb") as stream:
        args = stream.read().decode("utf-8").split("\0")[:-1]
    try:
        wrapper = next(index for index, arg in enumerate(args)
                       if arg.endswith("/run_original.py"))
    except StopIteration:
        raise ValueError("The expected original process is not running its wrapper")
    if "-u" not in args[1:wrapper]:
        raise ValueError("Original logging must be unbuffered (-u) before automatic return")
    with open("/proc/%d/stat" % pid) as stream:
        start_ticks = stream.read().rsplit(")", 1)[1].split()[19]
    return tuple(args), start_ticks


def probe(interpreter, expected_pid):
    """Accept exactly one responding original root belonging to the expected PID."""
    if isinstance(expected_pid, bool) or not isinstance(expected_pid, int) or expected_pid <= 0:
        raise ValueError("A positive original process ID is required")
    own_name = interpreter.call("tk", "appname")
    names = interpreter.splitlist(interpreter.call("winfo", "interps"))
    if len(names) != len(set(names)):
        raise ValueError("Tk application identities are ambiguous")
    matches = []
    for name in names:
        if name == own_name:
            continue
        # Separate Tcl arguments keep application names as data. The fixed script
        # reads only built-in process/window information in the target event loop.
        response = interpreter.splitlist(interpreter.call("send", "--", name, QUERY))
        if len(response) != 3:
            raise ValueError("A Tk application returned an invalid identity")
        try:
            pid, exists = int(response[0]), int(response[1])
        except (TypeError, ValueError):
            raise ValueError("A Tk application returned an invalid identity")
        if pid == expected_pid and exists == 1:
            matches.append({"pid": pid, "app_name": name, "title": response[2]})
    if len(matches) != 1:
        raise ValueError("The exact original process did not identify one responsive Tk root")
    result = dict(matches[0], version=1, idle=True)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", required=True, type=int,
                        help="Exact original process ID verified by the parent")
    args = parser.parse_args(argv)
    root = None
    try:
        if args.pid <= 0:
            raise ValueError("A positive original process ID is required")
        identity = process_identity(args.pid)
        try:
            import tkinter as tk
        except ImportError:
            import Tkinter as tk
        root = tk.Tk()
        root.withdraw()
        result = probe(root.tk, args.pid)
        if process_identity(args.pid) != identity:
            raise ValueError("The original process changed during the connection check")
        result["start_ticks"] = identity[1]
    except Exception as error:
        result = {"version": 1, "idle": False, "error": str(error)}
    finally:
        if root is not None:
            try:
                root.destroy()
            except Exception:
                pass
    print(json.dumps(result, ensure_ascii=True))
    return 0 if result["idle"] else 1


if __name__ == "__main__":
    sys.exit(main())
