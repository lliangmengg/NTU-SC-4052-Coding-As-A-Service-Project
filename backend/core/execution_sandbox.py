import subprocess
import tempfile
import os
import sys
from typing import Dict, Any

def execute_code_safely(python_code: str, timeout_seconds: int = 5) -> Dict[str, Any]:
    """
    Executes a string of Python code in a secure, isolated subprocess.
    Captures standard output and standard error (tracebacks).
    """
    # 1. Create a temporary file that auto-deletes
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as temp_file:
        temp_file.write(python_code)
        temp_file_path = temp_file.name

    try:
        # 2. Execute the file via the operating system
        result = subprocess.run(
            ['python', temp_file_path],
            capture_output=True,
            text=True,
            timeout=timeout_seconds
        )
        
        # 3. Parse the results
        if result.returncode == 0:
            return {
                "success": True, 
                "output": result.stdout.strip(),
                "error": None
            }
        else:
            return {
                "success": False, 
                "output": result.stdout.strip(),
                "error": result.stderr.strip()
            }
            
    except subprocess.TimeoutExpired:
        # Catch infinite loops (e.g., bad graph traversals)
        return {
            "success": False, 
            "output": "",
            "error": f"TimeoutError: Code execution exceeded {timeout_seconds} seconds."
        }
    except Exception as e:
        # Catch unexpected OS-level errors
        return {
            "success": False,
            "output": "",
            "error": f"SystemError: {str(e)}"
        }
    finally:
        # 4. Mandatory cleanup: Ensure the temp file is deleted even if execution crashes
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)


def execute_tests_against_solution(
    solution_code: str,
    test_code: str,
    timeout_seconds: int = 8,
) -> Dict[str, Any]:
    """
    Executes QA pytest tests against a developer solution in isolated files.

    The developer code is written to solution.py, and QA tests are written to
    test_solution.py in a temporary directory. This preserves responsibility
    boundaries and prevents QA output from replacing developer code.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        solution_path = os.path.join(temp_dir, "solution.py")
        test_path = os.path.join(temp_dir, "test_solution.py")

        with open(solution_path, "w", encoding="utf-8") as solution_file:
            solution_file.write(solution_code)

        with open(test_path, "w", encoding="utf-8") as tests_file:
            tests_file.write(test_code)

        env = os.environ.copy()
        existing_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            temp_dir if not existing_pythonpath else f"{temp_dir}{os.pathsep}{existing_pythonpath}"
        )

        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", test_path],
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                cwd=temp_dir,
                env=env,
            )

            combined_output = "\n".join(
                part.strip() for part in [result.stdout, result.stderr] if part and part.strip()
            ).strip()

            if result.returncode == 0:
                return {
                    "success": True,
                    "output": combined_output,
                    "error": None,
                }

            return {
                "success": False,
                "output": result.stdout.strip(),
                "error": result.stderr.strip() or result.stdout.strip(),
            }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "output": "",
                "error": f"TimeoutError: Test execution exceeded {timeout_seconds} seconds.",
            }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": f"SystemError: {str(e)}",
            }