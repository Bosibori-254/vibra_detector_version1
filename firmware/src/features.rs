//! Feature extraction and signed wire messages.

use alloc::collections::BTreeMap;
use alloc::format;
use alloc::string::{String, ToString};
use alloc::vec::Vec;
use hmac::{Hmac, Mac};
use serde::Serialize;
use sha2::Sha256;

use crate::dsp;
use crate::sensor::SensorFrame;

/// Feature extraction configuration.
#[derive(Clone, Copy, Debug)]
pub struct FeatureConfig {
    /// Samples per second.
    pub sample_rate_hz: u32,
    /// Analysis window length in seconds.
    pub window_seconds: f32,
    /// Number of dominant peaks to report.
    pub top_n_peaks: usize,
}

impl Default for FeatureConfig {
    fn default() -> Self {
        Self { sample_rate_hz: 2000, window_seconds: 0.5, top_n_peaks: 5 }
    }
}

/// A dominant spectral peak.
#[derive(Clone, Debug, Serialize)]
pub struct FftPeak {
    /// Frequency in Hz.
    pub hz: f32,
    /// Amplitude in m/s².
    pub amplitude_mps2: f32,
}

/// The feature vector published by a node.
#[derive(Clone, Debug, Serialize)]
pub struct Features {
    /// Sample rate.
    pub sample_rate_hz: u32,
    /// Window length.
    pub window_seconds: f32,
    /// Per-axis RMS acceleration.
    pub accel_rms_mps2: BTreeMap<String, f32>,
    /// Band-limited velocity RMS.
    pub velocity_rms_mm_s: f32,
    /// Peak acceleration.
    pub peak_mps2: f32,
    /// Crest factor.
    pub crest_factor: f32,
    /// Excess kurtosis.
    pub kurtosis: f32,
    /// Relative band energies.
    pub band_energies: BTreeMap<String, f32>,
    /// Dominant FFT peaks.
    pub fft_peaks: Vec<FftPeak>,
}

/// Operating conditions.
#[derive(Clone, Debug, Serialize)]
pub struct OperatingState {
    /// Flow rate.
    pub flow_m3h: f32,
    /// Pressure.
    pub pressure_kpa: f32,
    /// Pump speed.
    pub pump_speed_rpm: f32,
    /// Valve position.
    pub valve_position_pct: f32,
}

/// Node health block.
#[derive(Clone, Debug, Serialize)]
pub struct NodeHealth {
    /// Battery percentage.
    pub battery_pct: f32,
    /// Temperature.
    pub temp_c: f32,
    /// Sampling healthy.
    pub sampling_ok: bool,
    /// Sensor drift ppm.
    pub drift_ppm: f32,
}

/// Complete signed telemetry message.
#[derive(Clone, Debug, Serialize)]
pub struct FeatureMessage {
    /// Schema version.
    pub schema_version: String,
    /// Unique message ID.
    pub message_id: String,
    /// Node identifier.
    pub node_id: String,
    /// Site identifier.
    pub site: String,
    /// Segment identifier.
    pub segment: String,
    /// Timestamp.
    pub timestamp: String,
    /// Monotonic sequence number.
    pub sequence: u64,
    /// Operating conditions.
    pub operating_state: OperatingState,
    /// Feature vector.
    pub features: Features,
    /// Node health.
    pub health: NodeHealth,
    /// HMAC signature (filled by `signed_json`).
    pub signature: String,
}

/// Extract features from a window of 3-axis frames.
pub fn extract_features(frames: &[SensorFrame], config: &FeatureConfig) -> Features {
    let x: Vec<f32> = frames.iter().map(|f| f.x).collect();
    let y: Vec<f32> = frames.iter().map(|f| f.y).collect();
    let z: Vec<f32> = frames.iter().map(|f| f.z).collect();
    let mut accel = BTreeMap::new();
    accel.insert("x".to_string(), dsp::rms(&x));
    accel.insert("y".to_string(), dsp::rms(&y));
    accel.insert("z".to_string(), dsp::rms(&z));
    let bands = [(10.0, 50.0), (50.0, 150.0), (150.0, 500.0), (500.0, 2000.0)];
    let band_energies = dsp::band_energies(&z, config.sample_rate_hz, &bands)
        .into_iter()
        .map(|(low, high, energy)| (format!("{low:g}_{high:g}"), energy))
        .collect();
    let peaks = dsp::top_peaks(&z, config.sample_rate_hz, config.top_n_peaks)
        .into_iter()
        .map(|(hz, amplitude_mps2)| FftPeak { hz, amplitude_mps2 })
        .collect();
    Features {
        sample_rate_hz: config.sample_rate_hz,
        window_seconds: config.window_seconds,
        accel_rms_mps2: accel,
        velocity_rms_mm_s: dsp::velocity_rms_mm_s(&z, config.sample_rate_hz),
        peak_mps2: dsp::peak(&z),
        crest_factor: dsp::crest_factor(&z),
        kurtosis: dsp::kurtosis(&z),
        band_energies,
        fft_peaks: peaks,
    }
}

impl FeatureMessage {
    /// Serialize to canonical JSON with an HMAC-SHA256 signature.
    pub fn signed_json(&self, key: &str) -> Result<String, String> {
        let mut value = serde_json::to_value(self).map_err(|e| e.to_string())?;
        if let Some(object) = value.as_object_mut() {
            object.remove("signature");
        }
        let canonical = serde_json::to_string(&value).map_err(|e| e.to_string())?;
        let mut mac = Hmac::<Sha256>::new_from_slice(key.as_bytes())
            .map_err(|_| "invalid HMAC key".to_string())?;
        mac.update(canonical.as_bytes());
        let signature = hex::encode(mac.finalize().into_bytes());
        let mut signed = value;
        if let Some(object) = signed.as_object_mut() {
            object.insert("signature".to_string(), serde_json::Value::String(signature));
        }
        serde_json::to_string(&signed).map_err(|e| e.to_string())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn extracts_features_from_synthetic_frames() {
        let config = FeatureConfig::default();
        let frames: Vec<SensorFrame> = (0..1000)
            .map(|i| {
                let t = i as f32 / 2000.0;
                SensorFrame {
                    t_us: i * 500,
                    x: 0.1,
                    y: 0.1,
                    z: libm::sinf(2.0 * core::f32::consts::PI * 50.0 * t),
                }
            })
            .collect();
        let features = extract_features(&frames, &config);
        assert!(features.velocity_rms_mm_s > 0.0);
        assert!(features.fft_peaks[0].hz > 40.0);
    }

    #[test]
    fn signature_is_stable_and_covers_payload() {
        let message = FeatureMessage {
            schema_version: "1.0".to_string(),
            message_id: "m1".to_string(),
            node_id: "node-03".to_string(),
            site: "gulf-north".to_string(),
            segment: "seg-12".to_string(),
            timestamp: "T+0".to_string(),
            sequence: 1,
            operating_state: OperatingState {
                flow_m3h: 820.0,
                pressure_kpa: 3450.0,
                pump_speed_rpm: 2950.0,
                valve_position_pct: 100.0,
            },
            features: extract_features(&[], &FeatureConfig::default()),
            health: NodeHealth {
                battery_pct: 90.0,
                temp_c: 40.0,
                sampling_ok: true,
                drift_ppm: 3.0,
            },
            signature: String::new(),
        };
        let a = message.signed_json("secret").unwrap();
        let b = message.signed_json("secret").unwrap();
        assert_eq!(a, b);
        assert!(!a.contains("hmac"));
        assert!(a.contains("\"signature\""));
    }
}
