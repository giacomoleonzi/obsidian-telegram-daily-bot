FROM python:3.11-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Persist Obsidian headless auth/config inside the mounted vault.
# This avoids losing `ob login` state when the container restarts.
ENV HOME=/vault

RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    bash \
    build-essential \
    ca-certificates \
    cmake \
    curl \
    ffmpeg \
    git \
    gnupg \
  && rm -rf /var/lib/apt/lists/*

# Install Node.js 22.x (npm included) for `obsidian-headless`.
RUN set -eux; \
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash -; \
  apt-get update; \
  apt-get install -y --no-install-recommends nodejs; \
  rm -rf /var/lib/apt/lists/*

RUN npm install -g obsidian-headless

RUN pip install --no-cache-dir google-genai pillow python-telegram-bot supervisor

# Build whisper.cpp for local CPU transcription on ARM64 (Raspberry Pi).
RUN git clone https://github.com/ggml-org/whisper.cpp.git /tmp/whisper.cpp \
  && cmake -S /tmp/whisper.cpp -B /tmp/whisper.cpp/build \
  && cmake --build /tmp/whisper.cpp/build --config Release -j"$(nproc)" \
  && cp /tmp/whisper.cpp/build/bin/whisper-cli /usr/local/bin/whisper-cli \
  && find /tmp/whisper.cpp/build -name "*.so*" -exec cp {} /usr/local/lib/ \; \
  && ldconfig \
  && mkdir -p /models \
  && /tmp/whisper.cpp/models/download-ggml-model.sh base \
  && cp /tmp/whisper.cpp/models/ggml-base.bin /models/ggml-base.bin \
  && rm -rf /tmp/whisper.cpp

RUN mkdir -p /app /vault/Inbox/Audio

WORKDIR /app

COPY bot.py /app/bot.py
COPY config/setup.sh /usr/local/bin/setup.sh
COPY config/supervisord.conf /etc/supervisor/supervisord.conf

RUN chmod +x /usr/local/bin/setup.sh

CMD ["supervisord", "-c", "/etc/supervisor/supervisord.conf"]

