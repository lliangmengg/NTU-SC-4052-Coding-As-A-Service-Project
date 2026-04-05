import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List

import requests
import streamlit as st
from dotenv import load_dotenv


load_dotenv()

BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000/api/v1/tutor")
DATASET_PATH = Path(__file__).resolve().parents[1] / "evaluation" / "dataset.json"
POLL_INTERVAL_SECONDS = 2
PANEL_HEIGHT = 1080
LEDGER_HEIGHT = 420
TUTOR_HEIGHT = 960


def load_predefined_tasks() -> List[Dict[str, Any]]:
	if not DATASET_PATH.exists():
		return []
	with open(DATASET_PATH, "r", encoding="utf-8") as f:
		data = json.load(f)
	return data.get("tasks", [])


def submit_job(problem_description: str) -> Dict[str, Any]:
	response = requests.post(
		f"{BASE_URL}/solve",
		json={"problem_description": problem_description},
		timeout=20,
	)
	response.raise_for_status()
	return response.json()


def fetch_status(job_id: str) -> Dict[str, Any]:
	response = requests.get(f"{BASE_URL}/status/{job_id}", timeout=20)
	response.raise_for_status()
	return response.json()


def run_playground_tests(solution_code: str, test_code: str, timeout_seconds: int = 10) -> Dict[str, Any]:
	response = requests.post(
		f"{BASE_URL}/run-tests",
		json={
			"solution_code": solution_code,
			"test_code": test_code,
			"timeout_seconds": timeout_seconds,
		},
		timeout=60,
	)
	response.raise_for_status()
	return response.json()


def build_timeline(status: Dict[str, Any]) -> List[Dict[str, str]]:
	artifacts = status.get("artifacts", {}) or {}
	sandbox = artifacts.get("sandbox", {})

	timeline = [
		{
			"stage": "Planner",
			"summary": artifacts.get("planner", {}).get("summary", "Awaiting planner context..."),
		},
		{
			"stage": "Developer",
			"summary": artifacts.get("developer", {}).get("summary", "Generating implementation..."),
		},
		{
			"stage": "QA",
			"summary": artifacts.get("qa", {}).get("summary", "Designing adversarial tests..."),
		},
		{
			"stage": "Sandbox",
			"summary": (
				"Tests passed."
				if sandbox.get("success") is True
				else "Tests failed, waiting for reflection."
				if sandbox.get("success") is False
				else "Running tests in isolated sandbox..."
			),
		},
		{
			"stage": "Tutor",
			"summary": artifacts.get("tutor", {}).get("summary", "Awaiting explanation..."),
		},
	]

	return timeline


def infer_active_stage(status: Dict[str, Any]) -> str:
	if not status:
		return ""

	if status.get("status") == "COMPLETED":
		return ""

	step = str(status.get("current_step", "")).lower()
	if "developer" in step:
		return "Developer"
	if "qa" in step:
		return "QA"
	if "sandbox" in step or "reflect" in step:
		return "Sandbox"
	if "tutor" in step:
		return "Tutor"
	return "Planner"


def stage_icon(stage_index: int, active_index: int, is_completed: bool) -> str:
	if is_completed:
		return "✅"
	if stage_index == active_index:
		return "⏳"
	return "⚪"


def render_requirement_anchor(task: Dict[str, Any], custom_problem: str):
	st.sidebar.header("Requirement Anchor")
	if custom_problem.strip():
		statement = custom_problem.strip()
		constraints = ["Return valid Python solution semantics.", "Handle edge cases."]
		examples = ["Custom prompt mode: no predefined examples."]
	else:
		statement = task.get("problem_description", "No problem selected.")
		constraints = task.get(
			"constraints",
			[
				"Follow exact function signature expected by tests.",
				"Handle edge cases and invalid boundaries where applicable.",
				"Prefer clear and efficient Python implementation.",
			],
		)
		examples = task.get("tests", [])

	st.sidebar.subheader("Problem Statement")
	st.sidebar.markdown(statement)

	st.sidebar.subheader("Constraints")
	st.sidebar.markdown("\n".join(f"- {item}" for item in constraints))

	st.sidebar.subheader("Input / Output Examples")
	st.sidebar.code("\n".join(examples) if examples else "No examples available.", language="python")


def initialize_session_state():
	defaults = {
		"job_id": None,
		"status": None,
		"logs_cursor": 0,
		"problem_description": "",
		"last_error": "",
		"playground_code": "",
		"playground_job_id": None,
		"playground_result": None,
	}
	for key, value in defaults.items():
		if key not in st.session_state:
			st.session_state[key] = value


def main():
	st.set_page_config(page_title="Agentic IDE Workbench", layout="wide")
	initialize_session_state()

	st.title("Agentic IDE Workbench")
	st.caption("Live Ledger for Planner -> Developer -> QA -> Sandbox -> Tutor")

	tasks = load_predefined_tasks()
	task_labels = [f"{t.get('task_id', 'task')}: {t.get('problem_description', '')[:60]}..." for t in tasks]

	selected_index = st.sidebar.selectbox(
		"Choose predefined question",
		options=list(range(len(task_labels))) if task_labels else [0],
		format_func=(lambda i: task_labels[i]) if task_labels else (lambda _: "No dataset tasks found"),
	)
	selected_task = tasks[selected_index] if tasks else {}

	custom_problem = st.sidebar.text_area("Or enter a custom question", value="", height=140)
	render_requirement_anchor(selected_task, custom_problem)

	if st.sidebar.button("Run Pipeline", type="primary", use_container_width=True):
		st.session_state.logs_cursor = 0
		st.session_state.last_error = ""
		st.session_state.problem_description = custom_problem.strip() or selected_task.get("problem_description", "")

		if not st.session_state.problem_description:
			st.session_state.last_error = "No problem statement provided."
		else:
			try:
				submitted = submit_job(st.session_state.problem_description)
				st.session_state.job_id = submitted.get("job_id")
			except requests.RequestException as exc:
				st.session_state.last_error = f"Failed to submit job: {exc}"

	if st.session_state.last_error:
		st.error(st.session_state.last_error)

	if st.session_state.job_id:
		try:
			st.session_state.status = fetch_status(st.session_state.job_id)
		except requests.RequestException as exc:
			st.error(f"Failed to fetch status: {exc}")

	left, right = st.columns([1.1, 1.6], gap="small")

	with left:
		st.subheader("Orchestration Stream")
		left_panel = st.container(height=PANEL_HEIGHT, border=True)

		with left_panel:
			if not st.session_state.status:
				st.info("Awaiting run...")
			else:
				current = st.session_state.status.get("current_step", "")
				st.markdown(f"**Current Step:** {current}")
				st.markdown(
					f"**Attempt:** {st.session_state.status.get('current_attempt', 0)} / {st.session_state.status.get('max_retries', 0)}"
				)

				timeline = build_timeline(st.session_state.status)
				active_stage = infer_active_stage(st.session_state.status)
				active_index = next((i for i, t in enumerate(timeline) if t["stage"] == active_stage), 0)

				for i, item in enumerate(timeline):
					is_completed = st.session_state.status.get("status") == "COMPLETED" or i < active_index
					icon = stage_icon(i, active_index, is_completed)
					st.markdown(f"### {icon} {item['stage']}")
					st.write(item["summary"])

	with right:
		st.subheader("Deliverable Workspace")
		right_panel = st.container(height=PANEL_HEIGHT, border=True)
		with right_panel:
			solution_tab, playground_tab, tests_tab, tutor_tab = st.tabs(
				["Developer Solution", "Code Playground", "Test Results", "Tutor / Explanation"]
			)

			artifacts = (st.session_state.status or {}).get("artifacts", {}) or {}
			developer_artifact = artifacts.get("developer", {})
			qa_artifact = artifacts.get("qa", {})
			sandbox_artifact = artifacts.get("sandbox", {})
			tutor_artifact = artifacts.get("tutor", {})
			developer_code = (st.session_state.status or {}).get("code") or developer_artifact.get("sanitized_code")

			if developer_code and st.session_state.get("playground_job_id") != st.session_state.get("job_id"):
				st.session_state.playground_code = developer_code
				st.session_state.playground_job_id = st.session_state.get("job_id")
				st.session_state.playground_result = None

			with solution_tab:
				code_box = st.container(height=610, border=True)
				with code_box:
					if developer_code:
						st.code(developer_code, language="python")
					else:
						st.info("Awaiting Code...")

			with playground_tab:
				st.caption("Editable playground. Default template is the latest developer solution.")
				playground_box = st.container(height=520, border=True)
				with playground_box:
					st.text_area(
						"Playground Code",
						key="playground_code",
						height=470,
					)

				tests = qa_artifact.get("sanitized_tests")
				button_cols = st.columns([1, 1, 2])
				with button_cols[0]:
					run_clicked = st.button("Run Against QA Tests", use_container_width=True)
				with button_cols[1]:
					if st.button("Reset to Developer Code", use_container_width=True):
						if developer_code:
							st.session_state.playground_code = developer_code
							st.session_state.playground_result = None
							st.rerun()

				if run_clicked:
					if not tests:
						st.warning("QA tests are not available yet. Wait for QA stage completion.")
					elif not st.session_state.playground_code.strip():
						st.warning("Playground code is empty.")
					else:
						try:
							st.session_state.playground_result = run_playground_tests(
								solution_code=st.session_state.playground_code,
								test_code=tests,
							)
						except requests.RequestException as exc:
							st.session_state.playground_result = {
								"success": False,
								"output": "",
								"error": f"Playground run failed: {exc}",
							}

				if st.session_state.playground_result:
					result = st.session_state.playground_result
					if result.get("success"):
						st.success("Playground Result: PASS")
					else:
						st.error("Playground Result: FAIL")
					st.json(result)

			with tests_tab:
				tests_box = st.container(height=420, border=True)
				with tests_box:
					tests = qa_artifact.get("sanitized_tests")
					if tests:
						st.code(tests, language="python")
					else:
						st.info("Awaiting QA tests...")

				if sandbox_artifact:
					if sandbox_artifact.get("success"):
						st.success("Sandbox: PASS")
					else:
						st.error("Sandbox: FAIL")

					result = sandbox_artifact.get("result")
					if result:
						st.json(result)

			with tutor_tab:
				tutor_box = st.container(height=TUTOR_HEIGHT, border=True)
				with tutor_box:
					explanation = (st.session_state.status or {}).get("explanation") or tutor_artifact.get("explanation")
					if explanation:
						st.markdown(explanation)
					else:
						st.info("Awaiting Tutor explanation...")

	st.markdown("---")
	with st.expander("Event Ledger", expanded=False):
		logs = (st.session_state.status or {}).get("logs", []) or []
		ledger_box = st.container(height=LEDGER_HEIGHT, border=True)
		with ledger_box:
			if logs:
				st.code("\n".join(logs[-50:]))
			else:
				st.caption("No logs yet.")

	if st.session_state.status and st.session_state.status.get("status") == "PROCESSING":
		time.sleep(POLL_INTERVAL_SECONDS)
		st.rerun()


if __name__ == "__main__":
	main()
