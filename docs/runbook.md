# PipeGuard Operations Runbook

## 1. Roles and authority

| Role | Permissions |
|---|---|
| viewer | Read overview, alarms, actions, incidents, health |
| operator | Acknowledge/shelve/clear alarms; generate incident reports |
| engineer | Operator + bounded manual setpoint changes; AUTO policy changes via config-as-code |
| admin | Engineer + global kill switch; user/credential administration |

Demo credentials are `viewer`/`operator`/`engineer`/`admin` with the same password.
Replace them before any non-demo deployment.

## 2. Normal operations

1. Confirm `make up` completed and all containers are healthy.
2. Open the dashboard at <http://localhost:5173> and sign in.
3. Check **Pipeline map** (all segments green), **Device health**, and **Alarm list**.
4. Confirm the backend is ingesting telemetry:
   - `curl -H "Authorization: Bearer <token>" localhost:8000/api/overview`
5. Leave `ADVISORY` as the normal mode. AUTO is only enabled explicitly, per segment
   and per cause, in `backend/config/policies.yaml` plus `system.auto_segments`
   in `backend/config/default.yaml`, with change control.

## 3. Responding to an alarm

1. Read the alarm priority, segment/cause and evidence in the dashboard and
   `/api/actions` audit log.
2. Acknowledge (operator+) once the condition is understood. Shelving is temporary
   (default 300 s) and must be justified in the shift log.
3. Review the recommended action. For leak/critical alarms: **do not** rely on
   automation — escalate to the control room and follow site isolation procedures.
4. If an automatic action executed, confirm the verification outcome:
   - `verified`: vibration improved; alarm should clear.
   - `rolled_back`: no improvement, setpoint restored, escalation raised.
   - `failed`: communication/device failure; operator intervention required.
5. Generate an incident report from `/api/incidents/generate` or the dashboard
   after the event. Reports are stored in `docs/reports/incidents/`.

## 4. Kill switch

- **Engage** `/api/kill-switch` (`admin`) or the dashboard button when:
  - any unexpected actuator behaviour occurs,
  - sensor health is uncertain,
  - maintenance is in progress,
  - process conditions leave the configured operating envelope.
- Engagement blocks all automation immediately (G0) but does not clear alarms.
- Releasing the switch does not re-enable AUTO by itself; AUTO is a separate,
  explicit per-segment configuration choice.

## 5. Fail-safe behaviour

PipeGuard issues **no** command when any of these is true (see `rules/safety.py`):
- global or segment automation kill switch active;
- mode is ADVISORY or segment AUTO is not explicitly enabled;
- cause is leak or action requires human confirmation;
- telemetry older than `system.max_message_age_s`, duplicate, out-of-order or
  from an unhealthy sensor;
- process variable outside `operating_envelope`;
- target setpoint outside hard min/max or in the SIS/ESD deny-list;
- step/rate/cooldown limits exceeded;
- operator not authorized.

## 6. Fault diagnosis reference

| Cause | Typical evidence | Response |
|---|---|---|
| cavitation | high-band energy, low suction pressure, high speed | bounded VFD speed reduction (AUTO opt-in) |
| resonance | narrow peak at natural frequency | shift speed past skip band; engineering review |
| water hammer | transient impulse, high valve close rate | increase close time; check surge relief |
| loose support | impact bursts, high crest factor | maintenance work order |
| leak | broadband change, pressure drop | critical alarm, human isolation only |
| imbalance | 1×/2× running speed peaks | maintenance work order |
| sensor fault | drift/flatline/implausible steps | suppress actuation, repair sensor |

## 7. Troubleshooting

| Symptom | Check | Action |
|---|---|---|
| No telemetry | Mosquitto credentials, LWT status, node clock skew | restart node/simulator; verify signatures |
| Backend unhealthy | `docker compose logs backend`, DB URL/connection | restart backend; check TimescaleDB |
| Dashboard shows stale data | WebSocket connection, `/api/health` | reload page; check proxy config |
| Repeated rollback | vibration signal not responding to setpoint | disable AUTO; engineering assessment |
| High alarm chatter | debounce/hysteresis config, sensor mounting | tune config with change control |

## 8. Configuration changes

- All thresholds and policies live in `backend/config/default.yaml` and
  `policies.yaml`. Never edit code to change a limit.
- Use version control, peer review, and documented commissioning evidence.
- After changes: `make test && make lint`, restart backend, verify on the demo
  scenario (`make demo`) before returning to service.

## 9. Shutdown

`make down` removes containers and volumes (including the demo database). Use a
managed backup/restore procedure for any non-demo data.
