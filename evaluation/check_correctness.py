import os
import subprocess
import tempfile
from typing import Dict, List


def run_functional_check(
    candidate_code: str,
    tests: List[str],
    entry_point: str,
    timeout_seconds: int = 8,
) -> Dict[str, str]:
    """
    Execute canonical task tests against generated code in an isolated subprocess.
    """
    test_lines = "\n".join(tests)
    harness = f"""
{candidate_code}

if '{entry_point}' not in globals():
    raise NameError("Expected entry point '{entry_point}' was not defined")

{test_lines}
print('FUNCTIONAL_CHECK_OK')
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as temp_file:
        temp_file.write(harness)
        temp_path = temp_file.name

    try:
        result = subprocess.run(
            ["python", temp_path],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        if result.returncode == 0 and "FUNCTIONAL_CHECK_OK" in result.stdout:
            return {"passed": "true", "error": ""}
        return {
            "passed": "false",
            "error": (result.stderr or result.stdout or "Functional check failed").strip(),
        }
    except subprocess.TimeoutExpired:
        return {"passed": "false", "error": f"TimeoutError: functional check exceeded {timeout_seconds}s."}
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
