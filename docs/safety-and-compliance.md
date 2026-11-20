# PipeGuard Safety Case and Compliance Context

**Document status:** design-basis safety case for a software prototype.
This document states the assumptions, hazard controls and limits of the
PipeGuard prototype. It is not a certification dossier.

## 1. Intended function and boundaries

PipeGuard monitors pipeline/pump vibration, diagnoses probable causes, and may
issue **bounded, reversible setpoint changes** to a VFD or valve rate through
OPC UA / Modbus TCP. It reports alarms and recommendations to a control room.

**Out of scope / explicitly forbidden:**

- Any write to SIS, ESD, emergency shutdown, trip or mainline isolation systems.
- Automatic closure of mainline valves (leak/damage → critical alarm + human
  confirmation only).
- Any safety-instrumented function or protective relay duty.
- Operation as the sole protective layer for personnel or asset safety.

## 2. Assumptions

- Field devices are installed in hazardous (Zone 2 / Division 2) areas using
  ATEX/IECEx-certified intrinsically safe sensors, barriers and enclosures.
  The prototype assumes certified hardware exists; it does not certify it.
- The existing process control system and SIS are independent and remain the
  authoritative protection layers. PipeGuard is an advisory/optimisation layer
  connected through a read-mostly data diode or DMZ in production.
- Sensors are accelerometers (ADXL355/MPU6050 class) sampled 1–4 kHz; sampling,
  DSP and local detection occur on the edge node.
- Network is a managed industrial network with MQTT/TLS and per-device
  identities; SCADA integration uses OPC UA.
- Vibration limits are asset-specific and must be set by vibration engineers;
  ISO 10816/20816 zones in `backend/config/default.yaml` are placeholders.

## 3. Hazard analysis (summary)

| Hazard | Control | Verification |
|---|---|---|
| Unbounded actuator command | min/max, max-step, rate limit, cooldown, envelope gates G3–G5 | `backend/tests/test_safety.py` |
| Command to SIS/ESD | explicit deny-list in G4/G6 | safety tests with `sis_*`, `esd_*` tags |
| Automation active during sensor fault | G2 fail-safe + sensor-fault diagnosis dominates | tests + `test_demo_scenarios` |
| Stale/duplicate telemetry drives action | HMAC verification, sequence monotonicity, lateness tagging, G2 freshness | ingestion + safety tests |
| Unwanted actuation on leak | leak policy is `recommend_isolation`; G1 blocks AUTO for leak | safety + engine tests |
| Operator cannot stop automation | global kill switch (admin) and per-segment AUTO opt-in | API + gate tests |
| Action makes vibration worse | post-action verification with rollback + escalation | controller tests |
| Undetected/unauthorized change | immutable action audit log with who/what/why/before/after | repository tests |
| Alarm flapping | debounce N-of-M, hysteresis, persistence timers | detector tests |
| Cyber compromise of node | TLS, per-device HMAC keys, signed config, JWT RBAC (viewer/operator/engineer/admin) | security tests |
| Loss of comms | no command on missing/LWT-offline telemetry; fail-safe alarm | integration scenario |

## 4. Safety requirements → implementation

| Safety requirement | Code location |
|---|---|
| Never write SIS/ESD | `rules/safety.py` deny-list in G4/G6; `api/app.py` manual-control check |
| Default ADVISORY; per-segment AUTO opt-in | `config/policies.yaml`, `rules/engine.py::mode_for` |
| Kill switch | `rules/engine.py::set_kill_switch`, G0, `/api/kill-switch` |
| Bounds/step/rate/cooldown/envelope | G3–G5 in `rules/safety.py` |
| Two-person/human confirmation for isolation | leak policy + G1 block |
| Verify effect and roll back | `actuation/controller.py::verify` |
| Fail-safe on comm loss/sensor fault | `ingest/service.py`, G2, sensor-fault diagnosis |
| Every action audited | `db/repository.py::insert_action`, `ActionAudit` schema |

## 5. Alarm philosophy (ISA-18.2 alignment)

- Priorities: advisory, warning, critical. Leak is always critical.
- Lifecycle: ACTIVE → ACKED → CLEARED → CLOSED; SHELVED (timed) and SUPPRESSED.
- Escalation timers re-notify unacknowledged alarms; notification adapters are
  pluggable (dashboard WebSocket, email, SMS/webhook).
- Alarm state is exposed to SCADA via the optional OPC UA alarm server and REST.

## 6. Cybersecurity (IEC 62443 alignment)

- **Zones:** field/edge zone, control zone (backend + broker + DB), DMZ/SCADA.
- **Identities:** per-device MQTT credentials + HMAC-SHA256 message signatures;
  JWT RBAC for dashboard/API (`viewer < operator < engineer < admin`).
- **Data:** TLS for MQTT and OPC UA; config-as-code with signed config pushes in
  production (prototype ships demo keys; replace before deployment).
- **Logging:** immutable audit table for actuation; application logs for alarms.
- **Hardening:** container images, no hardcoded production secrets, deny-by-default
  actuation targets. Demo credentials are explicitly non-production.

## 7. Asset-integrity context (API 570 / ASME B31.4)

- API 570 (in-service inspection) and ASME B31.4 (liquid hydrocarbon piping)
  provide the maintenance/inspection context. PipeGuard supports—does not
  replace—periodic inspection, corrosion monitoring and engineering assessment.
- Thresholds, natural frequencies and skip bands must be commissioned per
  segment and recorded in `backend/config/*.yaml` with change control.
- Diagnosis output is evidence + confidence, not a certified fitness-for-service
  determination.

## 8. Limitations and residual risk

- The simulator is deterministic and simpler than real rotating machinery.
- IsolationForest/autoencoder scores are advisory; ML drift and retraining are
  not production-hardened.
- The Goertzel-based firmware spectrum is a prototype; ESP32 deployment should
  use a validated FFT library and calibrated sensors.
- HMAC demo keys and JWT demo secret are not production credentials.
- PDF report generation is optional (reportlab).
- No formal verification of the safety gate; recommended before field trial.

## 9. Conclusion

For the stated prototype scope, the controls above prevent automatic commands
from exceeding configured limits, touching SIS/ESD, or acting on invalid data,
and require rollback/escalation when the effect is not verified. Deployment to
a live pipeline requires site-specific safety engineering, independent review
and regulatory compliance work.
