FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# 提前装好 SSH 和常用工具，不在容器启动时安装
# 为什么：每次启动现装要花几十秒，导致 controller 等待超时
RUN apt-get update && apt-get install -y \
    openssh-server \
    netcat-openbsd \
    python3 \
    sudo \
    && rm -rf /var/lib/apt/lists/*

# 创建 sshd 运行所需目录
RUN mkdir -p /run/sshd

# 设置 root 密码
RUN echo 'root:root123' | chpasswd

# 允许 root 登录和密码认证（后续 Ansible 会加固）
RUN sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config && \
    sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config

EXPOSE 22

CMD ["/usr/sbin/sshd", "-D"]
