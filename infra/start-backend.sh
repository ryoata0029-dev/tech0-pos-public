#!/bin/sh
set -eu
cd /home/site/wwwroot
# Deployment includes Linux-built .venv, app/, and an explicitly supplied trusted CA.
exec .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1 --no-access-log --log-level warning
