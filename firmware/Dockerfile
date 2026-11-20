FROM rust:1-slim AS builder
WORKDIR /app
COPY Cargo.toml ./
COPY src ./src
RUN cargo test --release && cargo build --release

FROM debian:bookworm-slim
COPY --from=builder /app/target/release/pipeguard-firmware /usr/local/bin/pipeguard-firmware
ENTRYPOINT ["pipeguard-firmware"]
CMD ["normal", "10"]
