#!/usr/bin/env python
"""Run the preserved original UI with the configured room client environment.

The original window stays hidden while Beta covers the screen, so taps meant for
Beta can never reach Legacy buttons. Beta sends SIGUSR2 about once a second while
it covers the screen and SIGUSR1 when the user opens Legacy. Without a cover
signal for a few seconds (Beta closed, crashed or frozen) Legacy shows itself.
"""

from __future__ import print_function
import argparse
import os
import runpy
import signal
import sys
import time

COVER_SECONDS = 5
PID_FILE = os.path.expanduser("~/.cache/scr-panel/original.pid")


def clock():
    return time.monotonic() if hasattr(time, "monotonic") else time.time()


def hide_while_covered(tkinter):
    """Show or hide the first Tk window from cover signals; main.py stays unchanged."""
    covered = {"at": None}
    original_init = tkinter.Tk.__init__

    def cover(signum, frame):
        covered["at"] = clock()

    def uncover(signum, frame):
        covered["at"] = None

    def init(window, *args, **kwargs):
        original_init(window, *args, **kwargs)
        tkinter.Tk.__init__ = original_init

        def follow():
            hidden = covered["at"] is not None and clock() - covered["at"] < COVER_SECONDS
            try:
                if hidden and window.state() != "withdrawn":
                    window.withdraw()
                elif not hidden and window.state() == "withdrawn":
                    window.deiconify()
                    window.attributes("-fullscreen", True)
                    window.lift()
            except tkinter.TclError:
                return
            window.after(250, follow)

        window.after(250, follow)

    signal.signal(signal.SIGUSR2, cover)
    signal.signal(signal.SIGUSR1, uncover)
    tkinter.Tk.__init__ = init
    # Only a Legacy that handles the signals advertises itself; older ones are left alone.
    try:
        directory = os.path.dirname(PID_FILE)
        if not os.path.isdir(directory):
            os.makedirs(directory)
        with open(PID_FILE, "w") as stream:
            stream.write(str(os.getpid()) + "\n")
    except OSError:
        pass


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--classic-dir",
        default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        help="Preserved original main.py directory; room clients must already be on PYTHONPATH",
    )
    args = parser.parse_args(argv)
    directory = os.path.realpath(args.classic_dir)
    if not os.path.isfile(os.path.join(directory, "main.py")):
        parser.error("Original main.py is missing from --classic-dir")
    if sys.version_info[0] >= 3:
        import tkinter
        import tkinter.font

        sys.modules["Tkinter"] = tkinter
        sys.modules["tkFont"] = tkinter.font
    else:
        import Tkinter as tkinter
    from PIL import Image

    if not hasattr(Image, "ANTIALIAS"):
        Image.ANTIALIAS = getattr(Image, "Resampling", Image).LANCZOS
    if sys.platform.startswith("linux"):
        hide_while_covered(tkinter)
    os.chdir(directory)
    sys.path.insert(0, directory)
    runpy.run_path(os.path.join(directory, "main.py"), run_name="__main__")


if __name__ == "__main__":
    main()
