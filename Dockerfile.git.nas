FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential \
       ca-certificates \
       curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt

RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip install -r /app/requirements.txt

# Copy the repository exactly as GitHub validated it. The production image must
# not depend on temporary generated files from the NAS or from previous builds.
COPY . /app

# Runtime data is provided by NAS bind mounts. Creating the directories here
# keeps Streamlit and the persistence layer safe during health checks and tests.
RUN mkdir -p /app/data /app/photos /app/backups /app/logs /app/secrets

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=5 \
  CMD curl --fail http://127.0.0.1:8080/_stcore/health || exit 1

CMD ["python", "-m", "streamlit", "run", "streamlit_app/app.py", "--server.port=8080", "--server.address=0.0.0.0", "--server.headless=true"]