#!/bin/bash
set -euo pipefail

: "${OPS_BOOTSTRAP_PASSWORD:?必须通过环境变量配置实验节点初始密码}"
echo "root:${OPS_BOOTSTRAP_PASSWORD}" | chpasswd
sed -ri 's/^#?PermitRootLogin .*/PermitRootLogin yes/' /etc/ssh/sshd_config
sed -ri 's/^#?PasswordAuthentication .*/PasswordAuthentication yes/' /etc/ssh/sshd_config

exec /usr/bin/supervisord -c /etc/supervisor/supervisord.conf
