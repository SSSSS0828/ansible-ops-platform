#!/bin/bash
set -e

wait_for_ssh() {
    local host=$1
    local max_attempts=60
    local attempt=0
    echo ">>> 等待 $host SSH 就绪..."
    while [ $attempt -lt $max_attempts ]; do
        if nc -z -w 2 "$host" 22 2>/dev/null; then
            echo ">>> $host SSH 已就绪"
            return 0
        fi
        attempt=$((attempt + 1))
        echo "    第 $attempt 次检测失败，3秒后重试..."
        sleep 3
    done
    echo ">>> $host SSH 等待超时"
    return 1
}

# 等待三个节点 SSH 全部就绪
wait_for_ssh node1
wait_for_ssh node2
wait_for_ssh node3

# 关闭主机指纹验证
# 为什么：第一次连接新主机时 SSH 会交互确认指纹，自动化场景不能有人工干预
export ANSIBLE_HOST_KEY_CHECKING=False

# 分发公钥到三个节点
# 为什么要分发公钥：后续 Ansible 通过 SSH 免密登录执行命令，不需要每次输密码
for host in node1 node2 node3; do
    echo ">>> 分发公钥到 $host..."
    sshpass -p root123 ssh-copy-id \
        -i /root/.ssh/id_rsa.pub \
        -o StrictHostKeyChecking=no \
        root@$host
    echo ">>> $host 公钥分发完成"
done

echo ">>> 所有节点公钥分发完成，启动 Flask..."
cd /app
python3 app.py
