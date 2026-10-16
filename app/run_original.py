#!/usr/bin/env python
"""Run the preserved original UI with the configured room client environment."""

from __future__ import print_function
import argparse
import os
import runpy
import sys


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
    from PIL import Image

    if not hasattr(Image, "ANTIALIAS"):
        Image.ANTIALIAS = getattr(Image, "Resampling", Image).LANCZOS
    os.chdir(directory)
    sys.path.insert(0, directory)
    runpy.run_path(os.path.join(directory, "main.py"), run_name="__main__")


if __name__ == "__main__":
    main()
