FROM python:3.12-slim
WORKDIR /app
COPY plc_sim/pyproject.toml ./pyproject.toml
COPY plc_sim/src ./src
ENV PIP_DEFAULT_TIMEOUT=120 PIP_RETRIES=10
RUN pip install --no-cache-dir -e '.[opcua]'
EXPOSE 4840 5020
ENTRYPOINT ["python", "-m", "plc_sim.cli"]
