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

# Apply deterministic, idempotent patches during image creation so every
# runtime receives the same verified camera, widget-key and inventory behavior.
RUN python scripts/apply_mobile_camera_fix.py \
    && python -m scripts.patch_inventory_name_matching \
    && python -m scripts.patch_multi_input_state \
    && python -m scripts.patch_additive_quantity_ui \
    && python -m scripts.patch_multi_input_analysis \
    && python -m scripts.patch_multi_input_tabs \
    && python -m scripts.patch_replace_semantics \
    && python -m scripts.patch_multi_input_messages

EXPOSE 8080

CMD ["streamlit", "run", "streamlit_app/app.py", "--server.port=8080", "--server.address=0.0.0.0", "--server.headless=true"]
