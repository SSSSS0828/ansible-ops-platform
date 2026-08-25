"""任务提交、并发保护和幂等验证应用服务。"""

from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from typing import Any, Protocol
from uuid import uuid4

from job_platform.catalog import PLAYBOOKS
from job_platform.repository import JobRepository, utc_now
from job_platform.runner import RunnerResult


class RunnerPort(Protocol):
    def run(self, **kwargs: Any) -> RunnerResult: ...


class TargetBusyError(RuntimeError):
    def __init__(self, job_id: str) -> None:
        super().__init__(f"目标组已有运行任务: {job_id}")
        self.job_id = job_id


class JobService:
    """单进程演示版任务调度器；跨进程调度明确不在当前范围。"""

    def __init__(self, repository: JobRepository, runner: RunnerPort) -> None:
        self._repository = repository
        self._runner = runner
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ansible-job")
        self._submit_lock = Lock()

    def submit(self, playbook_id: str, target_group: str, mode: str) -> dict[str, Any]:
        with self._submit_lock:
            active = self._repository.find_active_job(target_group)
            if active is not None:
                raise TargetBusyError(active["id"])
            job = {
                "id": f"job_{uuid4().hex}",
                "playbook_id": playbook_id,
                "target_group": target_group,
                "mode": mode,
                "status": "queued",
                "created_at": utc_now(),
            }
            self._repository.create_job(job)
            self._repository.add_event(
                job["id"], event_type="job_queued", status="queued", stdout="任务已进入队列"
            )
            self._executor.submit(self._execute, job)
            return self._repository.get_job(job["id"]) or job

    def _execute(self, job: dict[str, Any]) -> None:
        job_id = job["id"]
        self._repository.mark_running(job_id)
        self._repository.add_event(
            job_id, event_type="job_started", status="running", stdout="开始执行任务"
        )
        definition = PLAYBOOKS[job["playbook_id"]]
        phases = ["check"] if job["mode"] == "check" else ["apply"]
        if job["mode"] == "verify":
            phases = ["verify-first", "verify-second"]
        runs: list[dict[str, Any]] = []
        try:
            for phase in phases:
                self._repository.add_event(
                    job_id,
                    event_type="phase_started",
                    status="running",
                    stdout=f"阶段 {phase} 开始",
                )
                result = self._runner.run(
                    job_id=job_id,
                    phase=phase,
                    playbook=definition.playbook,
                    target_group=job["target_group"],
                    check=job["mode"] == "check",
                    on_event=lambda **event: self._repository.add_event(job_id, **event),
                )
                runs.append(
                    {
                        "phase": phase,
                        "return_code": result.return_code,
                        "recap": result.recap,
                    }
                )
                if result.return_code != 0:
                    self._finish(job_id, False, result.return_code, runs, "Ansible 执行失败")
                    return
            idempotent = None
            if job["mode"] == "verify":
                idempotent = _changed_total(runs[-1]["recap"]) == 0
            succeeded = idempotent is not False
            error = "" if succeeded else "第二次执行仍有 changed，幂等验证失败"
            self._finish(job_id, succeeded, 0 if succeeded else 2, runs, error, idempotent)
        except Exception as error:  # noqa: BLE001 - 后台任务必须落库失败原因
            self._finish(job_id, False, 1, runs, str(error))

    def _finish(
        self,
        job_id: str,
        succeeded: bool,
        return_code: int,
        runs: list[dict[str, Any]],
        error: str,
        idempotent: bool | None = None,
    ) -> None:
        status = "succeeded" if succeeded else "failed"
        summary = {"runs": runs, "idempotent": idempotent}
        self._repository.finish_job(
            job_id,
            status=status,
            return_code=return_code,
            summary=summary,
            error=error,
        )
        self._repository.add_event(
            job_id,
            event_type="job_done",
            status=status,
            stdout="任务执行成功" if succeeded else error,
        )


def _changed_total(recap: dict[str, dict[str, int]]) -> int:
    return sum(stats.get("changed", 0) for stats in recap.values())
