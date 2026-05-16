# Use standard Python 3.10 on Debian Bullseye
FROM python:3.10-slim

# Install system deps: ffmpeg (audio extraction), curl (healthcheck/debug)
RUN apt-get update && apt-get install -y \
      ffmpeg \
      curl \
      && rm -rf /var/lib/apt/lists/*

# Hugging Face Spaces require running as a non-root user
RUN useradd -m -u 1000 user

USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    HF_HOME=/home/user/cache

WORKDIR $HOME/app

# Copy requirements first for better Docker layer caching
COPY --chown=user requirements.txt .

# Upgrade pip and install Python dependencies
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY --chown=user . .

# Pre-download the Whisper 'small' model at BUILD TIME
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8', download_root='/home/user/cache'); print('Whisper small model pre-downloaded OK')"

# Expose port 7860 for Hugging Face
EXPOSE 7860

# Healthcheck so Docker knows when the service is ready
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
      CMD curl -f http://localhost:7860/health || exit 1

# Start FastAPI with uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
