FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 tennis-ai \
    && useradd --uid 10001 --gid tennis-ai --create-home tennis-ai \
    && install -d -m 0700 -o tennis-ai -g tennis-ai /data/media

WORKDIR /srv/tennis-ai
COPY backend/requirements.txt backend/requirements.txt
RUN python -m pip install --no-cache-dir --require-hashes -r backend/requirements.txt
COPY --chown=tennis-ai:tennis-ai backend/ backend/

USER tennis-ai
EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--limit-concurrency", "64"]
