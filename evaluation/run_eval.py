import argparse
import json
import os
import time
from typing import Dict, List

import requests

try:
    from evaluation.check_correctness import run_functional_check
    from evaluation.passk import aggregate_pass_at_k
except ModuleNotFoundError:
    from check_correctness import run_functional_check
    from passk import aggregate_pass_at_k


def load_dataset(path: str) -> List[Dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)["tasks"]


def submit_and_poll(base_url: str, problem_description: str, poll_interval: int, poll_timeout: int) -> Dict:
    started_at = time.time()
    submit = requests.post(
        f"{base_url}/solve",
        json={"problem_description": problem_description},
        timeout=20,
    )
    submit.raise_for_status()
    payload = submit.json()
    job_id = payload["job_id"]
    last_body = {}
    last_state = "UNKNOWN"
    last_step = "UNKNOWN"
    last_log_count = 0

    while time.time() - started_at < poll_timeout:
        status = requests.get(f"{base_url}/status/{job_id}", timeout=20)
        status.raise_for_status()
        body = status.json()
        state = body.get("status", "UNKNOWN")
        last_body = body
        last_state = state
        last_step = body.get("current_step", "UNKNOWN")
        logs = body.get("logs", [])
        last_log_count = len(logs) if isinstance(logs, list) else 0
        if state in {"COMPLETED", "FAILED"}:
            return {
                "job_id": job_id,
                "status": state,
                "latency_seconds": round(time.time() - started_at, 3),
                "payload": body,
            }
        time.sleep(poll_interval)

    print(
        f"[EVAL][TIMEOUT] job_id={job_id} exceeded {poll_timeout}s | last_state={last_state} | last_step={last_step} | last_logs={last_log_count}",
        flush=True,
    )

    return {
        "job_id": job_id,
        "status": "TIMEOUT",
        "latency_seconds": round(time.time() - started_at, 3),
        "payload": {
            "last_state": last_state,
            "last_step": last_step,
            "last_log_count": last_log_count,
            "last_payload": last_body,
        },
    }


def classify_error(status: str, payload: Dict, functional_error: str) -> str:
    if status == "TIMEOUT":
        return "queue_or_pipeline_timeout"
    if status == "FAILED":
        return "pipeline_failed"
    if functional_error:
        return "functional_incorrect"
    return ""


def run_evaluation(
    dataset_path: str,
    base_url: str,
    attempts_per_task: int,
    k_values: List[int],
    poll_interval: int,
    poll_timeout: int,
    max_runtime: int,
    max_tasks: int,
) -> Dict:
    tasks = load_dataset(dataset_path)
    if max_tasks > 0:
        tasks = tasks[:max_tasks]

    results = []
    eval_started_at = time.time()

    for task_index, task in enumerate(tasks, start=1):
        if time.time() - eval_started_at > max_runtime:
            print(f"[EVAL] Max runtime reached ({max_runtime}s). Stopping early.", flush=True)
            break

        print(
            f"[EVAL] Task {task_index}/{len(tasks)}: {task['task_id']} | attempts={attempts_per_task}",
            flush=True,
        )
        task_attempts = []
        for attempt_idx in range(attempts_per_task):
            if time.time() - eval_started_at > max_runtime:
                print(f"[EVAL] Max runtime reached ({max_runtime}s) during attempts. Stopping early.", flush=True)
                break

            print(
                f"[EVAL]   Attempt {attempt_idx + 1}/{attempts_per_task} submitting...",
                flush=True,
            )
            run = submit_and_poll(base_url, task["problem_description"], poll_interval, poll_timeout)
            payload = run["payload"]
            generated_code = payload.get("code") if payload else None

            functional = {"passed": "false", "error": ""}
            if run["status"] == "COMPLETED" and generated_code:
                functional = run_functional_check(
                    candidate_code=generated_code,
                    tests=task["tests"],
                    entry_point=task["entry_point"],
                )

            record = {
                "task_id": task["task_id"],
                "attempt": attempt_idx + 1,
                "job_id": run["job_id"],
                "status": run["status"],
                "latency_seconds": run["latency_seconds"],
                "generated_code": generated_code,
                "explanation": payload.get("explanation") if payload else None,
                "functional_pass": functional["passed"] == "true",
                "error_type": classify_error(run["status"], payload, functional["error"]),
                "error_message": functional["error"],
            }
            task_attempts.append(record)
            results.append(record)
            print(
                f"[EVAL]   Attempt {attempt_idx + 1}/{attempts_per_task} done | status={record['status']} | functional_pass={record['functional_pass']}",
                flush=True,
            )

        completed_and_correct = sum(
            1 for x in task_attempts if x["status"] == "COMPLETED" and x["functional_pass"]
        )
        task["correct_count"] = completed_and_correct
        print(
            f"[EVAL] Task {task['task_id']} summary | correct={completed_and_correct}/{len(task_attempts)}",
            flush=True,
        )

        if len(task_attempts) < attempts_per_task:
            break

    passk = {
        f"pass@{k}": aggregate_pass_at_k([t["correct_count"] for t in tasks], n=attempts_per_task, k=k)
        for k in k_values
    }

    functional_pass_rate = 0.0
    if results:
        functional_pass_rate = sum(1 for x in results if x["functional_pass"]) / len(results)

    summary = {
        "task_count": len(tasks),
        "attempts_per_task": attempts_per_task,
        "total_attempts": len(results),
        "max_runtime_seconds": max_runtime,
        "elapsed_seconds": round(time.time() - eval_started_at, 3),
        "functional_pass_rate": functional_pass_rate,
        "passk": passk,
        "failure_breakdown": {
            "pipeline_failed": sum(1 for x in results if x["error_type"] == "pipeline_failed"),
            "timeout": sum(1 for x in results if x["error_type"] == "queue_or_pipeline_timeout"),
            "functional_incorrect": sum(1 for x in results if x["error_type"] == "functional_incorrect"),
        },
    }

    return {"results": results, "summary": summary}


def write_outputs(output_dir: str, report: Dict):
    os.makedirs(output_dir, exist_ok=True)

    results_path = os.path.join(output_dir, "results.json")
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    summary = report["summary"]
    md_path = os.path.join(output_dir, "summary.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# Evaluation Summary\n\n")
        f.write(f"- Task count: {summary['task_count']}\n")
        f.write(f"- Attempts per task: {summary['attempts_per_task']}\n")
        f.write(f"- Total attempts: {summary['total_attempts']}\n")
        f.write(f"- Functional pass rate: {summary['functional_pass_rate']:.4f}\n")
        for key, value in summary["passk"].items():
            f.write(f"- {key}: {value:.4f}\n")
        f.write("\n## Failure Breakdown\n")
        for key, value in summary["failure_breakdown"].items():
            f.write(f"- {key}: {value}\n")


def main():
    parser = argparse.ArgumentParser(description="Run standalone API-driven evaluation.")
    parser.add_argument("--dataset", default="evaluation/dataset.json")
    parser.add_argument("--base-url", default=os.getenv("BASE_URL", "http://127.0.0.1:8000/api/v1/tutor"))
    parser.add_argument("--attempts", type=int, default=5)
    parser.add_argument("--k", default="1,3")
    parser.add_argument("--poll-interval", type=int, default=2)
    parser.add_argument("--poll-timeout", type=int, default=180)
    parser.add_argument("--max-runtime", type=int, default=900)
    parser.add_argument("--max-tasks", type=int, default=0, help="0 means all tasks")
    parser.add_argument("--output-dir", default="evaluation")
    args = parser.parse_args()

    k_values = [int(x.strip()) for x in args.k.split(",") if x.strip()]

    report = run_evaluation(
        dataset_path=args.dataset,
        base_url=args.base_url,
        attempts_per_task=args.attempts,
        k_values=k_values,
        poll_interval=args.poll_interval,
        poll_timeout=args.poll_timeout,
        max_runtime=args.max_runtime,
        max_tasks=args.max_tasks,
    )
    write_outputs(args.output_dir, report)
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
