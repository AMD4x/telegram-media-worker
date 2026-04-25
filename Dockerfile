FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        ffmpeg \
        nodejs \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --upgrade pip \
    && python3 -m pip install --upgrade --pre "yt-dlp[default]"

RUN python3 -m yt_dlp --version \
    && node --version \
    && ffmpeg -version | head -n 1

WORKDIR /work
