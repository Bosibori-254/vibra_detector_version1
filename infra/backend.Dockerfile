FROM python:3.12-slim
WORKDIR /app
COPY backend/pyproject.toml ./backend/pyproject.toml
COPY simulator/pyproject.toml ./simulator/pyproject.toml
COPY plc_sim/pyproject.toml ./plc_sim/pyproject.toml
COPY backend ./backend
COPY simulator ./simulator
COPY plc_sim ./plc_sim
ENV PIP_DEFAULT_TIMEOUT=120 PIP_RETRIES=10
RUN pip install --no-cache-dir -e ./backend[opcua] -e ./simulator -e ./plc_sim[opcua]
EXPOSE 8000
CMD ["python", "-m", "pipeguard_backend.main", "--host", "0.0.0.0", "--port", "8000"]
