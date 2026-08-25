FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    netcat-openbsd \
    openssh-client \
    python3 \
    python3-pip \
    sshpass \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt
RUN ssh-keygen -t ed25519 -f /root/.ssh/id_ed25519 -N ""

COPY . .
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

HEALTHCHECK --interval=10s --timeout=3s --retries=6 \
    CMD curl -fsS http://127.0.0.1:5000/healthz || exit 1

CMD ["/entrypoint.sh"]
