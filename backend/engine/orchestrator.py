from backend.engine import pipeline_actions as actions
from backend.engine import pipeline_data as data
from backend.engine.utils import sanitize_developer, sanitize_qa, _log
STEP_HANDLERS = {
    "developer": actions.run_developer,
    "sanitize_developer": sanitize_developer,
    "qa": actions.run_qa,
    "sanitize_qa": sanitize_qa,
    "sandbox": actions.run_sandbox,
    "reflection": actions.run_reflection,
    "tutor": actions.run_tutor,
}


def run_agentic_pipeline(problem_description: str, job_id: str):
    state = data.PipelineState(problem_description=problem_description, job_id=job_id)
    state = actions._start_new_attempt(state)

    while state.step not in {"completed", "failed"}:
        handler = STEP_HANDLERS[state.step]
        state = handler(state)

    return