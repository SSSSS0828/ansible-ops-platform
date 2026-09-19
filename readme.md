# ansible-ops-platform

用 Docker Compose 拉起三个实验节点，浏览器里点一下跑 Ansible。

需要 Linux 和 Docker Compose：

```bash
git clone https://github.com/SSSSS0828/ansible-ops-platform.git
cd ansible-ops-platform
cp .env.example .env
docker compose up --build -d
```

- 任务页 http://127.0.0.1:5000
- Prometheus http://127.0.0.1:9090
- Grafana http://127.0.0.1:3000

`.env` 里的密码只给这套环境用，别拿到真机器上。

页面上只能选仓库里登记过的 playbook，不能随便填命令。现在就两条：

- `init`：装 curl/vim，建 `ops` 用户，时区设成 Asia/Shanghai
- `node_exporter`：装固定版本的 Node Exporter，交给 Supervisor

模式三个：`check` 只预检，`apply` 跑一遍，`verify` 连跑两遍，第二遍 `changed` 必须是 0。目标组在 `controller/inventory/hosts.ini`，`monitored` 是三台一起打。

`ops` 用户密码在 `controller/inventory/group_vars/all/vault.yml`，用环境变量 `OPS_VAULT_PASSWORD` 解密。节点第一次配 SSH 还是 `.env` 里的 `OPS_BOOTSTRAP_PASSWORD`。

```bash
printf '%s' "$OPS_VAULT_PASSWORD" > /tmp/ops-vault-pass
ansible-vault view controller/inventory/group_vars/all/vault.yml --vault-password-file /tmp/ops-vault-pass
```

测代码：

```bash
python -m venv .venv
.venv/bin/pip install -r controller/requirements-dev.txt
.venv/bin/python -m ruff check controller scripts
.venv/bin/python -m pytest controller/tests
```

CI 还会 `compose up` 跑一遍 `apply` / `verify`，并看三个 Node Exporter 是否在 Prometheus 里是 UP。
