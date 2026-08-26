#!/usr/bin/env python3
"""运行中的 Compose 平台端到端验收。"""

import base64
import json
import os
import time
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

BASE_URL = "http://127.0.0.1:5000"


def request_json(path: str, payload: dict[str, Any] | None = None) -> Any:
    body = json.dumps(payload).encode() if payload is not None else None
    request = Request(
        f"{BASE_URL}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST" if payload is not None else "GET",
    )
    with urlopen(request, timeout=15) as response:
        return json.load(response)


def wait_url(url: str, timeout_seconds: int = 180) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=3) as response:
                if response.status == 200:
                    return
        except (OSError, URLError, TimeoutError):
            time.sleep(2)
    raise RuntimeError(f"服务未在时限内就绪: {url}")


def wait_prometheus_targets(timeout_seconds: int = 90) -> list[dict[str, Any]]:
    """等待首次抓取完成，避免在 Prometheus ready 后立即读取到 unknown。"""

    deadline = time.monotonic() + timeout_seconds
    node_targets: list[dict[str, Any]] = []
    while time.monotonic() < deadline:
        with urlopen("http://127.0.0.1:9090/api/v1/targets", timeout=10) as response:
            targets = json.load(response)
        node_targets = [
            item
            for item in targets["data"]["activeTargets"]
            if item["labels"].get("job") == "node_exporter"
        ]
        if len(node_targets) == 3 and all(
            item["health"] == "up" for item in node_targets
        ):
            return node_targets
        time.sleep(2)
    raise RuntimeError(f"Prometheus targets 未全部恢复为 UP: {node_targets}")


def grafana_json(path: str) -> Any:
    """使用 CI 注入的管理员密码验收只读的自动配置结果。"""

    password = os.environ["GRAFANA_ADMIN_PASSWORD"]
    credentials = base64.b64encode(f"admin:{password}".encode()).decode()
    request = Request(
        f"http://127.0.0.1:3000{path}",
        headers={"Authorization": f"Basic {credentials}"},
    )
    with urlopen(request, timeout=10) as response:
        return json.load(response)


def wait_job(job_id: str, timeout_seconds: int = 300) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        job = request_json(f"/api/jobs/{job_id}")
        if job["status"] in {"succeeded", "failed"}:
            return job
        time.sleep(2)
    raise RuntimeError(f"任务未在时限内结束: {job_id}")


def submit(mode: str) -> dict[str, Any]:
    job = request_json(
        "/api/jobs",
        {"playbook_id": "node_exporter", "target_group": "monitored", "mode": mode},
    )
    completed = wait_job(job["id"])
    if completed["status"] != "succeeded":
        with urlopen(f"{BASE_URL}/api/jobs/{job['id']}/events", timeout=15) as response:
            print(response.read().decode("utf-8"))
    assert completed["status"] == "succeeded", completed
    return completed


def main() -> None:
    wait_url(f"{BASE_URL}/healthz")
    submit("apply")
    verified = submit("verify")
    assert verified["summary"]["idempotent"] is True
    assert (
        sum(
            host["changed"] for host in verified["summary"]["runs"][1]["recap"].values()
        )
        == 0
    )

    wait_url("http://127.0.0.1:9090/-/ready")
    wait_prometheus_targets()
    wait_url("http://127.0.0.1:3000/api/health")
    datasource = grafana_json("/api/datasources/name/Prometheus")
    dashboard = grafana_json("/api/dashboards/uid/ansible-managed-nodes")
    assert datasource["url"] == "http://prometheus:9090"
    assert dashboard["dashboard"]["title"] == "Ansible Managed Nodes"
    print(
        "platform passed: apply -> verify changed=0 -> 3 targets up -> Grafana provisioned"
    )


if __name__ == "__main__":
    main()
