# PipeGuard developer entry points.
COMPOSE := docker compose -f infra/docker-compose.yml

ifeq ($(OS),Windows_NT)
PY ?= .venv\Scripts\python.exe
else
PY ?= .venv/bin/python
endif

.PHONY: up down test lint sim demo eval firmware-test install clean

install:
	$(PY) -m pip install -e "simulator[dev,mqtt]" -e "backend[dev,opcua]" -e "plc_sim[dev,opcua]"
	cd dashboard && npm install

up:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down -v

test:
	$(PY) -m pytest simulator/tests backend/tests plc_sim/tests -q

eval:
	$(PY) -m pipeguard_backend.main --evaluate

lint:
	$(PY) -m ruff check simulator/src simulator/tests backend/src backend/tests plc_sim/src plc_sim/tests
	$(PY) -m mypy simulator/src/pipeguard_sim backend/src/pipeguard_backend plc_sim/src/plc_sim
	cd dashboard && npm run lint && npm run build
	docker build -q -f firmware/Dockerfile --target builder firmware >/dev/null

sim:
	$(PY) -m pipeguard_sim.cli --scenario all --duration 60 --out features.jsonl

demo:
	$(PY) scripts/demo.py

firmware-test:
	$(COMPOSE) run --rm firmware-test cargo test --release

clean:
	$(COMPOSE) down -v --remove-orphans
	rm -rf .pytest_cache .mypy_cache .ruff_cache
