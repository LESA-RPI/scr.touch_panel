#!/bin/bash
# Diyanko Bhowmik. Private deployment values stay outside this checkout.
set -eu
config=${1:-"$HOME/.config/scr-panel/deployment.env"}
test -r "$config" || { echo "Missing private deployment configuration: $config" >&2; exit 1; }
. "$config"
: "${SCR_CLASSIC_DIR:?Set the installed original checkout}"
: "${SCR_ROS_SETUP:?Set the installed ROS workspace setup}"
: "${SCR_PANEL_MASTER:?Set the approved remote ROS master}"
classic_python=${SCR_CLASSIC_PYTHON:-/usr/bin/python2.7}
panel_python=${SCR_PANEL_PYTHON:-/usr/bin/python2.7}
adapter_python=${SCR_ADAPTER_PYTHON:-$classic_python}
start_mode=${SCR_START_MODE:-room}
case "$start_mode" in room|original) ;; *) echo 'SCR_START_MODE must be room or original' >&2; exit 1 ;; esac
SCR_CLASSIC_DIR=$(cd "$SCR_CLASSIC_DIR" && pwd -P)
app_dir=$(cd "$(dirname "$0")" && pwd -P)
export DISPLAY=${DISPLAY:-:0}
export PYTHONDONTWRITEBYTECODE=1
cache="$HOME/.cache/scr-panel"
mkdir -p "$cache/ros"
exec 9>"$cache/launcher.lock"
flock -n 9 || exit 0
# Installed ROS setup scripts can reference unset variables.
set +u
. "$SCR_ROS_SETUP"
set -u
export ROS_MASTER_URI="$SCR_PANEL_MASTER"
export SCR_PANEL_MASTER
export ROS_IP ROS_HOSTNAME
export ROS_LOG_DIR="$cache/ros"
sleep "${SCR_START_DELAY:-8}"
original_running=false
for pid in $(pgrep -f '[m]ain[.]py|[r]un_original[.]py' || true); do
    if test "$(readlink "/proc/$pid/cwd" 2>/dev/null || true)" = "$SCR_CLASSIC_DIR"; then
        original_running=true
        break
    fi
done
if ! $original_running; then
    (
        exec 9>&-
        cd "$SCR_CLASSIC_DIR"
        exec "$classic_python" -B "$app_dir/run_original.py" --classic-dir "$SCR_CLASSIC_DIR"
    ) >>"$cache/original.log" 2>&1 &
    classic_pid=$!
    sleep 2
    kill -0 "$classic_pid" 2>/dev/null || { echo 'Original panel failed to start; inspect original.log' >&2; exit 1; }
fi
run_dir=$(mktemp -d "$cache/panel-XXXXXXXX")
set -- --preferences "${SCR_PANEL_PREFERENCES:-$HOME/.config/scr-panel/appearance.json}"
if test -n "${SCR_WEATHER_LATITUDE:-}" && test -n "${SCR_WEATHER_LONGITUDE:-}"; then
    set -- "$@" --weather-latitude "$SCR_WEATHER_LATITUDE" --weather-longitude "$SCR_WEATHER_LONGITUDE" \
        --weather-name "${SCR_WEATHER_NAME:-Local area}"
fi
if test -n "${SCR_CONTROL_SOCKET:-}"; then
    set -- "$@" --control-socket "$SCR_CONTROL_SOCKET"
fi
exec "$panel_python" -B "$app_dir/scr_touch_panel.py" \
    --keep-switcher --start-mode "$start_mode" --live-lights --theme auto --duration 0 \
    --adapter-python "$adapter_python" \
    --journal "$run_dir/events.jsonl" "$@" >>"$cache/switcher.log" 2>&1
