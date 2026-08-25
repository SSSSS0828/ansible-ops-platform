#!/bin/bash
set -euo pipefail

: "${OPS_BOOTSTRAP_PASSWORD:?必须通过环境变量配置实验节点初始密码}"

wait_for_ssh() {
    local host="$1"
    for attempt in $(seq 1 60); do
        if nc -z -w 2 "$host" 22 2>/dev/null; then
            echo ">>> $host SSH 已就绪"
            return 0
        fi
        echo ">>> 等待 $host SSH 就绪（$attempt/60）"
        sleep 2
    done
    echo ">>> $host SSH 等待超时" >&2
    return 1
}

for host in node1 node2 node3; do
    wait_for_ssh "$host"
    sshpass -p "$OPS_BOOTSTRAP_PASSWORD" ssh-copy-id \
        -i /root/.ssh/id_ed25519.pub \
        -o ConnectTimeout=5 \
        -o PreferredAuthentications=password \
        -o PubkeyAuthentication=no \
        -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile=/dev/null \
        "root@$host"
done

exec gunicorn --bind 0.0.0.0:5000 --workers 1 --threads 8 --timeout 300 app:app
