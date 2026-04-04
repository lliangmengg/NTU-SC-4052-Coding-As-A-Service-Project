from backend.core.execution_sandbox import execute_code_safely, execute_tests_against_solution

def test_valid_code_execution():
    """Test that valid python code returns the correct output and success status."""
    code = "print(1 + 1)"
    result = execute_code_safely(code)
    
    assert result["success"] is True
    assert result["output"] == "2"
    assert result["error"] is None

def test_syntax_error_handling():
    """Test that code with errors returns success=False and captures the traceback."""
    # Intentional ZeroDivisionError
    code = "print(10 / 0)"
    result = execute_code_safely(code)
    
    assert result["success"] is False
    assert "ZeroDivisionError" in result["error"]
    assert result["output"] == ""

def test_infinite_loop_timeout():
    """Test that code exceeding the timeout is terminated and returns a TimeoutError."""
    code = "while True: pass"
    # Setting a short 1-second timeout for the test
    result = execute_code_safely(code, timeout_seconds=1)
    
    assert result["success"] is False
    assert "TimeoutError" in result["error"]
    assert "exceeded 1 seconds" in result["error"]

def test_complex_algorithm_output():
    """Test a real data structure solution to ensure output formatting is preserved."""
    code = """
def bubble_sort(arr):
    for i in range(len(arr)):
        for j in range(0, len(arr) - i - 1):
            if arr[j] > arr[j+1]:
                arr[j], arr[j+1] = arr[j+1], arr[j]
    return arr

print(bubble_sort([3, 1, 2]))
    """
    result = execute_code_safely(code)
    
    assert result["success"] is True
    assert result["output"] == "[1, 2, 3]"


def test_execute_tests_against_solution_success():
    solution_code = """
def add(a, b):
    return a + b
"""
    test_code = """
from solution import add


def test_add_basic():
    assert add(1, 2) == 3


def test_add_negative():
    assert add(-1, 1) == 0
"""

    result = execute_tests_against_solution(solution_code, test_code)

    assert result["success"] is True
    assert result["error"] is None


def test_execute_tests_against_solution_failure():
    solution_code = """
def add(a, b):
    return a - b
"""
    test_code = """
from solution import add


def test_add_basic():
    assert add(1, 2) == 3
"""

    result = execute_tests_against_solution(solution_code, test_code)

    assert result["success"] is False
    assert "AssertionError" in result["error"] or "FAILED" in result["error"]