FROM node:20-bookworm-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        ffmpeg \
        make \
        g++ \
        python3 \
        python3-pip \
    && python3 -m pip install --break-system-packages --no-cache-dir edge-tts \
    && rm -rf /var/lib/apt/lists/*

COPY package*.json ./
RUN npm install --omit=dev

COPY . .
RUN mkdir -p /app/data/auth /app/data/tmp

ENV REDIA_HOST=0.0.0.0
ENV REDIA_PORT=3099
ENV REDIA_DATA_DIR=/app/data
ENV REDIA_DB_PATH=/app/data/redia.sqlite

EXPOSE 3099

CMD ["npm", "start"]
