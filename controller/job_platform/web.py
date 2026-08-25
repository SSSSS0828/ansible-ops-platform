"""Flask REST、SSE 和页面入口。"""

import json
import os
import time
from collections.abc import Iterator

from flask import Flask, Response, jsonify, render_template, request, stream_with_context

from job_platform.catalog import MODES, PLAYBOOKS, TARGET_GROUPS, public_catalog
from job_platform.repository import TERMINAL_STATUSES, JobRepository
from job_platform.runner import AnsibleRunnerAdapter
from job_platform.service import JobService, RunnerPort, TargetBusyError


def create_app(
    *,
    database_path: str | None = None,
    runner: RunnerPort | None = None,
) -> Flask:
    app = Flask(__name__, template_folder="../templates")
    repository = JobRepository(database_path or os.getenv("OPS_DB_PATH", "/data/jobs.db"))
    selected_runner = runner or AnsibleRunnerAdapter(
        private_data_dir=os.getenv("OPS_RUNNER_DATA", "/data/runner"),
        project_dir=os.getenv("OPS_PLAYBOOK_DIR", "/app/playbooks"),
        inventory=os.getenv("OPS_INVENTORY", "/app/inventory/hosts.ini"),
    )
    service = JobService(repository, selected_runner)
    app.extensions["job_repository"] = repository
    app.extensions["job_service"] = service

    @app.get("/")
    def index() -> str:
        return render_template("index.html")

    @app.get("/healthz")
    def healthz() -> tuple[dict[str, str], int]:
        return {"status": "ok", "service": "ansible-job-platform"}, 200

    @app.get("/api/catalog")
    def catalog() -> Response:
        return jsonify(public_catalog())

    @app.post("/api/jobs")
    def create_job() -> tuple[Response, int] | Response:
        payload = request.get_json(silent=True) or {}
        playbook_id = payload.get("playbook_id")
        target_group = payload.get("target_group")
        mode = payload.get("mode")
        errors = []
        if playbook_id not in PLAYBOOKS:
            errors.append("playbook_id 不在允许目录中")
        if target_group not in TARGET_GROUPS:
            errors.append("target_group 不在 inventory 白名单中")
        if mode not in MODES:
            errors.append("mode 只允许 check、apply 或 verify")
        if errors:
            return jsonify({"error": "; ".join(errors)}), 400
        try:
            job = service.submit(playbook_id, target_group, mode)
        except TargetBusyError as error:
            return jsonify({"error": str(error), "active_job_id": error.job_id}), 409
        return jsonify(job), 202

    @app.get("/api/jobs")
    def list_jobs() -> Response:
        return jsonify(repository.list_jobs())

    @app.get("/api/jobs/<job_id>")
    def get_job(job_id: str) -> tuple[Response, int] | Response:
        job = repository.get_job(job_id)
        return jsonify(job) if job else (jsonify({"error": "任务不存在"}), 404)

    @app.get("/api/jobs/<job_id>/events")
    def stream_events(job_id: str) -> tuple[Response, int] | Response:
        if repository.get_job(job_id) is None:
            return jsonify({"error": "任务不存在"}), 404
        header_sequence = request.headers.get("Last-Event-ID", "0")
        query_sequence = request.args.get("after", header_sequence)
        try:
            after = max(int(query_sequence), 0)
        except ValueError:
            return jsonify({"error": "after 必须是非负整数"}), 400

        @stream_with_context
        def generate() -> Iterator[str]:
            cursor = after
            while True:
                events = repository.list_events(job_id, cursor)
                for event in events:
                    cursor = event["sequence"]
                    yield (
                        f"id: {cursor}\n"
                        f"event: {event['event_type']}\n"
                        f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    )
                job = repository.get_job(job_id)
                if job and job["status"] in TERMINAL_STATUSES and not events:
                    break
                if not events:
                    yield ": keep-alive\n\n"
                time.sleep(0.4)

        response = Response(generate(), mimetype="text/event-stream")
        response.headers["Cache-Control"] = "no-cache"
        response.headers["X-Accel-Buffering"] = "no"
        return response

    return app
