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
        name="服务器初始化",
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
    "check": "预检并展示 diff，不修改节点",
    "apply": "正常应用配置",
    "verify": "连续执行两次，第二次 changed=0 才通过",
}


def public_catalog() -> dict[str, object]:
    """返回前端可选择但不能修改的任务目录。"""

    return {
        "playbooks": [asdict(item) for item in PLAYBOOKS.values()],
        "target_groups": [
            {"id": group_id, "name": name} for group_id, name in TARGET_GROUPS.items()
        ],
        "modes": [{"id": mode_id, "name": name} for mode_id, name in MODES.items()],
    }
