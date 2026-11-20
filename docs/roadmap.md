# PipeGuard Roadmap

## Delivered (prototype)

- [x] Architecture and topic/schema contract
- [x] Deterministic multi-fault simulator (Python) and signed messages
- [x] Edge firmware core in Rust (`no_std`-friendly, SensorTrait/simulator/DSP/HMAC)
- [x] HMAC ingestion with dedupe, lateness/drift handling and baseline learning
- [x] Four detection layers + debounce/hysteresis
- [x] Evidence-based diagnosis with confusion-matrix evaluation utility
- [x] YAML policies, hard safety gates, kill switch, per-segment AUTO opt-in
- [x] OPC UA / Modbus PLC simulator and interchangeable device adapters
- [x] Bounded actuation with verification, rollback and escalation
- [x] Alarm lifecycle, RBAC notifications, incident reports
- [x] React control-room dashboard with WebSocket push
- [x] Docker Compose stack, TimescaleDB schema, Makefile, end-to-end demo

## Near term (production hardening)

- [ ] Replace demo secrets: TLS everywhere, per-device certs, signed config pushes
- [ ] Real accelerometer drivers (ADXL355/MPU6050) and validated ESP32 FFT (`esp-dsp`)
- [ ] Production ML lifecycle: drift detection, retraining, model registry, versioning
- [ ] Formal verification / independent review of the safety gate logic
- [ ] TimescaleDB retention/compression tuning and high-availability deployment
- [ ] Full ISA-18.2 alarm rationalization and performance metrics
- [ ] Site-specific commissioning: vibration limits, natural frequencies, skip bands

## Longer term

- [ ] Distributed fiber-optic/acoustic sensing integration
- [ ] Digital twin / asset model with corrosion and wall-thickness context
- [ ] Predictive maintenance scheduling and remaining-useful-life estimation
- [ ] Federated learning across sites with privacy-preserving model updates
- [ ] Certified hardware target (ATEX/IECEx Zone 2) and functional-safety assessment
- [ ] Multi-site control room, SSO integration and SCADA historian bridge
