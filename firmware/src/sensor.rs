/// One 3-axis accelerometer frame.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct SensorFrame {
    /// Timestamp in microseconds since node boot.
    pub t_us: u64,
    /// Acceleration X in m/s².
    pub x: f32,
    /// Acceleration Y in m/s².
    pub y: f32,
    /// Acceleration Z in m/s².
    pub z: f32,
}

/// Sensor failure modes reported through node health.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SensorError {
    /// I²C/SPI bus failure.
    Bus,
    /// Sampling deadline missed.
    Timeout,
    /// Excessive calibration drift.
    Drift,
}

/// Hardware and simulator sensors are interchangeable behind this trait.
pub trait SensorTrait {
    /// Read one frame.
    fn read(&mut self) -> Result<SensorFrame, SensorError>;
    /// Configured sample rate.
    fn sample_rate_hz(&self) -> u32;
    /// Whether sampling is healthy and the estimated drift in ppm.
    fn health(&self) -> (bool, f32);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn frame_holds_axes() {
        let frame = SensorFrame { t_us: 1, x: 0.1, y: 0.2, z: 0.3 };
        assert_eq!(frame.z, 0.3);
    }
}
