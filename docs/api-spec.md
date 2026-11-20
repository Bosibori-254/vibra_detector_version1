# PipeGuard API Specification

Base URL: `http://localhost:8000`. Interactive OpenAPI docs: `/docs`.
All `/api/*` endpoints except `POST /api/auth/token` require
`Authorization: Bearer <JWT>` (demo login returns a token).
WebSocket alerts: `ws://localhost:8000/ws/alerts`.

## Authentication

### POST /api/auth/token
Body: `{ "username": "operator", "password": "operator" }` →
`{ "access_token": "...", "token_type": "bearer" }`.
Demo roles: viewer, operator, engineer, admin (password equals username).

## Observability

### GET /api/health
Returns `{"status":"ok","service":"pipeguard-backend"}`. Requires viewer.

### GET /api/overview
Returns site, segment statuses/node IDs, device adapter snapshots and the
kill-switch state. Requires viewer.

## Alarms

### GET /api/alarms
List alarms with fields: `alarm_id`, `node_id`, `segment`, `site`, `priority`
(advisory/warning/critical), `state` (ACTIVE/ACKED/SHELVED/CLEARED), `cause`,
`message`, `created_at`, `updated_at`, `acked_by`, `escalation_count`.

### POST /api/alarms/{alarm_id}/ack
Body `{ "operator": "operator" }` → updated alarm. Requires operator.

### POST /api/alarms/{alarm_id}/shelve
Body `{ "seconds": 300 }` → updated alarm. Requires operator.

### POST /api/alarms/{alarm_id}/clear
→ updated alarm. Requires operator.

## Actions and incidents

### GET /api/actions
List immutable action audit records: `action_id`, `timestamp`, `node_id`,
`segment`, `cause`, `mode`, `action_type`, `target`, `before`, `after`, `result`
(recommended/executed/verified/rolled_back/failed), `reason`, `gate_results`,
`operator`, `rollback_of`.

### GET /api/incidents · GET /api/incidents/{incident_id}
List/read generated incident reports (timeline, diagnoses, actions, alarms,
spectrum snapshot, outcome).

### POST /api/incidents/generate
Query params: `cause` (enum), `severity` (default warning), `site`, `segment`.
Generates Markdown/JSON/PDF report in `docs/reports/incidents/`. Requires operator.

## Telemetry and control

### POST /api/ingest
Body: signed feature message JSON. Runs it through the full pipeline
(ingest → detect → diagnose → decide → act → alarm) and returns the result
envelope. Requires viewer (used by the demo and tests).

### POST /api/manual-control
Body `{ "target": "vfd_speed_rpm", "value": 2800, "reason": "..." }` → audit
record. Requires engineer. Hard bounds, max-step, deny-list and audit apply.

### POST /api/kill-switch
Body `{ "active": true }` → `{"kill_switch": true, "at": <epoch>}`.
Requires admin. Blocks all automation immediately.

## WebSocket events

Streamed JSON envelopes `{"type": "alarm"|"action"|"diagnosis"|"telemetry", ...}`
with `verb` and full `alarm`/`audit` payloads where applicable.

## MQTT topic schema

`pipeguard/{site}/{segment}/{node}/{features|raw|status|cmd/#}`.
QoS 1, retained status, per-device credentials, HMAC-SHA256 over canonical JSON
(without the `signature` field). `cmd` topics are reserved for future signed
configuration pushes; actuation is currently backend → OPC UA/Modbus only.
