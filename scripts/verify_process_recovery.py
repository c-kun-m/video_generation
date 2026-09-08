"""Exercise real API/dispatcher/Activity crashes and Temporal persistence in isolated test data.

Requires the repository's local Docker Compose services. Stops only subprocesses it owns
and the two named Temporal containers created by this repository; never removes data volumes.
"""

import argparse
import json
import os
import subprocess
import sys
import time
import uuid

import httpx
from sqlalchemy.engine import make_url
from video_generation.config import REPO_ROOT, Settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--restart-temporal",
        action="store_true",
        help="Also restart the local Temporal server and its PostgreSQL container",
    )
    args = parser.parse_args()
    production = Settings()
    database = (
        make_url(production.database_url.get_secret_value())
        .set(database="video_generation_faults_test")
        .render_as_string(hide_password=False)
    )
    log_dir = REPO_ROOT / "runtime" / "verification" / "process-recovery"
    log_dir.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "VIDEO_DATABASE_URL": database,
        "VIDEO_API_PORT": "18002",
        "VIDEO_TEMPORAL_NAMESPACE": "video-process-tests",
        "VIDEO_TEMPORAL_TASK_QUEUE": "video-process-tests",
        "VIDEO_SIMULATION_STEP_SECONDS": "1",
        "VIDEO_TEST_FAULTS": "true",
        "PYTHONIOENCODING": "utf-8",
    }
    process_env = {
        "cwd": str(REPO_ROOT),
        "creationflags": subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    }
    prepare_env = {
        **env,
        "VIDEO_DATABASE_URL": production.database_url.get_secret_value(),
        "VIDEO_TEST_DATABASE_URL": database,
        "VIDEO_TEST_FAULTS": "false",
    }
    subprocess.run(
        [sys.executable, "scripts/prepare_test_db.py"],
        env=prepare_env,
        check=True,
        **process_env,
    )
    subprocess.run(
        [sys.executable, "-m", "video_generation", "init-temporal"],
        env=env,
        check=True,
        **process_env,
    )
    invitation = subprocess.run(
        [sys.executable, "-m", "video_generation", "init-owner", "--json"],
        env=env,
        capture_output=True,
        text=True,
        check=True,
        **process_env,
    )
    code = json.loads(invitation.stdout)["pairing_code"]
    processes = []

    def start(command, point=None, identity=None):
        child_env = {**env}
        child_env.pop("VIDEO_TEST_CRASH_POINT", None)
        child_env.pop("VIDEO_TEST_CRASH_ID", None)
        if point:
            child_env.update(VIDEO_TEST_CRASH_POINT=point, VIDEO_TEST_CRASH_ID=identity)
        with (log_dir / f"{command}.log").open("ab") as output:
            child = subprocess.Popen(
                [sys.executable, "-m", "video_generation", command],
                env=child_env,
                stdout=output,
                stderr=output,
                stdin=subprocess.DEVNULL,
                **process_env,
            )
        processes.append(child)
        return child

    def wait_for(predicate, description, seconds=45):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            try:
                value = predicate()
                if value:
                    return value
            except (httpx.TransportError, KeyError):
                pass
            time.sleep(0.15)
        raise AssertionError(f"Timed out waiting for {description}")

    def stop(child):
        if child.poll() is not None:
            return
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(child.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        else:
            child.kill()
        child.wait(timeout=10)

    def uid():
        return str(uuid.uuid4())

    report = {"suite": "b1-process-recovery", "cases": [], "verified_at": None}
    with httpx.Client(base_url="http://127.0.0.1:18002", timeout=10) as client:

        def post(path, body):
            response = client.post("/video/v1" + path, json=body)
            assert response.is_success, (
                f"{path}: {response.status_code} {response.text}"
            )
            return response.json()

        def get(path):
            response = client.get("/video/v1" + path)
            assert response.is_success, response.text
            return response.json()

        try:
            start_command = uid()
            api = start("serve", "api_after_commit", start_command)
            wait_for(
                lambda: client.get("/health/ready").status_code == 200, "API readiness"
            )
            pair = post(
                "/auth/pair",
                {"pairing_code": code, "device_name": "process-recovery-verifier"},
            )
            client.headers["Authorization"] = "Bearer " + pair["access_token"]
            project = post(
                "/projects", {"command_id": uid(), "title": "B1 进程崩溃验证"}
            )["project"]
            pid = project["project_id"]
            segment_id = uid()
            refs = {}
            brief = {
                "kind": "brief",
                "theme": "晨光",
                "audience": "居民",
                "purpose": "生活记录",
                "style": "写实",
            }
            for kind in ("brief", "script", "storyboard"):
                payload = (
                    brief
                    if kind == "brief"
                    else {
                        "kind": "script",
                        "brief_ref": refs["brief"],
                        "segments": [
                            {
                                "segment_id": segment_id,
                                "spoken_text": "城市醒来了。",
                                "visual_description": "阳光照进街道",
                            }
                        ],
                    }
                    if kind == "script"
                    else {
                        "kind": "storyboard",
                        "script_ref": refs["script"],
                        "shots": [
                            {
                                "shot_id": uid(),
                                "segment_ids": [segment_id],
                                "intent": "晨光街道",
                                "camera": "缓慢推进",
                                "duration_frames": 240,
                            }
                            for _ in range(3)
                        ],
                    }
                )
                refs[kind] = post(
                    f"/projects/{pid}/revisions",
                    {
                        "command_id": uid(),
                        "entity_kind": kind,
                        "expected_row_version": 0,
                        "payload": payload,
                    },
                )["business_result_ref"]
                post(
                    f"/projects/{pid}/approvals",
                    {
                        "command_id": uid(),
                        "subject_ref": refs[kind],
                        "expected_row_version": 1,
                        "decision": "APPROVED",
                    },
                )
            body = {
                "command_id": start_command,
                "execution_mode": "simulation",
                "expected_row_version": 1,
                "input_refs": refs,
            }
            try:
                client.post(f"/video/v1/projects/{pid}/production-runs", json=body)
            except httpx.TransportError:
                pass
            assert api.wait(timeout=15) == 91
            api = start("serve")
            wait_for(
                lambda: client.get("/health/ready").status_code == 200, "restarted API"
            )
            accepted = get(f"/commands/{start_command}")
            assert accepted["status"] == "ACCEPTED"
            run_id = accepted["business_result_ref"]["production_run_id"]
            assert (
                post(f"/projects/{pid}/production-runs", body)["business_result_ref"]
                == accepted["business_result_ref"]
            )
            assert len(get(f"/projects/{pid}/snapshot")["production_runs"]) == 1
            report["cases"].append(
                "API exited after DB commit before HTTP response; original command/run recovered"
            )
            print("PASS: API commit/response crash", flush=True)

            dispatcher = start("dispatcher", "outbox_after_send", run_id)
            assert dispatcher.wait(timeout=45) == 91
            detail = get(f"/production-runs/{run_id}")
            assert detail["deliveries"][0]["transport_status"] == "PENDING"
            shot_id = detail["snapshot"]["contents"][2]["payload"]["shots"][0][
                "shot_id"
            ]
            worker = start(
                "worker", "activity_after_commit", f"{run_id}/shot/{shot_id}"
            )
            assert worker.wait(timeout=45) == 91
            crashed = get(f"/production-runs/{run_id}")
            assert crashed["run"]["completed_shots"] == 1 and len(crashed["steps"]) == 1
            original_temporal_id = crashed["run"]["temporal_run_id"]
            post(
                f"/production-runs/{run_id}/commands",
                {"command_id": uid(), "action": "pause"},
            )
            print(
                "PASS: Outbox send/ack and Activity commit/result crashes", flush=True
            )

            if args.restart_temporal:
                compose = [
                    "docker",
                    "compose",
                    "--env-file",
                    ".env",
                    "-f",
                    "deploy/video/compose.yaml",
                ]
                with (log_dir / "temporal-restart.log").open("ab") as output:
                    for command in (
                        [*compose, "stop", "temporal"],
                        [*compose, "restart", "temporal-postgres"],
                        [*compose, "up", "-d", "--wait", "temporal"],
                    ):
                        subprocess.run(
                            command,
                            stdout=output,
                            stderr=output,
                            check=True,
                            timeout=60,
                            **process_env,
                        )
                report["cases"].append(
                    "Temporal Server and its PostgreSQL container restarted with volumes retained"
                )
                print("PASS: Temporal/PostgreSQL container restart", flush=True)

            dispatcher = start("dispatcher")
            worker = start("worker")
            paused = wait_for(
                lambda: (
                    d
                    if (d := get(f"/production-runs/{run_id}"))["run"]["status"]
                    == "PAUSED"
                    else None
                ),
                "recovered paused workflow",
                60,
            )
            assert paused["run"]["completed_shots"] == 1
            assert paused["run"]["temporal_run_id"] == original_temporal_id
            post(
                f"/production-runs/{run_id}/commands",
                {"command_id": uid(), "action": "resume"},
            )
            final = wait_for(
                lambda: (
                    d
                    if (d := get(f"/production-runs/{run_id}"))["run"]["status"]
                    == "COMPLETED"
                    else None
                ),
                "completed recovered workflow",
                60,
            )
            assert final["run"]["temporal_run_id"] == original_temporal_id
            assert final["run"]["snapshot_id"] == crashed["run"]["snapshot_id"]
            assert (
                len(final["steps"]) == 4
                and len({s["operation_id"] for s in final["steps"]}) == 4
            )
            wait_for(
                lambda: all(
                    d["transport_status"] == "SENT" and d["consumed"]
                    for d in get(f"/production-runs/{run_id}")["deliveries"]
                ),
                "outbox retry and business receipts",
                60,
            )
            report["cases"].extend(
                [
                    "Dispatcher exited after send before delivery ACK; lease expiry re-delivered same workflow",
                    "Worker exited after step DB commit before Activity response; retry kept one step result",
                    "Paused workflow resumed with original Temporal run id, snapshot and four unique final results",
                ]
            )
            report.update(
                project_id=pid,
                production_run_id=run_id,
                temporal_run_id=original_temporal_id,
                snapshot_id=final["run"]["snapshot_id"],
                verified_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            )
            (log_dir / "result.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(
                "PASS: all process recovery scenarios; evidence runtime/verification/process-recovery/result.json",
                flush=True,
            )
        finally:
            for child in reversed(processes):
                stop(child)


if __name__ == "__main__":
    main()
