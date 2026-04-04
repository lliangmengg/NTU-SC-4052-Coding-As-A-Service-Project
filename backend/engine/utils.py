import ast
import re
from backend.engine.pipeline_data import PipelineState, AGENT_TIMEOUT_SECONDS
from backend.engine.prompts import error_reflection_prompt
from backend.core import state_manager
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from crewai import Crew

def _log(job_id: str, message: str):
    # Keep logs visible in server output and retrievable via job status.
    print(message, flush=True)
    state_manager.append_log(job_id, message)


def _log_agent_exchange(job_id: str, attempt: int, agent_name: str, prompt: str, response: str):
    divider = "=" * 72
    _log(job_id, f"\n{divider}")
    _log(job_id, f"[ATTEMPT {attempt}] AGENT: {agent_name}")
    _log(job_id, "[PROMPT]")
    _log(job_id, prompt)
    _log(job_id, "[RESPONSE]")
    _log(job_id, response)
    _log(job_id, divider)


def _run_crew_with_timeout(job_id: str, attempt: int, stage: str, crew: Crew, timeout_seconds: int = AGENT_TIMEOUT_SECONDS) -> str:
    _log(job_id, f"[ATTEMPT {attempt}] Running {stage} (timeout={timeout_seconds}s)")
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(crew.kickoff)
        try:
            result = future.result(timeout=timeout_seconds)
            return str(result)
        except FuturesTimeoutError as exc:
            future.cancel()
            raise TimeoutError(f"{stage} timed out after {timeout_seconds} seconds.") from exc

def _update_job(job_id: str, status: str, step: str, **kwargs):
    state_manager.update_job(job_id, status, step=step, **kwargs)


def _sanitize_python_output(raw_text: str) -> str:
    """Extract executable Python from LLM output and validate syntax."""
    raw = (raw_text or "").replace("\ufeff", "").strip()
    if not raw:
        raise ValueError("SanitizationError: Empty model response.")

    candidates = []

    # Prefer fenced code blocks when present.
    fenced_blocks = re.findall(r"```(?:python|py)?\s*(.*?)```", raw, flags=re.IGNORECASE | re.DOTALL)
    for block in fenced_blocks:
        candidate = block.strip()
        if candidate:
            candidates.append(candidate)

    # Fallback: remove fence marker lines if model returned malformed markdown.
    if not candidates and "```" in raw:
        lines = [line for line in raw.splitlines() if not line.strip().startswith("```")]
        stripped = "\n".join(lines).strip()
        if stripped:
            candidates.append(stripped)

    if not candidates:
        candidates.append(raw)

    syntax_errors = []
    for candidate in candidates:
        try:
            ast.parse(candidate)
            return candidate
        except SyntaxError as exc:
            syntax_errors.append(str(exc))

    raise ValueError(
        "SanitizationError: No syntactically valid Python could be extracted from model output. "
        f"Parse errors: {syntax_errors[:2]}"
    )

def sanitize_developer(state: PipelineState) -> PipelineState:
    try:
        state.developer_code = _sanitize_python_output(state.developer_code_raw or "")
        if state.developer_code != state.developer_code_raw:
            _log(state.job_id, "[SANITIZED] Developer output cleaned before QA handoff.")

        _update_job(
            state.job_id,
            "PROCESSING",
            f"Attempt {state.attempt}: QA generating tests..."
        )
        state.step = "qa"
        return state

    except ValueError as exc:
        _append_failure_history(state, state.developer_code_raw or "", str(exc))
        state.reflection_input = error_reflection_prompt(
            f"Developer output is not executable Python: {str(exc)}"
        )
        _update_job(
            state.job_id,
            "PROCESSING",
            f"Attempt {state.attempt} failed. Reflecting..."
        )
        state.step = "reflection"
        return state

def sanitize_qa(state: PipelineState) -> PipelineState:
    try:
        state.qa_tests = _sanitize_python_output(state.qa_tests_raw or "")
        if state.qa_tests != state.qa_tests_raw:
            _log(state.job_id, "[SANITIZED] QA output cleaned before sandbox execution.")

        _update_job(
            state.job_id,
            "PROCESSING",
            f"Attempt {state.attempt}: Running isolated sandbox..."
        )
        state.step = "sandbox"
        return state

    except ValueError as exc:
        _append_failure_history(state, state.developer_code or "", str(exc))
        state.reflection_input = error_reflection_prompt(
            f"QA output is not executable Python: {str(exc)}"
        )
        _update_job(
            state.job_id,
            "PROCESSING",
            f"Attempt {state.attempt} failed. Reflecting..."
        )
        state.step = "reflection"
        return state
    

def _append_failure_history(state: PipelineState, code: str, error: str):
    state.previous_answers.append(code)
    state.previous_errors.append(error)

