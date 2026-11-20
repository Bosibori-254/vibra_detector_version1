//! MQTT/TLS publisher for the host build (`--features mqtt`).

use rumqttc::{Client, EventLoop, MqttOptions, QoS};

use crate::Publisher;

/// MQTT publisher backed by `rumqttc`.
pub struct MqttPublisher {
    /// Client used to enqueue publishes.
    pub client: Client,
    /// Event loop that must be polled to drive I/O.
    pub eventloop: EventLoop,
}

impl MqttPublisher {
    /// Connect to a broker with optional username/password.
    pub fn new(
        client_id: &str,
        host: &str,
        port: u16,
        credentials: Option<(&str, &str)>,
    ) -> Self {
        let mut options = MqttOptions::new(client_id, host, port);
        options.set_keep_alive(std::time::Duration::from_secs(30));
        if let Some((username, password)) = credentials {
            options.set_credentials(username, password);
        }
        let (client, eventloop) = Client::new(options, 10);
        Self { client, eventloop }
    }

    /// Drive one iteration of the MQTT event loop.
    pub fn poll(&mut self) -> Result<(), String> {
        self.eventloop.poll().map(|_| ()).map_err(|e| e.to_string())
    }
}

impl Publisher for MqttPublisher {
    fn publish(&mut self, topic: &str, payload: &str) -> Result<(), String> {
        self.client
            .publish(topic, QoS::AtLeastOnce, false, payload.as_bytes())
            .map_err(|e| e.to_string())
    }
}
