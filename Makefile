PY := backend/.venv/bin/python

.PHONY: install lint typecheck test contract build check smoke dev-backend dev-frontend start-frontend

install:
	$(PY) -m pip install --require-hashes --only-binary=:all: -r backend/requirements-dev.lock
	sh tools/frontend.sh ci --ignore-scripts --strict-peer-deps

lint:
	cd backend && .venv/bin/ruff check app tests ../tools
	cd backend && .venv/bin/ruff format --check app tests ../tools
	sh tools/frontend.sh run lint

typecheck:
	cd backend && .venv/bin/mypy
	sh tools/frontend.sh run typecheck

test:
	cd backend && .venv/bin/python -m unittest discover -s tests -v
	sh tools/frontend.sh run test

contract:
	$(PY) tools/validate_openapi.py

build:
	cd backend && .venv/bin/python -m build --no-isolation
	sh tools/frontend.sh run build

check: lint typecheck test contract

smoke:
	$(PY) tools/smoke.py

dev-backend:
	cd backend && .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log

dev-frontend:
	sh tools/frontend.sh run dev

start-frontend:
	sh tools/frontend.sh run start
