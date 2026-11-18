#!/usr/bin/env bash
set -e
source /opt/ros/jazzy/setup.bash
export VIRTUAL_ENV=/opt/robopilot-venv
export PATH="$VIRTUAL_ENV/bin:$PATH"
exec "$@"
