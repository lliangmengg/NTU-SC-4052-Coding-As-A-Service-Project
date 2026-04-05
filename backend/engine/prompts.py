DEVELOPER_EXPECTED_OUTPUT = """
Return exactly two tagged sections in this order:

[CODE]
<executable Python solution>
[/CODE]
[SUMMARY]
<concise developer approach summary>
[/SUMMARY]

Rules:
- No markdown
- No code fences
""".strip()

QA_EXPECTED_OUTPUT = """
Return exactly two tagged sections in this order:

[TESTS]
<executable pytest tests>
[/TESTS]
[SUMMARY]
<concise QA test-strategy summary>
[/SUMMARY]

Requirements:
- Exactly 5 adversarial test cases
- Validate problem requirements, not implementation

Rules:
- No markdown
- No explanations
- No code fences
- Do NOT reimplement the solution
- Import from module `solution`
""".strip()

REFLECTION_EXPECTED_OUTPUT = """
Return a structured debugging analysis with exactly these sections:

1. Fault Location
2. Root Cause
3. Trigger Condition
4. Fix Strategy

Rules:
- Be specific and actionable
- No extra commentary
""".strip()

TUTOR_EXPECTED_OUTPUT = """
Return exactly two tagged sections in this order:

[EXPLANATION]
<clear explanation>
[/EXPLANATION]
[SUMMARY]
<short tutor summary>
[/SUMMARY]

Include:
1. High-level idea
2. Step-by-step logic
3. Time complexity
4. Space complexity
5. Key edge cases

Rules:
- Be concise and easy to understand
""".strip()

def select_expected_output(step: str, is_error_reflection: bool = False) -> str:
    """
    Select the correct CrewAI Task expected_output contract from pipeline state.

    For reflection steps triggered by sanitization/error handling, pass
    is_error_reflection=True to return an empty string as requested.
    """
    if step == "reflection":
        return "" if is_error_reflection else REFLECTION_EXPECTED_OUTPUT

    expected_output_by_step = {
        "developer": DEVELOPER_EXPECTED_OUTPUT,
        "qa": QA_EXPECTED_OUTPUT,
        "tutor": TUTOR_EXPECTED_OUTPUT,
    }

    return expected_output_by_step.get(step, "")

def developer_prompt(problem_description, previous_answer, error):
    history = ""

    for i, (code, err) in enumerate(zip(previous_answer, error), start=1):
        history += f"Attempt {i}:\n"
        history += f"Code:\n{code}\n"
        history += f"Error:\n{err}\n\n"

    return f"""
        Solve the following algorithmic problem.

        Problem:
        {problem_description}

        Your previous attempts and their errors:
        {history}

        Output format (strict):
        [CODE]
        <executable Python solution>
        [/CODE]
        [SUMMARY]
        <concise approach summary>
        [/SUMMARY]
        """

def qa_prompt(problem_description, developer_code_str):
    return f"""
        You are a QA agent writing pytest tests.

        Problem (ground truth):
        {problem_description}

        Developer code (for interface only):
        {developer_code_str}

        Output format (strict):
        [TESTS]
        <executable pytest tests>
        [/TESTS]
        [SUMMARY]
        <concise test strategy summary>
        [/SUMMARY]
    """

def algo_reflection_prompt(developer_code_str, qa_tests_str, result):
    return f"""
            
        Code: {developer_code_str}
        
        Tests: {qa_tests_str}

        Error: {result['error']}
        
        Analyze the error and return structured debugging analysis.
        """

def error_reflection_prompt(error_message):
    return f"""
        Error:
        {error_message}

            Analyze the error and explain.

    """

def tutor_prompt(problem_description, developer_code_str):
    return f"""
        You are a patient tutor explaining an algorithm solution.

        Problem:
        {problem_description}

        Solution:
        {developer_code_str}

        Explain the solution clearly for a student.

        Output format (strict):
        [EXPLANATION]
        <full explanation>
        [/EXPLANATION]
        [SUMMARY]
        <short tutor summary>
        [/SUMMARY]

    """