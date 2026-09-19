"""服务端任务目录与输入白名单。"""

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class PlaybookDefinition:
    id: str
    name: str
    playbook: str
    description: str


PLAYBOOKS = {
    "init": PlaybookDefinition(
        id="init",
        name="初始化节点",
        playbook="init.yml",
        description="安装基础工具、创建运维用户并统一时区。",
    ),
    "node_exporter": PlaybookDefinition(
        id="node_exporter",
        name="部署 Node Exporter",
        playbook="node_exporter.yml",
        description="下载固定版本组件并通过 Supervisor 管理进程。",
    ),
}

TARGET_GROUPS = {
    "monitored": "全部三个实验节点",
    "webservers": "Web 节点 node1",
    "dbservers": "数据库节点 node2",
}

MODES = {
    "check": "预检，不改机器",
    "apply": "执行一次",
    "verify": "连跑两次，第二次 changed 必须为 0",
}

MODE_LABELS = {
    "check": "1. 预检",
    "apply": "2. 执行",
    "verify": "3. 验证幂等",
}


def public_catalog() -> dict[str, object]:
    """返回前端可选择但不能修改的任务目录。"""

    return {
        "playbooks": [asdict(item) for item in PLAYBOOKS.values()],
        "target_groups": [
            {"id": group_id, "name": name} for group_id, name in TARGET_GROUPS.items()
        ],
        "modes": [
            {
                "id": mode_id,
                "name": MODE_LABELS[mode_id],
                "description": description,
            }
            for mode_id, description in MODES.items()
        ],
    }
