#![cfg_attr(not(feature = "std"), no_std)]
//! PipeGuard edge node core: sensor abstraction, DSP, buffering and publishing.
//!
//! The crate avoids `std` in its core modules so the same code can be built for
//! ESP32 (`no_std`) and for the host (tests and the software simulator).

extern crate alloc;

pub mod buffer;
#[cfg(feature = "mqtt")]
pub mod mqtt;
pub mod sensor;
pub mod simulator;
pub mod dsp;
pub mod features;

use alloc::string::String;

/// A generic publisher used by the edge pipeline (host log or MQTT).
pub trait Publisher {
    /// Publish a payload on a topic.
    fn publish(&mut self, topic: &str, payload: &str) -> Result<(), String>;
}

/// A publisher that simply logs payloads; used by host tests and demos.
#[derive(Default)]
pub struct LogPublisher;

impl Publisher for LogPublisher {
    fn publish(&mut self, topic: &str, payload: &str) -> Result<(), String> {
        #[cfg(feature = "std")]
        println!("PUBLISH {topic}: {payload}");
        #[cfg(not(feature = "std"))]
        let _ = (topic, payload);
        Ok(())
    }
}
