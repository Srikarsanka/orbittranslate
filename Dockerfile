# Use standard Python 3.10 on Debian Bullseye (has GLIBCXX 3.4.29 — fine for faster-whisper)
FROM python:3.10-slim

# Install system deps: ffmpeg (audio extraction), curl (healthcheck/debug)
RUN apt-get update && apt-get install -y \
      ffmpeg \
      curl \
      && rm -rf /var/lib/apt/lists/*

# Create working directory
WORKDIR /app

# Copy requirements first for better Docker layer caching
COPY requirements.txt .

# Upgrade pip and install Python dependencies
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Pre-download the Whisper 'small' model at BUILD TIME
# This avoids a slow cold-start when the first request arrives.
# The 'small' model (~460MB) has much better multilingual support than 'base'.
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8'); print('Whisper small model pre-downloaded OK')"

# Expose port 8001 for this service
EXPOSE 8001

# Healthcheck so Docker knows when the service is ready
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
      CMD curl -f http://localhost:8001/health || exit 1

# Start FastAPI with uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
