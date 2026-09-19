# Ansible 任务实验：面试讲解

## 一分钟介绍

这是一个本机 Ansible 实验，不是运维平台。页面只能提交服务端白名单里的 Playbook、目标组和模式。后台用 Ansible Runner 执行，结构化事件写入 SQLite，页面用中文显示进度。

仓库里只有两个 Role：`init` 和 `node_exporter`。`check` 只预检，`apply` 执行一次，`verify` 连跑两次，第二次 `changed` 必须为 0。运维用户密码放在 Ansible Vault 里。执行完可以在 Prometheus / Grafana 看三个节点。

## 演示顺序

1. 打开任务页，说明只能选目录里的两项任务，不能提交任意命令。
2. `check`：预检，不改机器。
3. `apply`：部署 Node Exporter，看主机和任务进度。
4. `verify`：自动跑两轮，第二轮 `changed=0`。
5. 打开 Prometheus / Grafana，确认三个节点被采集。
6. 重建 controller，历史任务还在 SQLite 数据卷里。

## 三个技术点

### 为什么用 Ansible Runner

读子进程 stdout 只能拿到终端文本。Runner 回调能稳定拿到主机、任务名和 changed，方便落库和展示。

### 为什么用 SSE

日志是服务端单向推送。SSE 比 WebSocket 简单，还带事件 ID 和断线续读。关掉页面不会停掉 Ansible。

### 怎样验证幂等

`verify` 连续执行两次同一 Playbook。第一轮允许有变更，第二轮 recap 的 `changed` 合计必须为 0，否则任务失败并保留两次结果。

### Vault 管什么

只加密 `vault_ops_password`，给 `init` 里的 `ops` 用户设密码。节点首次 SSH 仍用 `.env` 的引导密码，不放进保险库。

## 常见追问

**为什么不用 Celery？** 这是单机实验，线程池和 SQLite 够演示。生产要队列和分布式锁。

**容器节点为什么不用 systemd？** 实验容器 PID 1 是 Supervisor，同时管 sshd 和 Node Exporter。真实机器应改用 systemd。

**如何防止命令注入？** API 只接受目录中的 Playbook ID、Inventory 组和固定模式。

**项目不足是什么？** 没有登录、RBAC、队列和多控制节点；Role 也只有两条。定位是可重复的本机实验。
