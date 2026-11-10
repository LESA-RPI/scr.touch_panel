#!/bin/bash
# Diyanko Bhowmik. Private deployment values stay outside this checkout.
set -eu
config=${1:-"$HOME/.config/scr-panel/deployment.env"}
test -r "$config" || { echo "Missing private deployment configuration: $config" >&2; exit 1; }
. "$config"
umask 077
: "${SCR_CLASSIC_DIR:?Set the installed original checkout}"
: "${SCR_ROS_SETUP:?Set the installed ROS workspace setup}"
: "${SCR_PANEL_MASTER:?Set the approved remote ROS master}"
classic_python=${SCR_CLASSIC_PYTHON:-/usr/bin/python2.7}
panel_python=${SCR_PANEL_PYTHON:-/usr/bin/python3}
adapter_python=${SCR_ADAPTER_PYTHON:-$classic_python}
start_mode=${SCR_START_MODE:-room}
case "$start_mode" in room|classic|original) ;; *) echo 'SCR_START_MODE must be room, classic or original' >&2; exit 1 ;; esac
SCR_CLASSIC_DIR=$(cd "$SCR_CLASSIC_DIR" && pwd -P)
app_dir=$(cd "$(dirname "$0")" && pwd -P)
export DISPLAY=${DISPLAY:-:0}
export PYTHONDONTWRITEBYTECODE=1
cache="$HOME/.cache/scr-panel"
mkdir -p "$cache/ros"
chmod 700 "$cache" "$cache/ros"
exec 9>"$cache/launcher.lock"
flock -n 9 || exit 0
# Rotate before ROS setup, Legacy or the panel can append to these files.
"$panel_python" - "$cache" <<'PY'
from pathlib import Path
import sys

cache = Path(sys.argv[1])
for name in ("original.log", "switcher.log", "launcher.log"):
    path = cache / name
    if path.is_file() and path.stat().st_size >= 5 * 1024 * 1024:
        path.replace(cache / (name + ".1"))
PY
# Reopen an inherited launcher log after rotation as well.
exec >>"$cache/launcher.log" 2>&1
# Validate before starting Legacy or sourcing the room environment. The ROS
# adapter keeps its independently configured interpreter.
"$panel_python" -c 'import sys; sys.version_info >= (3, 11) or sys.exit("The touch panel requires Python 3.11 or later"); import tkinter; from PIL import Image' || {
    echo 'The touch panel needs Python 3.11+, Tk and Pillow. Check SCR_PANEL_PYTHON.' >&2
    exit 1
}
# Installed ROS setup scripts can reference unset variables.
set +u
. "$SCR_ROS_SETUP"
set -u
export ROS_MASTER_URI="$SCR_PANEL_MASTER"
export SCR_PANEL_MASTER
export ROS_IP ROS_HOSTNAME
export ROS_LOG_DIR="$cache/ros"
sleep "${SCR_START_DELAY:-8}"
run_dir=$(mktemp -d "$cache/panel-XXXXXXXX")
"$panel_python" - "$cache" "$run_dir" <<'PY'
from pathlib import Path
import shutil
import sys

cache, current = (Path(value).resolve() for value in sys.argv[1:])
runs = sorted((path for path in cache.glob("panel-????????")
               if path.is_dir() and not path.is_symlink() and path != current),
              key=lambda path: path.stat().st_mtime, reverse=True)
for path in runs[9:]:
    if path.resolve().parent != cache:
        raise ValueError("Run directory outside panel cache")
    shutil.rmtree(path)
PY
set -- --preferences "${SCR_PANEL_PREFERENCES:-$HOME/.config/scr-panel/appearance.json}"
if test -n "${SCR_WEATHER_LATITUDE:-}" && test -n "${SCR_WEATHER_LONGITUDE:-}"; then
    set -- "$@" --weather-latitude "$SCR_WEATHER_LATITUDE" --weather-longitude "$SCR_WEATHER_LONGITUDE" \
        --weather-name "${SCR_WEATHER_NAME:-Local area}"
fi
if test -n "${SCR_CONTROL_SOCKET:-}"; then
    set -- "$@" --control-socket "$SCR_CONTROL_SOCKET"
fi
if test -n "${SCR_STATUS_URL:-}"; then
    set -- "$@" --status-url "$SCR_STATUS_URL"
fi
export SCR_ROOM_NETWORK_NAME SCR_ROOM_NETWORK_PASSWORD
exec "$panel_python" -B "$app_dir/scr_touch_panel.py" \
    --keep-switcher --start-mode "$start_mode" --live-lights --theme auto --duration 0 \
    --adapter-python "$adapter_python" \
    --classic-python "$classic_python" --classic-dir "$SCR_CLASSIC_DIR" \
    --journal "$run_dir/events.jsonl" "$@" >>"$cache/switcher.log" 2>&1
