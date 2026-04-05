import ast
import re
from backend.engine.pipeline_data import PipelineState, AGENT_TIMEOUT_SECONDS
from backend.engine.prompts import error_reflection_prompt
from backend.core import state_manager
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from crewai import Crew


def _extract_tagged_block(text: str, tag: str) -> str:
    pattern = rf"\[{re.escape(tag)}\]\s*(.*?)\s*\[/{re.escape(tag)}\]"
    match = re.search(pattern, text or "", flags=re.DOTALL | re.IGNORECASE)
    return (match.group(1).strip() if match else "")


def extract_structured_output(raw_text: str, primary_tag: str) -> dict:
    """
    Extract a dual-part tagged response. Returns fallback values if parsing fails.
    """
    primary = _extract_tagged_block(raw_text or "", primary_tag)
    summary = _extract_tagged_block(raw_text or "", "SUMMARY")

    if primary:
        return {
            "primary": primary,
            "summary": summary,
            "used_structured": True,
        }

    # Backward-compatible fallback: treat entire output as primary content.
    return {
        "primary": raw_text or "",
        "summary": "",
        "used_structured": False,
    }

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
        extracted = extract_structured_output(state.developer_code_raw or "", "CODE")
        state.developer_code = _sanitize_python_output(extracted["primary"])
        state.developer_summary = extracted["summary"]
        if state.developer_code != state.developer_code_raw:
            _log(state.job_id, "[SANITIZED] Developer output cleaned before QA handoff.")
        if not extracted["used_structured"]:
            _log(state.job_id, "[PARSE_FALLBACK] Developer response missing [CODE]/[SUMMARY] tags.")

        _update_job(
            state.job_id,
            "PROCESSING",
            f"Attempt {state.attempt}: QA generating tests...",
            current_attempt=state.attempt,
            max_retries=state.max_retries,
            artifacts={
                "developer": {
                    "attempt": state.attempt,
                    "sanitized_code": state.developer_code,
                    "summary": state.developer_summary,
                    "structured_format": extracted["used_structured"],
                }
            },
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
        extracted = extract_structured_output(state.qa_tests_raw or "", "TESTS")
        state.qa_tests = _sanitize_python_output(extracted["primary"])
        state.qa_summary = extracted["summary"]
        if state.qa_tests != state.qa_tests_raw:
            _log(state.job_id, "[SANITIZED] QA output cleaned before sandbox execution.")
        if not extracted["used_structured"]:
            _log(state.job_id, "[PARSE_FALLBACK] QA response missing [TESTS]/[SUMMARY] tags.")

        _update_job(
            state.job_id,
            "PROCESSING",
            f"Attempt {state.attempt}: Running isolated sandbox...",
            current_attempt=state.attempt,
            max_retries=state.max_retries,
            artifacts={
                "qa": {
                    "attempt": state.attempt,
                    "sanitized_tests": state.qa_tests,
                    "summary": state.qa_summary,
                    "structured_format": extracted["used_structured"],
                }
            },
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

