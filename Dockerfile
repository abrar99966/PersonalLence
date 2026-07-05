# syntax=docker/dockerfile:1

# ---- stage 1: compile gosearch (no Linux release exists, only a .exe) ----
FROM golang:1.24-bookworm AS gobuild
RUN go install github.com/ibnaleem/gosearch@latest
# -> /go/bin/gosearch

# ---- stage 2: the app ----
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates tar \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Go binaries into ./bin (resolved by app/engines/base.py)
RUN mkdir -p /app/bin
COPY --from=gobuild /go/bin/gosearch /app/bin/gosearch
RUN curl -sL -o /tmp/pi.tar.gz \
      https://github.com/sundowndev/phoneinfoga/releases/latest/download/phoneinfoga_Linux_x86_64.tar.gz \
    && tar -xzf /tmp/pi.tar.gz -C /app/bin phoneinfoga \
    && rm /tmp/pi.tar.gz \
    && chmod +x /app/bin/gosearch /app/bin/phoneinfoga

# Python deps + the pip-based OSINT engines
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

ENV PORT=8000
EXPOSE 8000

# --proxy-headers/--forwarded-allow-ips so OAuth builds correct https URLs behind
# Cloudflare + the host's proxy.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips=*"]
