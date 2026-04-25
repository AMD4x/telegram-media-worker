FROM python:3.12-slim-bookworm AS telegram_bot_api_builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        cmake \
        g++ \
        git \
        gperf \
        make \
        libssl-dev \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --recursive --depth 1 --shallow-submodules https://github.com/tdlib/telegram-bot-api.git /tmp/telegram-bot-api \
    && cmake -S /tmp/telegram-bot-api -B /tmp/telegram-bot-api/build \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX=/usr/local \
    && cmake --build /tmp/telegram-bot-api/build --target install -j"$(nproc)"


FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PIP_NO_CACHE_DIR=1
ENV DENO_INSTALL=/opt/deno
ENV PATH="/opt/deno/bin:${PATH}"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        ffmpeg \
        libssl3 \
        libstdc++6 \
        unzip \
        zlib1g \
    && rm -rf /var/lib/apt/lists/*

COPY --from=telegram_bot_api_builder /usr/local/bin/telegram-bot-api /usr/local/bin/telegram-bot-api

RUN curl -fsSL https://deno.land/install.sh | sh

RUN python3 -m pip install --upgrade pip \
    && python3 -m pip install --upgrade --pre "yt-dlp[default]"

RUN python3 -m yt_dlp --version \
    && deno --version \
    && ffmpeg -version | head -n 1 \
    && test -x /usr/local/bin/telegram-bot-api

WORKDIR /work
