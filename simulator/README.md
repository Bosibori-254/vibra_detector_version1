# PipeGuard Simulator

Software replacement for field sensor nodes. Generates deterministic 3-axis
acceleration, pressure, node health and feature messages for every fault class:
normal, cavitation, resonance, water hammer, loose support, leak/third-party
interference, imbalance/misalignment, and sensor failure.

## Install

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e simulator[dev]   # Windows
# source .venv/bin/activate && pip install -e simulator[dev]  # Linux/macOS
```

## Run

```bash
python -m pipeguard_sim.cli --scenario cavitation --duration 20 --out features.jsonl
python -m pipeguard_sim.cli --scenario all --duration 60 --out all.jsonl
python -m pipeguard_sim.cli --scenario mixed --mqtt --broker localhost --pace
```

`--key` enables HMAC-SHA256 signing with a per-device secret. MQTT publishing
requires the optional `mqtt` extra (`pip install -e simulator[mqtt]`).

## Tests

```bash
pytest simulator/tests -q
```

Phase 1 scope: signal generation, DSP features, message schema and scenario
runner. MQTT publishing is used by the Phase 8 end-to-end demo.
