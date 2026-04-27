FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libglib2.0-0 \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./

RUN pip install --upgrade pip \
    && pip install -r requirements.txt

COPY src ./src

RUN useradd --create-home --shell /bin/bash appuser \
    && mkdir -p /app/extracted_images /app/figure_info \
    && chown -R appuser:appuser /app

USER appuser

CMD ["python", "-m", "src.main"]