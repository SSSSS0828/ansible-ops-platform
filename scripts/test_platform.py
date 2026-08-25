"""运行中的 Compose 平台端到端验收。"""

import json
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
    targets = json.loads(
        urlopen("http://127.0.0.1:9090/api/v1/targets", timeout=10).read()
    )
    node_targets = [
        item
        for item in targets["data"]["activeTargets"]
        if item["labels"].get("job") == "node_exporter"
    ]
    assert len(node_targets) == 3
    assert all(item["health"] == "up" for item in node_targets)
    wait_url("http://127.0.0.1:3000/api/health")
    print("platform passed: apply -> verify changed=0 -> 3 Prometheus targets up")


if __name__ == "__main__":
    main()
