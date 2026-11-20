//! Deterministic software sensor implementing [`SensorTrait`].

use crate::sensor::{SensorError, SensorFrame, SensorTrait};

const PI: f32 = core::f32::consts::PI;

/// Fault classes matching the Python simulator.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Fault {
    Normal,
    Cavitation,
    Resonance,
    WaterHammer,
    LooseSupport,
    Leak,
    Imbalance,
    SensorFault,
}

/// Simple polynomial sine so the core stays `libm`-free.
pub fn sin_approx(value: f32) -> f32 {
    let period = 2.0 * PI;
    let mut x = value % period;
    if x > PI { x -= period; }
    if x < -PI { x += period; }
    let x2 = x * x;
    x * (1.0 - x2 / 6.0 + x2 * x2 / 120.0 - x2 * x2 * x2 / 5040.0)
}

/// A deterministic sensor simulator (xorshift PRNG).
pub struct SimulatedSensor {
    sample_rate: u32,
    t_us: u64,
    rng: u32,
    fault: Fault,
    severity: f32,
    natural_hz: f32,
    healthy: bool,
}

impl SimulatedSensor {
    /// Create a sensor at `sample_rate` with an optional injected fault.
    pub fn new(sample_rate: u32, fault: Fault, severity: f32, seed: u32) -> Self {
        Self {
            sample_rate,
            t_us: 0,
            rng: seed | 1,
            fault,
            severity,
            natural_hz: 187.0,
            healthy: fault != Fault::SensorFault,
        }
    }

    fn uniform(&mut self) -> f32 {
        self.rng ^= self.rng << 13;
        self.rng ^= self.rng >> 17;
        self.rng ^= self.rng << 5;
        (self.rng as f32 / u32::MAX as f32) * 2.0 - 1.0
    }
}

impl SensorTrait for SimulatedSensor {
    fn read(&mut self) -> Result<SensorFrame, SensorError> {
        if !self.healthy {
            return Err(SensorError::Drift);
        }
        self.t_us += 1_000_000 / self.sample_rate as u64;
        let t = self.t_us as f32 / 1_000_000.0;
        let run = 49.17f32; // 2950 rpm / 60
        let phase = sin_approx(2.0 * PI * run * t);
        let mut x = 0.26 * phase + 0.32 * self.uniform();
        let mut y = 0.15 * phase + 0.32 * self.uniform();
        let mut z = 0.48 * phase + 0.21 * sin_approx(4.0 * PI * run * t) + 0.32 * self.uniform();

        match self.fault {
            Fault::Normal => {}
            Fault::Cavitation => {
                let high = self.uniform() * sin_approx(2.0 * PI * 900.0 * t);
                z += 1.5 * self.severity * high;
                x += 0.5 * self.severity * high;
            }
            Fault::Resonance => {
                z += 1.8 * self.severity * sin_approx(2.0 * PI * self.natural_hz * t);
            }
            Fault::WaterHammer => {
                let event = 0.45;
                if t >= event {
                    let since = t - event;
                    let decay = 1.0 / (1.0 + 14.0 * since);
                    z += 4.0 * self.severity * decay * sin_approx(2.0 * PI * 32.0 * since);
                }
            }
            Fault::LooseSupport => {
                let phase_time = t % 0.11;
                if phase_time < 0.01 {
                    z += 3.2 * self.severity * sin_approx(2.0 * PI * 27.0 * phase_time);
                }
            }
            Fault::Leak => z += 1.1 * self.severity * self.uniform(),
            Fault::Imbalance => {
                z += 2.0 * self.severity * phase
                    + 1.1 * self.severity * sin_approx(4.0 * PI * run * t);
            }
            Fault::SensorFault => return Err(SensorError::Bus),
        }
        Ok(SensorFrame { t_us: self.t_us, x, y, z })
    }

    fn sample_rate_hz(&self) -> u32 { self.sample_rate }

    fn health(&self) -> (bool, f32) {
        (self.healthy, if self.healthy { 3.1 } else { 50.0 })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn deterministic_stream() {
        let mut a = SimulatedSensor::new(2000, Fault::Normal, 0.0, 42);
        let mut b = SimulatedSensor::new(2000, Fault::Normal, 0.0, 42);
        for _ in 0..10 { assert_eq!(a.read().unwrap(), b.read().unwrap()); }
    }

    #[test]
    fn fault_changes_signal() {
        let mut normal = SimulatedSensor::new(2000, Fault::Normal, 0.0, 7);
        let mut faulty = SimulatedSensor::new(2000, Fault::Cavitation, 0.9, 7);
        let mut different = false;
        for _ in 0..20 {
            if (normal.read().unwrap().z - faulty.read().unwrap().z).abs() > 0.1 {
                different = true;
            }
        }
        assert!(different);
    }

    #[test]
    fn sensor_fault_reports_error() {
        let mut sensor = SimulatedSensor::new(2000, Fault::SensorFault, 1.0, 1);
        assert_eq!(sensor.read().unwrap_err(), SensorError::Drift);
    }
}
