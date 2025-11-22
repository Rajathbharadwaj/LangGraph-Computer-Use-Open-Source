FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Cloud Run sets PORT environment variable
ENV PORT=8080
ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s \
  CMD curl -f http://localhost:${PORT}/ || exit 1

# Run with Uvicorn
CMD uvicorn backend_websocket_server:app \
    --host 0.0.0.0 \
    --port ${PORT} \
    --workers 4 \
    --timeout-keep-alive 300 \
    --ws-ping-interval 20 \
    --ws-ping-timeout 20
