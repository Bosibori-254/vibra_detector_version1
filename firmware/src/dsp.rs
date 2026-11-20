//! Allocation-light DSP primitives matching the Python reference implementation.

use alloc::vec::Vec;

/// Root-mean-square.
pub fn rms(samples: &[f32]) -> f32 {
    if samples.is_empty() { return 0.0; }
    let sum: f32 = samples.iter().map(|v| v * v).sum();
    libm::sqrtf(sum / samples.len() as f32)
}

/// Maximum absolute amplitude.
pub fn peak(samples: &[f32]) -> f32 {
    samples.iter().fold(0.0_f32, |m, v| m.max(v.abs()))
}

/// Peak-to-RMS ratio.
pub fn crest_factor(samples: &[f32]) -> f32 {
    let r = rms(samples);
    if r > 1e-6 { peak(samples) / r } else { 0.0 }
}

/// Excess kurtosis (normal distribution ≈ 0).
pub fn kurtosis(samples: &[f32]) -> f32 {
    if samples.is_empty() { return 0.0; }
    let mean = samples.iter().sum::<f32>() / samples.len() as f32;
    let m2 = samples.iter().map(|v| (v - mean) * (v - mean)).sum::<f32>() / samples.len() as f32;
    if m2 < 1e-9 { return 0.0; }
    let m4 = samples
        .iter()
        .map(|v| {
            let delta = v - mean;
            delta * delta * delta * delta
        })
        .sum::<f32>()
        / samples.len() as f32;
    m4 / (m2 * m2) - 3.0
}

/// Approximate band-limited velocity RMS in mm/s (accelerometer input in m/s²).
pub fn velocity_rms_mm_s(samples: &[f32], sample_rate: u32) -> f32 {
    if samples.len() < 4 { return 0.0; }
    let mut velocity = 0.0_f32;
    let mut sum = 0.0_f32;
    let mut sum_sq = 0.0_f32;
    let dt = 1.0 / sample_rate as f32;
    for value in samples {
        velocity += value * dt;
        sum += velocity;
        sum_sq += velocity * velocity;
    }
    let n = samples.len() as f32;
    let variance = (sum_sq / n - (sum / n) * (sum / n)).max(0.0);
    libm::sqrtf(variance) * 1000.0
}

/// Goertzel magnitude at one frequency.
pub fn goertzel(samples: &[f32], sample_rate: u32, frequency: f32) -> f32 {
    if samples.is_empty() || frequency <= 0.0 { return 0.0; }
    let w = 2.0 * core::f32::consts::PI * frequency / sample_rate as f32;
    let coeff = 2.0 * libm::cosf(w);
    let mut s1 = 0.0_f32;
    let mut s2 = 0.0_f32;
    for sample in samples {
        let s0 = *sample + coeff * s1 - s2;
        s2 = s1;
        s1 = s0;
    }
    libm::sqrtf((s1 * s1 + s2 * s2 - coeff * s1 * s2).max(0.0)) / samples.len() as f32
}

/// Relative spectral energy per band, returned as `(low, high, fraction)`.
pub fn band_energies(
    samples: &[f32],
    sample_rate: u32,
    bands: &[(f32, f32)],
) -> Vec<(f32, f32, f32)> {
    let mut energies = Vec::with_capacity(bands.len());
    let mut total = 0.0_f32;
    for &(low, high) in bands {
        let mut energy = 0.0_f32;
        for step in 0..4 {
            let freq = low + (high - low) * (step as f32 + 0.5) / 4.0;
            let magnitude = goertzel(samples, sample_rate, freq);
            energy += magnitude * magnitude;
        }
        energies.push((low, high, energy));
        total += energy;
    }
    if total > 1e-9 {
        for entry in &mut energies { entry.2 /= total; }
    }
    energies
}

/// Dominant spectral peaks found with a coarse Goertzel scan.
pub fn top_peaks(samples: &[f32], sample_rate: u32, top_n: usize) -> Vec<(f32, f32)> {
    let mut candidates = Vec::new();
    let mut frequency = 10.0_f32;
    let limit = sample_rate as f32 / 2.0;
    while frequency < limit {
        candidates.push((frequency, goertzel(samples, sample_rate, frequency)));
        frequency += 5.0;
    }
    candidates.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(core::cmp::Ordering::Equal));
    candidates.truncate(top_n);
    candidates
}

#[cfg(test)]
mod tests {
    use super::*;
    const PI: f32 = core::f32::consts::PI;

    fn sine() -> Vec<f32> {
        (0..1000).map(|i| (2.0 * PI * 50.0 * i as f32 / 2000.0).sin()).collect()
    }

    #[test]
    fn basic_statistics() {
        let values = sine();
        assert!((rms(&values) - 0.707).abs() < 0.01);
        assert!((peak(&values) - 1.0).abs() < 0.01);
        assert!((crest_factor(&values) - 1.414).abs() < 0.02);
        // A sinusoid has theoretical excess kurtosis of -1.5.
        assert!((kurtosis(&values) + 1.5).abs() < 0.1);
    }

    #[test]
    fn goertzel_finds_tone() {
        let values = sine();
        let at_50 = goertzel(&values, 2000, 50.0);
        let at_150 = goertzel(&values, 2000, 150.0);
        assert!(at_50 > at_150 * 10.0);
    }

    #[test]
    fn top_peaks_and_bands() {
        let values = sine();
        let peaks = top_peaks(&values, 2000, 3);
        assert!((peaks[0].0 - 50.0).abs() < 6.0);
        let bands = band_energies(&values, 2000, &[(10.0, 50.0), (50.0, 150.0), (150.0, 500.0)]);
        assert!(bands[1].2 > bands[2].2);
    }
}
