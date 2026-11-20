//! Fixed-capacity ring buffer for triggered raw-sample buffering.

use alloc::vec::Vec;

/// Overwriting ring buffer.
pub struct RingBuffer<T: Clone + Default> {
    data: Vec<T>,
    head: usize,
    len: usize,
}

impl<T: Clone + Default> RingBuffer<T> {
    /// Create a buffer with fixed capacity.
    pub fn new(capacity: usize) -> Self {
        let mut data = Vec::with_capacity(capacity.max(1));
        data.resize_with(capacity.max(1), T::default);
        Self { data, head: 0, len: 0 }
    }

    /// Push a value, overwriting the oldest entry when full.
    pub fn push(&mut self, value: T) {
        self.data[self.head] = value;
        self.head = (self.head + 1) % self.data.len();
        self.len = (self.len + 1).min(self.data.len());
    }

    /// Number of stored values.
    pub fn len(&self) -> usize { self.len }

    /// Whether the buffer is empty.
    pub fn is_empty(&self) -> bool { self.len == 0 }

    /// Return the stored values oldest-first.
    pub fn as_vec(&self) -> Vec<T> {
        let mut result = Vec::with_capacity(self.len);
        let start = (self.head + self.data.len() - self.len) % self.data.len();
        for index in 0..self.len {
            result.push(self.data[(start + index) % self.data.len()].clone());
        }
        result
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn overwrites_oldest() {
        let mut buffer = RingBuffer::<u32>::new(3);
        for value in 1..=5 { buffer.push(value); }
        assert_eq!(buffer.as_vec(), alloc::vec![3, 4, 5]);
        assert_eq!(buffer.len(), 3);
    }

    #[test]
    fn empty_buffer() {
        let buffer = RingBuffer::<f32>::new(4);
        assert!(buffer.is_empty());
    }
}
