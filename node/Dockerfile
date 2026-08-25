FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    openssh-server \
    python3 \
    sudo \
    supervisor \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /run/sshd /var/log/supervisor

COPY supervisord.conf /etc/supervisor/supervisord.conf
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 22 9100
HEALTHCHECK --interval=10s --timeout=3s --retries=6 CMD bash -c 'exec 3<>/dev/tcp/127.0.0.1/22'
CMD ["/entrypoint.sh"]
