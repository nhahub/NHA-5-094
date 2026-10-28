FROM python:3.11-slim

WORKDIR /app

# Production containers use a fixed unprivileged identity. The storage directory
# is owned by that identity so a fresh named volume can be initialized safely.
RUN groupadd --system --gid 10001 verifia \
    && useradd --system --uid 10001 --gid verifia --home-dir /app \
        --no-create-home --shell /usr/sbin/nologin verifia \
    && install -d --owner=10001 --group=10001 --mode=0750 /app/data/storage

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    tesseract-ocr \
    tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY --chown=10001:10001 requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY --chown=10001:10001 . .

# Reassert ownership after the source copy and drop root before serving traffic.
RUN install -d --owner=10001 --group=10001 --mode=0750 /app/data/storage
USER 10001:10001

# Expose API port
EXPOSE 8000

# Run FastAPI app with Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
