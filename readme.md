# 基于 Ansible 的自动化运维管理平台

## 项目简介

面向多节点 Linux 环境的自动化运维平台。支持通过 Web 界面触发 Ansible Playbook，批量完成服务器初始化、应用部署等运维任务，执行日志实时回显，历史记录持久化存储，底层接入 Prometheus + Grafana 实现被管节点指标监控。

**技术栈**：Python · Flask · Flask-SocketIO · Ansible · Docker · Docker Compose · Prometheus · Grafana

---
## 项目截图

### Flask 运维平台
![Flask平台执行成功](docs/flask_success.png)

### Prometheus 采集状态
![Prometheus三节点全部UP](docs/prometheus_targets.png)

### Grafana 监控面板
![Grafana节点监控面板](docs/grafana_dashboard.png)

---

## 技术选型原因

### 为什么用 Ansible 而不是 Shell 脚本？

Shell 脚本可以完成批量操作，但有几个根本性问题：

1. **不具备幂等性**：Shell 脚本重复执行会重复执行所有命令，比如 `useradd ops` 第二次执行会报错"用户已存在"。Ansible 的大多数模块执行前会先检查目标状态，状态已满足则跳过，天然幂等。

2. **多机器管理复杂**：用 Shell 管理 20 台机器需要 for 循环 + ssh 远程执行，错误处理、并发控制都要自己写。Ansible 内置并发执行（forks）、错误处理、重试机制。

3. **可读性差**：Shell 脚本逻辑复杂后难以维护。Ansible 的 YAML Playbook 接近自然语言，`- name: 创建运维用户` 直接说明意图。

4. **无法管理配置模板**：Nginx 配置文件里有动态变量（IP、域名），Shell 只能 sed 替换，Ansible 的 template 模块用 Jinja2 引擎渲染，更安全可控。

### 为什么用 Prometheus 而不是 Zabbix？

Zabbix 是传统监控系统，Prometheus 是云原生时代的主流选择，区别如下：

| 对比项 | Prometheus | Zabbix |
|--------|-----------|--------|
| 数据采集 | Pull（主动拉取） | Push（被动接收）或 Agent Pull |
| 部署复杂度 | 简单，单二进制 | 复杂，需要数据库 |
| 查询语言 | PromQL，灵活强大 | 有限的表达式 |
| 生态 | 丰富的 Exporter | 内置插件为主 |
| 适用场景 | 容器、微服务、动态环境 | 传统物理机、稳定环境 |

本项目选 Prometheus 的核心原因：与容器生态天然契合，node_exporter 只需暴露一个 HTTP 端口，Prometheus 定时来拉，不需要在被管节点安装复杂的 Agent。

### 为什么用 Docker Compose 而不是直接 Docker 命令？

`docker run` 命令管理多个容器时需要手动维护启动顺序、网络配置、端口映射，重启时需要逐个操作。Docker Compose 用一个 YAML 文件声明所有服务的关系，一条命令 `docker compose up -d` 启动全部，`docker compose down` 停止全部，适合本地开发和演示。

### 为什么用 Flask + SocketIO 而不是直接命令行？

命令行执行 Ansible 没有可视化界面，不方便展示给面试官或非技术人员。Flask 提供 Web 界面，SocketIO 实现 WebSocket 连接，可以把 Ansible 执行过程的每一行日志实时推送到浏览器，体验接近真实运维平台（如 Ansible Tower/AWX）。

---

## 架构说明

```
用户浏览器
    │
    │ HTTP + WebSocket
    ▼
Flask Web 服务（controller:5000）
    │
    │ 子进程调用
    ▼
ansible-playbook 命令
    │
    │ SSH 免密登录（RSA 密钥）
    ├──► node1（ubuntu容器，sshd监听22）
    ├──► node2
    └──► node3
         │
         │ node_exporter 监听 9100
         ▼
Prometheus（定时 Pull，15秒一次）
    │
    ▼
Grafana（查询 Prometheus，可视化展示）
```

**网络说明**：所有容器在同一个 Docker 自定义网络 `ops-net` 中。自定义网络会自动实现容器名到 IP 的 DNS 解析，controller 可以直接用 `node1` 作为主机名访问 node1 容器，Prometheus 可以用 `node1:9100` 访问 node_exporter，不需要写死 IP（容器重启后 IP 可能变化）。

---

## 目录结构

```
ansible-ops-platform/
├── docker-compose.yml          # 所有服务的编排配置
├── prometheus/
│   └── prometheus.yml          # Prometheus 采集配置
├── grafana/
│   └── provisioning/           # Grafana 自动加载配置（本项目暂未使用）
├── node/
│   └── Dockerfile              # 被管节点镜像，预装 SSH
└── controller/                 # 控制节点，运行 Ansible + Flask
    ├── Dockerfile              # 控制节点镜像，装 Python/Ansible/SSH客户端
    ├── entrypoint.sh           # 容器启动脚本
    ├── requirements.txt        # Python 依赖
    ├── app.py                  # Flask 主程序
    ├── inventory/
    │   └── hosts.ini           # Ansible 主机清单
    ├── playbooks/              # Playbook 入口文件（含 hosts 字段）
    │   ├── init.yml
    │   └── node_exporter.yml
    ├── roles/                  # Ansible Role（任务实现）
    │   ├── init/
    │   │   └── tasks/main.yml
    │   └── node_exporter/
    │       └── tasks/main.yml
    └── templates/
        └── index.html          # 前端页面
```

---

## 前置要求

### 安装 Docker（Ubuntu）

```bash
# 第一步：安装依赖工具
sudo apt update
sudo apt install -y ca-certificates curl gnupg

# 第二步：添加 Docker 官方 GPG 密钥
# 为什么需要 GPG key：验证下载的软件包确实来自 Docker 官方，防止被篡改
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
    sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# 第三步：添加 Docker apt 仓库
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# 第四步：安装 Docker Engine 和 Compose 插件
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# 第五步：把当前用户加入 docker 组，避免每次都要 sudo
# 为什么：docker 命令默认需要 root 权限，加入 docker 组后普通用户也能用
sudo usermod -aG docker $USER
newgrp docker  # 立即生效，不需要重新登录

# 验证
docker --version
docker compose version
```

---

## 部署步骤

### 第一步：建立目录结构

```bash
git clone https://github.com/你的用户名/ansible-ops-platform.git
cd ansible-ops-platform

mkdir -p controller/inventory
mkdir -p controller/roles/init/tasks
mkdir -p controller/roles/node_exporter/tasks
mkdir -p controller/playbooks
mkdir -p controller/templates
mkdir -p prometheus
mkdir -p grafana/provisioning
mkdir -p node
```

验证：

```bash
find . -type d | sort
```

### 第二步：写 node/Dockerfile（被管节点镜像）

**为什么要单独构建节点镜像，而不是用官方 ubuntu 镜像直接启动时安装？**

最初方案是在 docker-compose.yml 的 `command` 字段里写 `apt-get install openssh-server`，每次容器启动时现装。但这样有严重问题：安装过程需要 30~60 秒，而 controller 容器启动后很快就去连 SSH，导致"Connection refused"。

把安装步骤放进 Dockerfile，构建镜像时只装一次，之后每次容器启动直接运行 sshd，毫秒级就绪。

```bash
cat > node/Dockerfile << 'EOF'
FROM ubuntu:22.04

# 设置非交互模式，避免安装时弹出时区/地区选择界面卡住构建
ENV DEBIAN_FRONTEND=noninteractive

# 预装所有依赖，构建时装一次，后续每次启动不需要再装
RUN apt-get update && apt-get install -y \
    openssh-server \    # SSH 服务，Ansible 通过 SSH 连接
    netcat-openbsd \    # nc 命令，用于检测端口连通性
    python3 \           # Ansible 在被管节点执行模块需要 Python
    sudo \              # 允许 ops 用户 sudo
    && rm -rf /var/lib/apt/lists/*
    # 清理包缓存，减小镜像体积（apt 缓存不需要保留）

# sshd 运行需要这个目录存在
RUN mkdir -p /run/sshd

# 设置 root 密码（仅用于第一次公钥分发，之后全用密钥登录）
RUN echo 'root:root123' | chpasswd

# 允许 root 通过 SSH 登录（生产环境不建议，这里是为了简化演示）
# 允许密码认证（仅用于公钥分发阶段）
RUN sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config && \
    sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config

EXPOSE 22

# 容器启动时直接运行 sshd
# -D 参数：前台运行，不 daemon 化（容器里进程必须前台运行，否则容器会立即退出）
CMD ["/usr/sbin/sshd", "-D"]
EOF
```

### 第三步：写 docker-compose.yml

**docker-compose.yml 各字段详解：**

```bash
cat > docker-compose.yml << 'EOF'
services:

  node1:
    build: ./node          # 从 ./node/Dockerfile 构建镜像，而不是从仓库拉取
    container_name: node1  # 固定容器名，同时作为 DNS 名称在网络内访问
    hostname: node1        # 容器内部的主机名（影响 hostname 命令的输出）
    networks:
      - ops-net            # 加入自定义网络，可以用容器名互访

  node2:
    build: ./node
    container_name: node2
    hostname: node2
    networks:
      - ops-net

  node3:
    build: ./node
    container_name: node3
    hostname: node3
    networks:
      - ops-net

  controller:
    build: ./controller    # 从 ./controller/Dockerfile 构建
    container_name: controller
    networks:
      - ops-net
    ports:
      - "5000:5000"        # 宿主机5000端口 → 容器5000端口，暴露 Flask 服务
    depends_on:
      - node1              # 保证 node 容器先启动，再启动 controller
      - node2              # 注意：只保证启动顺序，不保证 SSH 服务就绪
      - node3              # 所以 entrypoint.sh 里还需要循环等待

  prometheus:
    image: prom/prometheus:latest  # 直接用官方镜像，不需要定制
    container_name: prometheus
    networks:
      - ops-net
    ports:
      - "9090:9090"        # 暴露 Prometheus Web UI 和 API
    volumes:
      - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml
      # 把宿主机的配置文件挂载到容器内
      # 注意：宿主机路径必须是文件，不能是目录，否则 Docker 会创建目录导致报错

  grafana:
    image: grafana/grafana:latest
    container_name: grafana
    networks:
      - ops-net
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin123  # 设置 Grafana admin 密码
    volumes:
      - ./grafana/provisioning:/etc/grafana/provisioning

networks:
  ops-net:
    driver: bridge
    # bridge 模式：Docker 创建一个虚拟网桥，所有加入的容器连接到这个网桥
    # 同一网桥内的容器可以互相访问，且有 DNS 解析（容器名 → IP）
    # 与默认的 bridge 网络区别：自定义网络支持容器名 DNS，默认网络不支持
EOF
```

**为什么 prometheus.yml 挂载时必须提前创建文件？**

Docker 的 volumes 挂载行为：如果宿主机路径不存在，Docker 会自动创建一个**目录**。而 Prometheus 期望挂载的是一个**文件**。结果就是容器内 `/etc/prometheus/prometheus.yml` 变成了目录，Prometheus 启动时读取配置失败，报错 "not a directory"（实际上是反过来，把文件路径挂成了目录）。

解决方法：先创建文件，再启动容器。

### 第四步：写 prometheus/prometheus.yml

**配置项详解：**

```bash
cat > prometheus/prometheus.yml << 'EOF'
global:
  scrape_interval: 15s      # 每 15 秒采集一次所有目标的指标
                            # 太短：被监控目标压力大，Prometheus 存储压力大
                            # 太长：告警延迟高，感知问题慢
  evaluation_interval: 15s  # 每 15 秒评估一次告警规则
                            # 建议与 scrape_interval 保持一致

scrape_configs:
  - job_name: 'node_exporter'   # job 名称，会作为 label 附在采集的指标上
                                # 例如：node_cpu_seconds_total{job="node_exporter"}
    static_configs:
      - targets:
          - 'node1:9100'    # node1 容器的 9100 端口（node_exporter 默认端口）
          - 'node2:9100'    # 用容器名而不是 IP，因为容器重启后 IP 可能变化
          - 'node3:9100'    # Prometheus 容器和 node 容器在同一网络，容器名可解析
EOF
```

**Prometheus Pull 模型工作原理：**

Prometheus 启动后，按照 `scrape_interval` 定时向每个 target 发送 HTTP GET 请求到 `/metrics` 路径，node_exporter 返回纯文本格式的指标数据，Prometheus 解析后存入本地时序数据库（TSDB）。

这与 Zabbix 的 Push 模型相反——Zabbix Agent 主动把数据推给 Server，Prometheus 是自己去拉。Pull 模型的优点是控制权在 Prometheus 侧，方便发现目标是否挂掉（拉不到数据就告警）。

### 第五步：写 controller/requirements.txt

```bash
cat > controller/requirements.txt << 'EOF'
flask==3.0.0          # Web 框架，处理 HTTP 请求和模板渲染
flask-socketio==5.3.6 # 为 Flask 添加 WebSocket 支持，实现实时日志推送
EOF
```

**为什么不加 eventlet？**

最初方案包含 `eventlet==0.35.1`，eventlet 是一个异步网络库，Flask-SocketIO 推荐用它提升并发性能。但在实际调试中发现，当前环境下 eventlet 与 Flask-SocketIO 存在兼容性问题：WebSocket 的 `run_playbook` 事件能被前端发出，但后端静默失败，没有任何报错，日志框永远显示"正在执行..."。

排查过程：检查 `docker logs controller` 没有任何请求记录，说明事件根本没到达后端。改用 `async_mode='threading'` 后问题消失。threading 模式使用 Python 标准库的线程，无外部依赖，稳定性更好，代价是高并发性能略差（对运维平台这种低频操作完全够用）。

### 第六步：写 controller/Dockerfile

```bash
cat > controller/Dockerfile << 'EOF'
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    python3 \           # Flask 和 Ansible 都基于 Python
    python3-pip \       # Python 包管理器，用于安装 Flask 等
    ansible \           # 自动化运维工具，执行 Playbook
    openssh-client \    # SSH 客户端，Ansible 通过 SSH 连接被管节点
    sshpass \           # 允许在命令行传递 SSH 密码（用于初次分发公钥）
    netcat-openbsd \    # nc 命令，用于检测被管节点 SSH 端口是否就绪
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app           # 设置工作目录，后续 COPY、RUN 等命令的相对路径基准

COPY requirements.txt .
RUN pip3 install -r requirements.txt

# 生成 SSH 密钥对
# -t rsa：使用 RSA 算法
# -b 4096：4096 位密钥，安全性高
# -f：指定密钥文件路径
# -N ""：不设置密码短语（自动化场景不能有交互）
RUN ssh-keygen -t rsa -b 4096 -f /root/.ssh/id_rsa -N ""

COPY . .               # 把 controller 目录下所有文件复制到容器 /app

# 单独 COPY entrypoint.sh 并设置可执行权限
# 为什么单独 COPY：确保权限设置正确，不依赖宿主机的文件权限
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

CMD ["/entrypoint.sh"]
EOF
```

### 第七步：写 controller/entrypoint.sh

**为什么需要 entrypoint.sh，不直接在 Dockerfile CMD 里写命令？**

容器启动时需要按顺序完成三件事：等待 SSH 就绪 → 分发公钥 → 启动 Flask。这三步有依赖关系，且第一步需要循环等待，用 Shell 脚本表达比 Dockerfile CMD 更清晰。

**为什么用循环检测而不是 `sleep 30`？**

固定 sleep 有两个问题：等太短不够用（网络慢时 SSH 还没就绪）；等太长浪费时间（SSH 5秒就好了却等了30秒）。循环检测每次等 3 秒，SSH 就绪立即继续，最多等 60 次（180秒），适应不同网络环境。

**nc 命令的作用：**

`nc -z -w 2 node1 22` 中：
- `-z`：只检测端口是否开放，不发送数据
- `-w 2`：等待超时 2 秒
- 返回码 0 表示端口可达，非 0 表示不可达

```bash
cat > controller/entrypoint.sh << 'EOF'
#!/bin/bash
set -e  # 任何命令失败立即退出脚本，避免错误被忽略继续执行

wait_for_ssh() {
    local host=$1
    local max_attempts=60      # 最多等 60 * 3 = 180 秒
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

wait_for_ssh node1
wait_for_ssh node2
wait_for_ssh node3

# 关闭主机指纹验证
# 默认情况下第一次 SSH 连接新主机时会提示"是否信任该主机指纹"，
# 需要手动输入 yes，自动化场景无法处理这个交互，必须关闭
export ANSIBLE_HOST_KEY_CHECKING=False

# 分发公钥
# sshpass -p root123：把密码传给 ssh-copy-id（只在初次分发时用密码）
# ssh-copy-id：把 /root/.ssh/id_rsa.pub 的内容追加到目标机器的 authorized_keys
# -o StrictHostKeyChecking=no：同上，跳过指纹确认
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
EOF
```

**SSH 免密登录原理：**

1. controller 容器启动时生成一对密钥：私钥（id_rsa）和公钥（id_rsa.pub）
2. 通过 sshpass 用密码登录各节点，把公钥内容写入节点的 `~/.ssh/authorized_keys`
3. 之后 Ansible 连接节点时，用私钥做认证：controller 发送"用私钥签名的数据"，节点用 authorized_keys 里的公钥验证签名，验证通过则允许登录，全程不需要密码

### 第八步：写 controller/inventory/hosts.ini

**Ansible Inventory 详解：**

Inventory 是 Ansible 的"主机名单"，告诉 Ansible 要管理哪些机器、如何连接它们。

```bash
cat > controller/inventory/hosts.ini << 'EOF'
# [组名] 定义主机组，Playbook 里用 hosts: 指定在哪个组执行
[webservers]
node1 ansible_host=node1 ansible_user=root ansible_ssh_private_key_file=/root/.ssh/id_rsa
# node1：主机别名（在 Ansible 里引用的名字）
# ansible_host：实际连接的地址（这里用容器名，Docker DNS 会解析成 IP）
# ansible_user：SSH 登录用户名
# ansible_ssh_private_key_file：SSH 私钥路径（免密登录用）

[dbservers]
node2 ansible_host=node2 ansible_user=root ansible_ssh_private_key_file=/root/.ssh/id_rsa

[monitored]
# monitored 组包含所有三个节点，用于部署 node_exporter
node1 ansible_host=node1 ansible_user=root ansible_ssh_private_key_file=/root/.ssh/id_rsa
node2 ansible_host=node2 ansible_user=root ansible_ssh_private_key_file=/root/.ssh/id_rsa
node3 ansible_host=node3 ansible_user=root ansible_ssh_private_key_file=/root/.ssh/id_rsa

[all:vars]
# 所有主机共用的变量
ansible_python_interpreter=/usr/bin/python3
# 明确指定 Python 解释器路径
# 为什么需要：某些系统默认 python 指向 python2，Ansible 模块需要 python3
EOF
```

### 第九步：写 Playbook 入口文件

**为什么需要单独的入口文件，不能直接执行 tasks/main.yml？**

`ansible-playbook` 命令期望一个完整的 Playbook 文件，格式是：

```yaml
- hosts: xxx      # 在哪些机器上执行（必须有）
  tasks:
    - ...
```

而 `roles/node_exporter/tasks/main.yml` 只包含任务列表，没有 `hosts:` 字段，直接执行会报错 `'get_url' is not a valid attribute for a Play`（Ansible 把第一个 task 当成了 Play 的属性）。

入口文件的作用是声明"在哪些机器上"执行"哪些任务"：

```bash
mkdir -p controller/playbooks

cat > controller/playbooks/init.yml << 'EOF'
---
- hosts: all          # all 表示 inventory 里所有主机，实际执行时用 --limit 限制范围
  gather_facts: yes   # 执行前收集被管节点的系统信息（OS 类型、IP、内存等）
                      # 存储在 ansible_* 变量中，tasks 里可以用
  tasks:
    - import_tasks: /app/roles/init/tasks/main.yml
    # import_tasks：静态引入，解析阶段就确定，适合无条件引入
EOF

cat > controller/playbooks/node_exporter.yml << 'EOF'
---
- hosts: all
  gather_facts: yes
  tasks:
    - import_tasks: /app/roles/node_exporter/tasks/main.yml
EOF
```

### 第十步：写 init Role

**每个 task 的作用和原因：**

```bash
cat > controller/roles/init/tasks/main.yml << 'EOF'
---
# apt 模块：管理 Debian/Ubuntu 系软件包，具备幂等性
# state: present 表示"确保已安装"，已安装则跳过，未安装则安装
- name: 安装基础工具
  apt:
    name:
      - ufw     # 防火墙管理工具（Uncomplicated Firewall）
      - curl    # HTTP 客户端，常用于下载和测试接口
      - vim     # 文本编辑器
    state: present
    update_cache: yes  # 相当于先执行 apt-get update，确保包列表是最新的

# user 模块：管理 Linux 用户，幂等（用户已存在则不重复创建）
- name: 创建运维用户 ops
  user:
    name: ops
    shell: /bin/bash   # 指定登录 shell
    create_home: yes   # 创建家目录 /home/ops

# lineinfile 模块：确保文件中某行存在（幂等）
# 为什么给 ops 配置 sudo：生产环境不应该直接用 root 做日常运维，
# 用专门的运维账号，操作有记录，权限可控
- name: 配置 ops 用户免密 sudo
  lineinfile:
    path: /etc/sudoers
    line: "ops ALL=(ALL) NOPASSWD:ALL"
    validate: "visudo -cf %s"  # 写入前用 visudo 验证语法，防止 sudoers 损坏导致无法 sudo

# timezone 模块：设置系统时区
# 为什么要统一时区：多节点环境下如果时区不一致，日志时间戳对不上，排查问题困难
- name: 设置时区为上海
  timezone:
    name: Asia/Shanghai

# ufw 模块：管理防火墙规则（幂等）
# 默认策略 deny all，只开放必要端口，最小化攻击面
- name: 放行 SSH 端口
  ufw:
    rule: allow
    port: "22"

- name: 放行 HTTP 端口
  ufw:
    rule: allow
    port: "80"

- name: 放行 Node Exporter 端口
  ufw:
    rule: allow
    port: "9100"   # Prometheus 需要从这个端口采集指标

- name: 启用防火墙
  ufw:
    state: enabled
    policy: deny   # 默认拒绝所有入站，只允许上面明确放行的端口
EOF
```

### 第十一步：写 node_exporter Role

**关键设计决策：为什么不用 systemd？**

在真实服务器上，推荐用 systemd 管理 node_exporter（开机自启、自动重启、日志管理）。但本项目的"服务器"是 Docker 容器，容器的 PID 1 是 sshd，不是 systemd。在容器内执行 `systemctl` 会报错：

```
System has not been booted with systemd as init system (PID 1). Can't operate.
Failed to connect to bus: Host is down
```

原因：systemd 需要作为 PID 1 运行才能正常工作，容器里 PID 1 是 sshd，systemd 的 D-Bus 总线没有启动，所以连接失败。

解决方案：用 `nohup` 把 node_exporter 放到后台运行。nohup 的作用是忽略 SIGHUP 信号（终端断开时发出），让进程在后台持续运行。

**幂等性设计：**

`nohup ... &` 如果重复执行会启动多个 node_exporter 进程，9100 端口冲突导致后续进程启动失败。解决方案是先用 `pgrep` 检测进程是否存在，已存在则跳过启动步骤。

```bash
cat > controller/roles/node_exporter/tasks/main.yml << 'EOF'
---
# get_url 模块：下载文件，幂等（文件已存在且 checksum 一致则跳过）
- name: 下载 node_exporter
  get_url:
    url: "https://github.com/prometheus/node_exporter/releases/download/v1.7.0/node_exporter-1.7.0.linux-amd64.tar.gz"
    dest: /tmp/node_exporter.tar.gz
    timeout: 60  # 网络慢时适当增加超时

# unarchive 模块：解压文件
# remote_src: yes 表示源文件在被管节点上，不是在控制节点上
- name: 解压 node_exporter
  unarchive:
    src: /tmp/node_exporter.tar.gz
    dest: /tmp/
    remote_src: yes

# copy 模块：复制文件
# remote_src: yes 表示源和目标都在被管节点，只是换个位置
# mode: '0755' 设置可执行权限
- name: 复制二进制文件到 /usr/local/bin
  copy:
    src: /tmp/node_exporter-1.7.0.linux-amd64/node_exporter
    dest: /usr/local/bin/node_exporter
    mode: '0755'
    remote_src: yes

# shell 模块：执行 shell 命令（非幂等，需要手动处理）
# pgrep -x node_exporter：精确匹配进程名（-x 表示全名匹配）
# register：把命令结果存到变量 pgrep_result
# ignore_errors: yes：pgrep 找不到进程时返回码为 1，不加这行会导致 task 失败
- name: 检查 node_exporter 是否已在运行
  shell: pgrep -x node_exporter
  register: pgrep_result
  ignore_errors: yes

# when: pgrep_result.rc != 0：只有 pgrep 返回非 0（进程不存在）时才执行
# nohup ... &：后台运行，忽略挂断信号
# > /var/log/node_exporter.log 2>&1：标准输出和错误都重定向到日志文件
- name: 启动 node_exporter
  shell: nohup /usr/local/bin/node_exporter > /var/log/node_exporter.log 2>&1 &
  when: pgrep_result.rc != 0

# wait_for 模块：等待端口就绪，确认 node_exporter 真正启动成功
# 如果 10 秒内端口还没开放，task 失败，Playbook 中止
- name: 等待 node_exporter 端口就绪
  wait_for:
    port: 9100
    timeout: 10
EOF
```

### 第十二步：写 controller/app.py

**代码结构说明：**

```bash
cat > controller/app.py << 'EOF'
from flask import Flask, render_template
from flask_socketio import SocketIO, emit
import subprocess
import sqlite3
import datetime
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'ops-secret'  # WebSocket 需要一个 secret key 做 session 签名

# async_mode='threading'：使用多线程模式
# 为什么不用 eventlet：实测发现 eventlet 与当前环境不兼容，
# WebSocket on 事件静默失败，改用 threading 模式后正常
# cors_allowed_origins='*'：允许所有来源的 WebSocket 连接
# 生产环境应限制为具体域名
socketio = SocketIO(app, async_mode='threading', cors_allowed_origins='*')

DB_PATH = '/app/history.db'

def init_db():
    # SQLite：轻量级嵌入式数据库，不需要独立数据库服务
    # 适合存储执行历史这种低频、小数据量的场景
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''CREATE TABLE IF NOT EXISTS history
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                     time TEXT,
                     playbook TEXT,
                     hosts TEXT,
                     status TEXT,
                     duration INTEGER)''')
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def index():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        'SELECT * FROM history ORDER BY id DESC LIMIT 20'
    ).fetchall()
    conn.close()
    return render_template('index.html', history=rows)

@socketio.on('run_playbook')
def handle_run(data):
    # 这个函数在前端 socket.emit('run_playbook', {...}) 时触发
    playbook = data.get('playbook')
    hosts    = data.get('hosts')
    start    = datetime.datetime.now()

    playbook_path  = f'/app/playbooks/{playbook}.yml'
    inventory_path = '/app/inventory/hosts.ini'

    if not os.path.exists(playbook_path):
        emit('log', {'data': f'[错误] Playbook 不存在: {playbook_path}\n'})
        emit('done', {'status': 'failed', 'duration': 0})
        return

    cmd = [
        'ansible-playbook',
        playbook_path,
        '-i', inventory_path,
        '--limit', hosts,   # 限制执行范围，即使 playbook 里写的是 hosts: all
    ]

    emit('log', {'data': f'执行命令: {" ".join(cmd)}\n'})

    # subprocess.Popen：启动子进程执行 ansible-playbook
    # stdout=PIPE：把子进程的标准输出重定向到管道，让父进程可以读取
    # stderr=STDOUT：把错误输出合并到标准输出，一起处理
    # text=True：以文本模式读取（而不是 bytes）
    # bufsize=1：行缓冲，每行输出后立即可读（不等缓冲区满）
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env={**os.environ, 'ANSIBLE_HOST_KEY_CHECKING': 'False'}
        # 继承当前环境变量，并追加/覆盖 ANSIBLE_HOST_KEY_CHECKING
    )

    # iter(proc.stdout.readline, '')：逐行读取输出，直到读到空字符串（EOF）
    # 为什么不用 proc.stdout.read()：read() 会阻塞直到进程结束，无法实时推送
    # 这里逐行读取，每读到一行就通过 WebSocket emit 推送到前端
    for line in iter(proc.stdout.readline, ''):
        emit('log', {'data': line})

    proc.stdout.close()
    proc.wait()  # 等待子进程完全结束

    status   = 'success' if proc.returncode == 0 else 'failed'
    # returncode 0 表示 ansible-playbook 执行成功（所有 task 都 ok/changed）
    # 非 0 表示有 task 失败
    duration = (datetime.datetime.now() - start).seconds

    # 写入执行历史
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        'INSERT INTO history (time, playbook, hosts, status, duration) VALUES (?,?,?,?,?)',
        (start.strftime('%Y-%m-%d %H:%M:%S'), playbook, hosts, status, duration)
    )
    conn.commit()
    conn.close()

    emit('done', {'status': status, 'duration': duration})
    # 前端收到 done 事件后，显示执行结果并刷新页面

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=False,
                 allow_unsafe_werkzeug=True)
    # host='0.0.0.0'：监听所有网络接口，容器外才能访问（默认 127.0.0.1 只能本机访问）
    # allow_unsafe_werkzeug=True：Flask-SocketIO 在生产环境警告使用 Werkzeug，
    # 添加这个参数消除警告（演示项目可以接受）
EOF
```

### 第十三步：写 controller/templates/index.html

```bash
cat > controller/templates/index.html << 'EOF'
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <title>Ansible 运维平台</title>
    <!-- 从 CDN 加载 Socket.IO 客户端库，版本需与服务端 flask-socketio 兼容 -->
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.6.1/socket.io.min.js"></script>
    <style>
        body { font-family: monospace; background: #1e1e1e; color: #d4d4d4; padding: 20px; }
        h1 { color: #4ec9b0; }
        select, button { padding: 8px 16px; margin: 5px; font-size: 14px; }
        button { background: #0e639c; color: white; border: none; cursor: pointer; border-radius: 4px; }
        button:disabled { background: #555; cursor: not-allowed; }
        #log { background: #0d0d0d; border: 1px solid #333; padding: 15px;
               height: 400px; overflow-y: auto; white-space: pre-wrap;
               font-size: 13px; margin-top: 15px; }
        .success { color: #4ec9b0; }
        .failed  { color: #f44747; }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; }
        th, td { border: 1px solid #333; padding: 8px 12px; text-align: left; }
        th { background: #2d2d2d; color: #9cdcfe; }
    </style>
</head>
<body>
    <h1>Ansible 自动化运维平台</h1>

    <div>
        <label>Playbook：</label>
        <select id="playbook">
            <option value="init">init（服务器初始化）</option>
            <option value="node_exporter">node_exporter（部署监控）</option>
        </select>

        <label>目标主机组：</label>
        <select id="hosts">
            <option value="monitored">monitored（全部节点）</option>
            <option value="webservers">webservers（node1）</option>
            <option value="dbservers">dbservers（node2）</option>
        </select>

        <button id="runBtn" onclick="runPlaybook()">▶ 执行</button>
    </div>

    <!-- 日志输出区域 -->
    <div id="log">等待执行...</div>

    <h2>执行历史</h2>
    <table>
        <tr><th>时间</th><th>Playbook</th><th>目标</th><th>状态</th><th>耗时(s)</th></tr>
        <!-- Jinja2 模板语法，Flask 渲染时替换为数据库中的记录 -->
        {% for row in history %}
        <tr>
            <td>{{ row[1] }}</td>
            <td>{{ row[2] }}</td>
            <td>{{ row[3] }}</td>
            <td class="{{ row[4] }}">{{ row[4] }}</td>
            <td>{{ row[5] }}</td>
        </tr>
        {% endfor %}
    </table>

    <script>
        // 建立 WebSocket 连接
        // io() 自动连接到当前页面的服务器
        const socket = io();
        const logDiv = document.getElementById('log');

        // 监听服务端推送的 log 事件，把日志追加到 logDiv
        socket.on('log', function(data) {
            logDiv.textContent += data.data;
            logDiv.scrollTop = logDiv.scrollHeight;  // 自动滚动到底部
        });

        // 监听 done 事件，显示结果并刷新页面（更新执行历史表格）
        socket.on('done', function(data) {
            logDiv.textContent += '\n--- 执行' + data.status + '，耗时 ' + data.duration + ' 秒 ---\n';
            document.getElementById('runBtn').disabled = false;
            setTimeout(() => location.reload(), 2000);  // 2秒后刷新
        });

        function runPlaybook() {
            const playbook = document.getElementById('playbook').value;
            const hosts    = document.getElementById('hosts').value;
            logDiv.textContent = '正在执行...\n';
            document.getElementById('runBtn').disabled = true;  // 防止重复点击
            // 向服务端发送 run_playbook 事件，触发后端 handle_run 函数
            socket.emit('run_playbook', { playbook, hosts });
        }
    </script>
</body>
</html>
EOF
```

### 第十四步：启动所有服务

```bash
cd ~/ansible-ops-platform
docker compose up -d --build
# -d：后台运行（detached mode）
# --build：强制重新构建镜像（即使镜像已存在）
# 构建时间约 3~5 分钟，主要耗时在安装 ansible
```

### 第十五步：验证部署

```bash
# 1. 确认所有容器正常运行
docker compose ps
# 正常输出：6 个容器全部 STATUS 为 Up

# 2. 验证 Ansible 连通性
docker exec controller ansible all -i /app/inventory/hosts.ini -m ping
# 正常输出：三个节点全部返回 "ping": "pong"

# 3. 查看 controller 启动日志
docker compose logs controller
# 正常输出：等待SSH就绪 → 公钥分发完成 → 启动Flask
```

---

## 访问地址

| 服务 | 地址 | 账号密码 |
|------|------|---------|
| Flask 运维平台 | http://宿主机IP:5000 | 无 |
| Prometheus | http://宿主机IP:9090 | 无 |
| Grafana | http://宿主机IP:3000 | admin / admin123 |

> 在虚拟机中运行时，用 `ip addr show | grep "inet " | grep -v 127.0.0.1` 查看虚拟机 IP，不能用 localhost。

---

## 使用说明

### 部署 node_exporter 并配置 Grafana

1. 打开 Flask 平台 `:5000`，选 node_exporter / monitored，点执行
2. 等待执行历史显示 success（约 30 秒）
3. 打开 Prometheus `:9090/targets`，确认三个目标全部 UP
4. 打开 Grafana `:3000`，登录 admin / admin123
5. Connections → Data sources → Add → Prometheus，URL 填 `http://prometheus:9090` → Save & test
6. Dashboards → New → Import → ID 填 `1860` → Load → Import
7. 看到三个节点的实时监控面板

---

## 踩坑记录

### 坑1：Prometheus 启动报 "not a directory"

**现象**：`docker compose up` 时 Prometheus 容器启动失败，报 `mount src=.../prometheus.yml ... not a directory`。

**原因**：docker-compose.yml 里把 `prometheus.yml` 挂载到容器，但宿主机上该文件不存在。Docker 发现挂载路径不存在时，自动创建一个**目录**。而容器内对应路径期望是一个**文件**，目录挂到文件路径上就冲突了。

**解决**：先创建文件再启动容器。每次 `docker compose up` 之前确认 `prometheus/prometheus.yml` 存在。

---

### 坑2：node 容器 SSH 一直连不上（Connection refused）

**现象**：entrypoint.sh 循环检测 60 次，node1/2/3 SSH 始终 Connection refused，超时放弃。

**原因**：最初用官方 ubuntu 镜像，在 docker-compose.yml 的 command 里现装 openssh-server。安装过程需要 30~60 秒，远超 controller 等待时间。

**解决**：为 node 创建独立 Dockerfile，把 openssh-server 预装进镜像。容器启动时直接运行 sshd，秒级就绪。

---

### 坑3：Playbook 报 "not a valid attribute for a Play"

**现象**：执行 `ansible-playbook roles/node_exporter/tasks/main.yml` 报错 `'get_url' is not a valid attribute for a Play`。

**原因**：`ansible-playbook` 命令需要的是包含 `hosts:` 字段的完整 Playbook 文件。直接传 tasks 文件时，Ansible 把文件的第一个 task（`- name: 下载 node_exporter`）当成了 Play 的定义，把 `get_url` 当成 Play 的属性，报错。

**解决**：在 `playbooks/` 目录下创建入口文件，声明 `hosts: all` 并用 `import_tasks` 引入 tasks 文件。

---

### 坑4：systemd 在容器内不可用

**现象**：node_exporter Role 中执行 `systemd` 模块报错 `System has not been booted with systemd as init system (PID 1). Can't operate.`

**原因**：Docker 容器的 PID 1 是 sshd（或 entrypoint 脚本），不是 systemd。systemd 需要作为 init 进程（PID 1）运行才能正常工作，在容器里调用 systemctl 相当于没有 init 进程时调用 service manager，自然失败。

**解决**：用 `nohup` 后台启动代替 systemd。并用 pgrep 检查进程是否已运行，保证幂等性。

---

### 坑5：WebSocket 事件静默失败（日志框卡在"正在执行..."）

**现象**：前端点击执行按钮，日志框显示"正在执行..."后不再更新，执行历史显示 failed，但 `docker logs controller` 没有任何请求记录。

**原因**：使用 `async_mode='eventlet'` 时，eventlet 与当前环境的 Flask-SocketIO 版本存在兼容性问题。WebSocket 的 `on` 事件处理器被注册了但从未被调用，没有任何报错，非常难以排查。

**排查过程**：
1. 先看 docker logs，发现没有任何 Flask 请求日志
2. 说明请求根本没到达后端，排除 Ansible 问题
3. 怀疑 WebSocket 连接本身有问题
4. 改用 `async_mode='threading'` 后正常

**解决**：移除 eventlet 依赖，改用 `async_mode='threading'`，同时去掉 requirements.txt 中的 eventlet。

---

### 坑6：重建单个容器导致其他容器断开

**现象**：执行 `docker compose up -d --build controller` 后，Prometheus 和 Grafana 容器消失，`docker compose ps` 只剩4个容器。

**原因**：重建 controller 镜像时触发了网络重建（ops-net），网络重建会断开并重连所有容器。Prometheus 和 Grafana 原本在网络里，重建过程中被踢出，之后没有自动重连。

**解决**：每次重建都用 `docker compose down && docker compose up -d --build`，保证所有容器在同一次操作中重启，网络状态一致。

---

## 面试常问知识点

### Ansible 幂等性

幂等性（Idempotency）：同一操作执行多次与执行一次的结果相同。

Ansible 大多数内置模块都是幂等的，执行前会先查询目标状态：
- `apt` 模块：检查包是否已安装，已安装则跳过
- `user` 模块：检查用户是否存在，存在则跳过
- `copy` 模块：对比源文件和目标文件的 checksum，相同则跳过
- `lineinfile` 模块：检查目标行是否已存在，存在则跳过

本项目中的幂等性体现：
- node_exporter Role 用 `pgrep` 检测进程，已运行则跳过启动
- init Role 的所有 task 都使用幂等模块，反复执行不产生副作用

不幂等的情况：`shell`/`command` 模块执行的原始命令默认不幂等，需要配合 `creates`（文件存在则跳过）或 `when`（条件判断）手动实现幂等。

### SSH 免密登录原理

非对称加密认证流程：

1. controller 生成密钥对：公钥（id_rsa.pub）+ 私钥（id_rsa）
2. 把公钥内容追加到被管节点的 `~/.ssh/authorized_keys`
3. Ansible 连接时：
   - controller 用私钥对一段随机数据签名
   - 发送签名和原始数据给被管节点
   - 被管节点用 authorized_keys 里的公钥验证签名
   - 验证通过则允许登录，全程不涉及密码

为什么更安全：密码可以被暴力破解，私钥是 4096 位随机数，实际上无法被暴力破解。且私钥只在 controller 上，不在网络上传输。

### Docker 网络模式

本项目使用自定义 bridge 网络，与默认 bridge 网络的区别：

| 特性 | 默认 bridge | 自定义 bridge |
|------|------------|--------------|
| 容器名 DNS 解析 | 不支持 | 支持 |
| 容器间隔离 | 较弱 | 可通过网络控制 |
| 推荐程度 | 不推荐生产用 | 推荐 |

自定义网络中，容器名自动注册到 Docker 内置 DNS，其他容器可以直接用容器名访问，这是本项目 `node1:9100`、`prometheus:9090` 能正常解析的原因。

### Prometheus Pull 模型 vs Zabbix Push 模型

**Pull 模型（Prometheus）**：
- Prometheus 主动向 target 发 HTTP GET `/metrics`
- target 需要暴露 HTTP 端口
- 优点：Prometheus 知道 target 是否挂掉（拉不到数据就告警）
- 缺点：短生命周期任务（跑完就退出的批处理）来不及被拉取，需要 Pushgateway 中转

**Push 模型（Zabbix/StatsD）**：
- 被监控目标主动把数据推给监控服务器
- 优点：适合短生命周期任务、NAT 后面的机器
- 缺点：监控服务器无法主动感知 Agent 是否挂掉

### subprocess 进程管理

本项目用 `subprocess.Popen` 执行 ansible-playbook：

```python
proc = subprocess.Popen(
    cmd,
    stdout=subprocess.PIPE,   # 重定向 stdout 到管道
    stderr=subprocess.STDOUT, # 合并 stderr 到 stdout
    text=True,                # 文本模式（str）而不是 bytes
    bufsize=1,                # 行缓冲，每行立即可读
)

for line in iter(proc.stdout.readline, ''):
    emit('log', {'data': line})  # 实时推送每一行
```

`bufsize=1` 行缓冲的重要性：默认情况下管道是全缓冲（通常 4096 字节），意味着数据会在缓冲区积累到 4096 字节或进程结束时才能读取，无法实时推送。行缓冲模式下每行输出后立即可读。
