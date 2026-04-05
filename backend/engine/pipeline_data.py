from dataclasses import dataclass, field
from typing import Literal, Optional

AGENT_TIMEOUT_SECONDS = 120
MAX_RETRIES = 3


Step = Literal[
    "developer",
    "sanitize_developer",
    "qa",
    "sanitize_qa",
    "sandbox",
    "reflection",
    "tutor",
    "completed",
    "failed",
]


@dataclass
class PipelineState:
    problem_description: str
    job_id: str
    attempt: int = 0
    max_retries: int = MAX_RETRIES
    step: Step = "developer"

    previous_answers: list[str] = field(default_factory=list)
    previous_errors: list[str] = field(default_factory=list)

    developer_code_raw: Optional[str] = None
    developer_code: Optional[str] = None
    developer_summary: Optional[str] = None

    qa_tests_raw: Optional[str] = None
    qa_tests: Optional[str] = None
    qa_summary: Optional[str] = None

    sandbox_result: Optional[dict] = None
    explanation: Optional[str] = None
    tutor_summary: Optional[str] = None
    artifacts: dict = field(default_factory=dict)

    reflection_input: Optional[str] = None
    reflection_output: Optional[str] = None
