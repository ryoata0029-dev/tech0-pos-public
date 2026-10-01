#!/bin/sh
set -eu
cd /home/site/wwwroot
# A Linux standalone Next build; no dependency install or build during startup.
export PORT="${PORT:-8080}"
export HOSTNAME=0.0.0.0
exec node server.js
