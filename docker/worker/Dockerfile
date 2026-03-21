FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[worker]"

COPY src/ src/

CMD ["python", "-m", "lightcron.worker.main"]
