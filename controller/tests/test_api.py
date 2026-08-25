import time
from pathlib import Path
from threading import Event
from typing import Any

from job_platform.runner import RunnerResult
from job_platform.web import create_app


class FakeRunner:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def run(self, **kwargs: Any) -> RunnerResult:
        self.calls.append(kwargs)
        changed = 0 if kwargs["phase"] in {"check", "verify-second"} else 1
        kwargs["on_event"](
            event_type="runner_on_ok",
            host="node1",
            task="配置服务",
            status="ok",
            changed=bool(changed),
            stdout="ok: [node1]",
        )
        return RunnerResult(
            return_code=0,
            recap={
                "node1": {
                    "ok": 1,
                    "changed": changed,
                    "failures": 0,
                    "dark": 0,
                    "skipped": 0,
                    "rescued": 0,
                    "ignored": 0,
                }
            },
        )


class SlowRunner(FakeRunner):
    def __init__(self) -> None:
        super().__init__()
        self.started = Event()
        self.release = Event()

    def run(self, **kwargs: Any) -> RunnerResult:
        self.started.set()
        assert self.release.wait(timeout=5)
        return super().run(**kwargs)


class NonIdempotentRunner(FakeRunner):
    def run(self, **kwargs: Any) -> RunnerResult:
        result = super().run(**kwargs)
        recap = {host: {**stats, "changed": 1} for host, stats in result.recap.items()}
        return RunnerResult(return_code=0, recap=recap)


def wait_for_terminal(client: Any, job_id: str) -> dict[str, Any]:
    for _ in range(100):
        job = client.get(f"/api/jobs/{job_id}").get_json()
        if job["status"] in {"succeeded", "failed"}:
            return job
        time.sleep(0.02)
    raise AssertionError("任务未在测试时限内结束")


def test_catalog_and_input_whitelist(tmp_path: Path) -> None:
    app = create_app(database_path=str(tmp_path / "jobs.db"), runner=FakeRunner())
    client = app.test_client()

    catalog = client.get("/api/catalog")
    assert catalog.status_code == 200
    assert {item["id"] for item in catalog.get_json()["modes"]} == {
        "check",
        "apply",
        "verify",
    }
    rejected = client.post(
        "/api/jobs",
        json={"playbook_id": "../../shell", "target_group": "all", "mode": "apply"},
    )
    assert rejected.status_code == 400


def test_verify_runs_twice_and_requires_second_changed_zero(tmp_path: Path) -> None:
    runner = FakeRunner()
    app = create_app(database_path=str(tmp_path / "jobs.db"), runner=runner)
    client = app.test_client()

    response = client.post(
        "/api/jobs",
        json={"playbook_id": "node_exporter", "target_group": "monitored", "mode": "verify"},
    )
    assert response.status_code == 202
    job = wait_for_terminal(client, response.get_json()["id"])

    assert job["status"] == "succeeded"
    assert job["summary"]["idempotent"] is True
    assert [call["phase"] for call in runner.calls] == ["verify-first", "verify-second"]
    assert job["summary"]["runs"][1]["recap"]["node1"]["changed"] == 0


def test_check_mode_and_sse_event_replay(tmp_path: Path) -> None:
    runner = FakeRunner()
    app = create_app(database_path=str(tmp_path / "jobs.db"), runner=runner)
    client = app.test_client()
    response = client.post(
        "/api/jobs",
        json={"playbook_id": "init", "target_group": "webservers", "mode": "check"},
    )
    job_id = response.get_json()["id"]
    wait_for_terminal(client, job_id)

    events = client.get(f"/api/jobs/{job_id}/events?after=0").get_data(as_text=True)
    assert "event: job_queued" in events
    assert "event: runner_on_ok" in events
    assert "event: job_done" in events
    assert runner.calls[0]["check"] is True


def test_verify_fails_when_second_run_still_changes_nodes(tmp_path: Path) -> None:
    app = create_app(database_path=str(tmp_path / "jobs.db"), runner=NonIdempotentRunner())
    client = app.test_client()
    response = client.post(
        "/api/jobs",
        json={"playbook_id": "init", "target_group": "webservers", "mode": "verify"},
    )
    job = wait_for_terminal(client, response.get_json()["id"])

    assert job["status"] == "failed"
    assert job["summary"]["idempotent"] is False
    assert "幂等验证失败" in job["error"]


def test_same_target_group_rejects_concurrent_job(tmp_path: Path) -> None:
    runner = SlowRunner()
    app = create_app(database_path=str(tmp_path / "jobs.db"), runner=runner)
    client = app.test_client()
    payload = {"playbook_id": "init", "target_group": "monitored", "mode": "apply"}

    first = client.post("/api/jobs", json=payload)
    assert runner.started.wait(timeout=2)
    second = client.post("/api/jobs", json=payload)
    assert second.status_code == 409
    assert second.get_json()["active_job_id"] == first.get_json()["id"]
    runner.release.set()
    wait_for_terminal(client, first.get_json()["id"])


def test_history_survives_app_recreation(tmp_path: Path) -> None:
    database = tmp_path / "jobs.db"
    first_app = create_app(database_path=str(database), runner=FakeRunner())
    first_client = first_app.test_client()
    response = first_client.post(
        "/api/jobs",
        json={"playbook_id": "init", "target_group": "dbservers", "mode": "apply"},
    )
    wait_for_terminal(first_client, response.get_json()["id"])

    second_app = create_app(database_path=str(database), runner=FakeRunner())
    jobs = second_app.test_client().get("/api/jobs").get_json()
    assert jobs[0]["id"] == response.get_json()["id"]
    assert jobs[0]["status"] == "succeeded"
