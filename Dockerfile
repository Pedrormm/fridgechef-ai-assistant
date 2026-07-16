FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . ./

# Apply the deterministic UI patch during image creation so every container
# receives the rear-camera and unique-widget-key fixes from the same source.
RUN python scripts/apply_mobile_camera_fix.py

EXPOSE 8080

CMD ["streamlit", "run", "streamlit_app/app.py", "--server.port=8080", "--server.address=0.0.0.0", "--server.headless=true"]
