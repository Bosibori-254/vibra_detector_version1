# PipeGuard Edge Firmware (Rust)

Host-testable, `no_std`-friendly edge core. Real ADXL355/MPU6050 drivers and the
software sensor implement the same `SensorTrait`, so they are interchangeable.

```bash
cargo test                    # host unit tests
cargo run -- cavitation 20    # print 20 signed feature messages
cargo run --features mqtt -- cavitation 20   # publish to localhost:1883
docker build -t pipeguard-firmware . && docker run --rm pipeguard-firmware
```

Modules: `sensor` (trait), `simulator` (deterministic fault sensor), `dsp`
(RMS, crest, kurtosis, band energies, Goertzel peaks), `features` (wire schema
and HMAC signing), `buffer` (raw ring buffer), `mqtt` (optional publisher).

For ESP32 deployment, replace `SimulatedSensor` with an embedded-hal I²C/SPI
driver and a timer-driven sampler; keep the DSP and feature modules unchanged.
Production FFT should use `esp-dsp`/CMSIS-DSP; the Goertzel scan here keeps the
prototype dependency-light while preserving the same feature semantics.
