FROM python:3.12-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        tzdata \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -u 1000 -m app
COPY --from=builder /root/.local /home/app/.local
RUN chown -R 1000:1000 /home/app/.local

ENV PATH=/home/app/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
COPY --chown=1000:1000 timelapse.py entrypoint.sh ./
RUN chmod +x entrypoint.sh

USER 1000:1000

LABEL com.centurylinklabs.watchtower.enable="true"

ENTRYPOINT ["/app/entrypoint.sh"]
