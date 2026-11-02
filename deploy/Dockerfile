FROM node:24-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends python3 ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY src ./src
COPY runtime ./runtime
USER node
ENV NODE_ENV=production PYTHONDONTWRITEBYTECODE=1
CMD ["node","runtime/watchdog.cjs"]
