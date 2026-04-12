FROM python:3.11-slim

WORKDIR /app

# Copy requirements first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY src/ ./src/

# Default environment variables
ENV MODE=cpu
ENV LOAD_INTENSITY=50
ENV MEMORY_LIMIT_MB=64
ENV PROCESSING_DELAY_MS=100
ENV SERVER_PORT=8080
ENV METRICS_PORT=8000
ENV RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672
ENV RABBITMQ_QUEUE=task-queue
ENV RABBITMQ_ROLE=consumer

# Expose HTTP server port
EXPOSE 8080

# Health check using HTTP endpoint
HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

CMD ["python", "src/main.py"]
