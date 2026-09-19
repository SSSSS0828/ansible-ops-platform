"""Ansible Runner 适配器，将回调事件转换为平台稳定结构。"""

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

EventCallback = Callable[..., dict[str, Any]]


@dataclass(frozen=True, slots=True)
class RunnerResult:
    return_code: int
    recap: dict[str, dict[str, int]]


class AnsibleRunnerAdapter:
    """使用官方事件回调而不是解析彩色终端文本。"""

    def __init__(
        self,
        *,
        private_data_dir: str,
        project_dir: str,
        inventory: str,
    ) -> None:
        self._private_data_dir = Path(private_data_dir)
        self._private_data_dir.mkdir(parents=True, exist_ok=True)
        self._project_dir = project_dir
        self._inventory = inventory

    def run(
        self,
        *,
        job_id: str,
        phase: str,
        playbook: str,
        target_group: str,
        check: bool,
        on_event: EventCallback,
    ) -> RunnerResult:
        # ansible-runner 依赖 POSIX fcntl，仅在真正执行任务时延迟导入；
        # 这样 Windows 开发机仍能使用伪 Runner 测试 REST、SSE 和持久化逻辑。
        import ansible_runner

        recap: dict[str, dict[str, int]] = {}

        def handle_event(event: dict[str, Any]) -> bool:
            nonlocal recap
            event_type = str(event.get("event", "runner_event"))
            event_data = event.get("event_data") or {}
            if event_type == "playbook_on_stats":
                recap = _build_recap(event_data)
            result = event_data.get("res") or {}
            on_event(
                event_type=event_type,
                host=str(event_data.get("host", "")),
                task=str(event_data.get("task", "")),
                status=_event_status(event_type),
                changed=bool(result.get("changed", False)),
                stdout=str(event.get("stdout", "")),
            )
            return True

        cmdline = f"--limit {target_group}"
        if check:
            cmdline += " --check --diff"
        result = ansible_runner.run(
            private_data_dir=str(self._private_data_dir),
            project_dir=self._project_dir,
            inventory=self._inventory,
            playbook=playbook,
            ident=f"{job_id}-{phase}",
            cmdline=cmdline,
            event_handler=handle_event,
            envvars=_runner_env(),
            quiet=True,
            rotate_artifacts=20,
        )
        return RunnerResult(return_code=int(result.rc or 0), recap=recap)


def _runner_env() -> dict[str, str]:
    env = {"ANSIBLE_HOST_KEY_CHECKING": "False"}
    vault_file = os.getenv("ANSIBLE_VAULT_PASSWORD_FILE")
    if vault_file:
        env["ANSIBLE_VAULT_PASSWORD_FILE"] = vault_file
    return env


def _event_status(event_type: str) -> str:
    return {
        "runner_on_ok": "ok",
        "runner_on_failed": "failed",
        "runner_on_unreachable": "unreachable",
        "runner_on_skipped": "skipped",
        "playbook_on_stats": "recap",
    }.get(event_type, "info")


def _build_recap(event_data: dict[str, Any]) -> dict[str, dict[str, int]]:
    keys = ("ok", "changed", "failures", "dark", "skipped", "rescued", "ignored")
    hosts = set(event_data.get("processed", {}))
    for key in keys:
        hosts.update((event_data.get(key) or {}).keys())
    return {
        host: {key: int((event_data.get(key) or {}).get(host, 0)) for key in keys}
        for host in sorted(hosts)
    }
