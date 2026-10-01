#!/bin/sh
# Prefer the isolated M0 runtime; otherwise require the pinned version on PATH.
set -eu
POS_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
POS_NODE_BIN="$POS_ROOT/.m0-cache/fnm/node-versions/v24.21.0/installation/bin"
if [ -x "$POS_NODE_BIN/node" ]; then
    PATH="$POS_NODE_BIN:$PATH"
    export PATH
fi
if [ "$(node --version)" != "v$(cat "$POS_ROOT/.node-version")" ]; then
    echo 'Use the Node.js version recorded in .node-version.' >&2
    exit 1
fi
export NEXT_TELEMETRY_DISABLED=1
cd "$POS_ROOT/frontend"
exec npm "$@"
