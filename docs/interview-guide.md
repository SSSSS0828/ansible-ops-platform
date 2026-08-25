# Ansible Ops Platform 面试讲解指南

## 一分钟介绍

这个项目用于管理多个 Linux 节点上的 Ansible 任务。前端提交的是服务端白名单中的 Playbook、目标组和运行模式，后台创建独立任务并使用 Ansible Runner 执行。Runner 的结构化事件会写入 SQLite，页面通过 SSE 实时展示。除了普通执行，我增加了 check 预检和 verify 幂等验证；verify 会自动连续执行两次，第二次 changed 必须为零。执行完成后，Prometheus 和 Grafana 可以看到三个节点的状态。

## 演示顺序

1. 展示任务目录，说明客户端不能提交任意 Playbook 路径。
2. 使用 check 模式查看可能发生的变更。
3. 使用 apply 模式部署 Node Exporter，展示主机级事件和 recap。
4. 使用 verify 模式自动运行两次，展示第二次 changed=0。
5. 打开 Prometheus 和 Grafana，确认三个节点均被监控。
6. 重建 controller，展示历史任务仍在 SQLite 数据卷中。

## 三个技术点

### 为什么使用 Ansible Runner

直接读取子进程 stdout 只能得到终端文本，难以稳定提取主机、任务和结果。Runner 会通过回调提供结构化事件，平台可以持久化并展示失败主机、任务名和 changed 状态。

### 为什么使用 SSE

执行日志是服务端单向推送，SSE 比 WebSocket 更简单，并原生支持事件 ID 和断线续读。任务本身独立于浏览器连接，关闭页面不会中止 Ansible。

### 如何验证幂等性

verify 模式连续执行两次同一 Playbook。第一次允许发生变更，第二次 recap 的 changed 合计必须等于零，否则任务标记失败并保存两次结果。

## 常见追问

**为什么不用 Celery？**  当前是单机作品项目，线程池和 SQLite 更容易部署和演示。生产环境会将任务投递到队列，并使用分布式锁保护目标资源。

**SQLite 并发安全吗？**  每次操作使用独立连接并启用 WAL，适合当前少量后台任务；高并发场景应迁移 PostgreSQL。

**为什么容器节点不用 systemd？**  实验容器 PID 1 使用 Supervisor，同时管理 sshd 和 Node Exporter。真实服务器上会改用 systemd Role。

**如何防止命令注入？**  API 只接受目录中登记的 Playbook ID、Inventory 组和固定模式，不把用户输入拼接为任意 Shell 命令。

**项目的不足是什么？**  当前没有登录、RBAC、分布式队列和多控制节点，定位是可重复的本地自动化运维实验平台。
