//! Host-runnable edge node: generates windows and publishes signed features.

use std::env;

use pipeguard_firmware::features::{extract_features, FeatureConfig, FeatureMessage, NodeHealth, OperatingState};
use pipeguard_firmware::sensor::SensorTrait;
use pipeguard_firmware::simulator::{Fault, SimulatedSensor};
use pipeguard_firmware::{LogPublisher, Publisher};

#[cfg(feature = "mqtt")]
use pipeguard_firmware::mqtt::MqttPublisher;

fn fault_from(name: &str) -> Fault {
    match name {
        "cavitation" => Fault::Cavitation,
        "resonance" => Fault::Resonance,
        "water_hammer" => Fault::WaterHammer,
        "loose_support" => Fault::LooseSupport,
        "leak" => Fault::Leak,
        "imbalance" => Fault::Imbalance,
        "sensor_fault" => Fault::SensorFault,
        _ => Fault::Normal,
    }
}

fn main() -> Result<(), String> {
    let args: Vec<String> = env::args().collect();
    let fault_name = args.get(1).map(String::as_str).unwrap_or("normal");
    let windows: usize = args.get(2).and_then(|v| v.parse().ok()).unwrap_or(10);
    let key = args.get(3).map(String::as_str).unwrap_or("device-secret");
    let mut sensor = SimulatedSensor::new(2000, fault_from(fault_name), 0.8, 42);
    let config = FeatureConfig::default();
    let samples_per_window = (config.sample_rate_hz as f32 * config.window_seconds) as usize;

    #[cfg(feature = "mqtt")]
    let mut publisher: Box<dyn Publisher> = Box::new(MqttPublisher::new(
        "pipeguard-node-03", "localhost", 1883, Some(("node-03", key)),
    ));
    #[cfg(not(feature = "mqtt"))]
    let mut publisher: Box<dyn Publisher> = Box::new(LogPublisher);

    for window in 0..windows {
        let mut frames = Vec::with_capacity(samples_per_window);
        for _ in 0..samples_per_window {
            if let Ok(frame) = sensor.read() { frames.push(frame); }
        }
        let (sampling_ok, drift_ppm) = sensor.health();
        let features = extract_features(&frames, &config);
        let message = FeatureMessage {
            schema_version: "1.0".to_string(),
            message_id: format!("node-03-{window}"),
            node_id: "node-03".to_string(),
            site: "gulf-north".to_string(),
            segment: "seg-12".to_string(),
            timestamp: format!("T+{:.3}s", window as f32 * config.window_seconds),
            sequence: window as u64,
            operating_state: OperatingState {
                flow_m3h: 820.0,
                pressure_kpa: if fault_name == "cavitation" { 2950.0 } else { 3450.0 },
                pump_speed_rpm: 2950.0,
                valve_position_pct: 100.0,
            },
            features,
            health: NodeHealth {
                battery_pct: 87.2,
                temp_c: 41.5,
                sampling_ok,
                drift_ppm,
            },
            signature: String::new(),
        };
        let payload = message.signed_json(key)?;
        publisher.publish("pipeguard/gulf-north/seg-12/node-03/features", &payload)?;
        #[cfg(feature = "mqtt")]
        publisher.poll()?;
    }
    Ok(())
}
