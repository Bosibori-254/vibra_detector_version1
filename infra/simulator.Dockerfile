FROM python:3.12-slim
WORKDIR /app
COPY simulator/pyproject.toml ./pyproject.toml
COPY simulator ./src
RUN pip install --no-cache-dir -e '.[mqtt]'
ENTRYPOINT ["python", "-m", "pipeguard_sim.cli"]
CMD ["--scenario", "normal", "--duration", "30"]
