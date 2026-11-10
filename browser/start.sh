#!/bin/sh
# Deployment values come from the independent user service's EnvironmentFile.
set -eu
set --
if test -n "${SCR_WEB_CONTROL_SOCKET:-}"; then
    set -- --panel-control-socket "$SCR_WEB_CONTROL_SOCKET"
elif test -n "${SCR_WEB_MASTER:-}"; then
    set -- --master "$SCR_WEB_MASTER"
fi
exec /usr/bin/python3 -B "$(dirname "$0")/serve.py" \
    --bind "${SCR_WEB_BIND:?Set the verified room interface address}" \
    --allow-clients "${SCR_WEB_CLIENTS:?Set the trusted room subnet}" \
    --port "${SCR_WEB_PORT:-8768}" --label "${SCR_WEB_LABEL:-Cabinet Pi}" "$@"
