# PipeGuard Dashboard

React + TypeScript + Vite control-room UI with WebSocket push, Recharts waveform
and spectrum views, alarm list, action log, device health, role-based manual
control and kill switch.

## Run

```bash
npm install
npm run dev      # http://localhost:5173, proxies /api and /ws to backend:8000
npm run build
npm run lint
```

Demo users (matching passwords): `viewer`, `operator`, `engineer`, `admin`.
Manual control requires `engineer+`; kill switch requires `admin`.
