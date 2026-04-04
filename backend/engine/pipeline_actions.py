from backend.engine.prompts import (
    developer_prompt,
    qa_prompt,
    algo_reflection_prompt,
    tutor_prompt,
    select_expected_output,
)
from backend.engine.pipeline_data import PipelineState, MAX_RETRIES
from crewai import Crew, Task
from backend.engine.utils import _log, _log_agent_exchange, _run_crew_with_timeout, _append_failure_history, _update_job
from backend.engine.agents import developer_agent, qa_agent, reflection_agent, tutor_agent
from backend.core.execution_sandbox import execute_tests_against_solution



def _run_agent_step(
    job_id: str,
    attempt: int,
    stage_name: str,
    agent,
    prompt: str,
    is_error_reflection: bool = False,
) -> str:
    state_key_by_stage = {
        "Developer Agent": "developer",
        "QA Agent": "qa",
        "Reflection Agent": "reflection",
        "Tutor Agent": "tutor",
    }
    task = Task(
        description=prompt,
        agent=agent,
        expected_output=select_expected_output(
            state_key_by_stage.get(stage_name, ""),
            is_error_reflection=is_error_reflection,
        ),
    )
    crew = Crew(agents=[agent], tasks=[task], verbose=True)
    return _run_crew_with_timeout(job_id, attempt, stage_name, crew)

def _fail_pipeline(state: PipelineState, reason: str) -> PipelineState:
    _update_job(state.job_id, "FAILED", reason)
    _log(state.job_id, f"[FATAL] {reason}")
    state.step = "failed"
    return state


def _start_new_attempt(state: PipelineState) -> PipelineState:
    state.attempt += 1
    if state.attempt > MAX_RETRIES:
        return _fail_pipeline(state, "Max retries reached. Solution unstable.")

    _update_job(
        state.job_id,
        "PROCESSING",
        f"Attempt {state.attempt}: Developer generating code..."
    )
    state.step = "developer"
    return state

def run_developer(state: PipelineState) -> PipelineState:
    dev_prompt = developer_prompt(
        state.problem_description,
        state.previous_answers,
        state.previous_errors,
    )

    try:
        state.developer_code_raw = _run_agent_step(
            state.job_id,
            state.attempt,
            "Developer Agent",
            developer_agent,
            dev_prompt,
        )
    except TimeoutError as exc:
        return _fail_pipeline(state, f"Attempt {state.attempt} failed: {str(exc)}")

    _log_agent_exchange(
        state.job_id,
        state.attempt,
        "Developer Agent",
        dev_prompt,
        state.developer_code_raw,
    )

    _update_job(
        state.job_id,
        "PROCESSING",
        f"Attempt {state.attempt}: Sanitizing developer output..."
    )
    state.step = "sanitize_developer"
    return state

def run_qa(state: PipelineState) -> PipelineState:

    prompt = qa_prompt(state.problem_description, state.developer_code or "")
    try:
        state.qa_tests_raw = _run_agent_step(
            state.job_id,
            state.attempt,
            "QA Agent",
            qa_agent,
            prompt,
        )
    except TimeoutError as exc:
        return _fail_pipeline(state, f"Attempt {state.attempt} failed: {str(exc)}")

    _log_agent_exchange(
        state.job_id,
        state.attempt,
        "QA Agent",
        prompt,
        state.qa_tests_raw,
    )

    _update_job(
        state.job_id,
        "PROCESSING",
        f"Attempt {state.attempt}: Sanitizing QA output..."
    )
    state.step = "sanitize_qa"
    return state

def run_sandbox(state: PipelineState) -> PipelineState:
    state.sandbox_result = execute_tests_against_solution(
        state.developer_code or "",
        state.qa_tests or "",
    )

    _log(
        state.job_id,
        f"[ATTEMPT {state.attempt}] SANDBOX RESULT "
        f"success={state.sandbox_result['success']} "
        f"error={state.sandbox_result['error']}"
    )

    if state.sandbox_result["success"]:
        _update_job(state.job_id, "PROCESSING", "Success! Tutoring...")
        state.step = "tutor"
        return state

    _append_failure_history(
        state,
        state.developer_code or "",
        state.sandbox_result.get("error") or "Unknown failure",
    )
    state.reflection_input = algo_reflection_prompt(
        state.developer_code or "",
        state.qa_tests or "",
        state.sandbox_result,
    )
    _update_job(
        state.job_id,
        "PROCESSING",
        f"Attempt {state.attempt} failed. Reflecting..."
    )
    state.step = "reflection"
    return state


def run_reflection(state: PipelineState) -> PipelineState:
    try:
        state.reflection_output = _run_agent_step(
            state.job_id,
            state.attempt,
            "Reflection Agent",
            reflection_agent,
            state.reflection_input or "",
            is_error_reflection=(state.sandbox_result is None),
        )
    except TimeoutError as exc:
        return _fail_pipeline(state, f"Attempt {state.attempt} failed: {str(exc)}")

    _log_agent_exchange(
        state.job_id,
        state.attempt,
        "Reflection Agent",
        state.reflection_input or "",
        state.reflection_output,
    )

    # Optional: replace raw error with structured reflection for next attempt memory
    if state.previous_errors:
        state.previous_errors[-1] = state.reflection_output

    if state.attempt >= MAX_RETRIES:
        return _fail_pipeline(state, "Max retries reached. Solution unstable.")

    _update_job(
        state.job_id,
        "PROCESSING",
        f"Attempt {state.attempt + 1}: Coding & Testing..."
    )
    state.step = "developer"
    state.attempt += 1
    return state


def run_tutor(state: PipelineState) -> PipelineState:
    prompt = tutor_prompt(
        state.problem_description,
        state.developer_code or "",
    )

    try:
        state.explanation = _run_agent_step(
            state.job_id,
            state.attempt,
            "Tutor Agent",
            tutor_agent,
            prompt,
        )
    except TimeoutError as exc:
        return _fail_pipeline(state, f"Attempt {state.attempt} failed: {str(exc)}")

    _log_agent_exchange(
        state.job_id,
        state.attempt,
        "Tutor Agent",
        prompt,
        state.explanation,
    )

    _update_job(
        state.job_id,
        "COMPLETED",
        "Completed successfully.",
        code=state.developer_code,
        explanation=state.explanation,
    )
    state.step = "completed"
    return state


