import os
from crewai import Agent, LLM
from dotenv import load_dotenv

load_dotenv()

# Initialize Gemini 2.5 Flash
gemini_flash = LLM(
    model="gemini/gemini-2.5-flash",
    api_key=os.environ.get("GEMINI_API_KEY"),
    temperature=0.2 # Lower temperature for stable coding
)

# 1. The Developer: Writes the algorithm
developer_agent = Agent(
    role="Senior Algorithmic Engineer",
    goal="Write the most efficient Python solution for: {algorithmic_problem}",
    backstory="Expert in Data Structures and Algorithms. You write clean, optimized, and bug-free Python code.",
    llm=gemini_flash,
    allow_delegation=False,
    verbose=True
)

# 2. The QA Engineer: Writes the tests
qa_agent = Agent(
    role="Software Test Engineer",
    goal="Create a comprehensive suite of PyTest unit tests for the code provided by the Developer.",
    backstory="You are obsessed with edge cases—null inputs, large datasets, and boundary conditions.",
    llm=gemini_flash,
    allow_delegation=False,
    verbose=True
)

# 3. The Reflection Agent: Analyzes failures
reflection_agent = Agent(
    role="Code Critic & Architect",
    goal="Analyze the Python traceback error and provide a specific strategy to fix the bug.",
    backstory="You don't write code; you find the 'Why' behind the failure. You provide high-level logical corrections.",
    llm=gemini_flash,
    allow_delegation=False,
    verbose=True
)

# 4. The Tutor: Explains the final success
tutor_agent = Agent(
    role="Computer Science Professor",
    goal="Explain the successful solution, its Time/Space complexity, and the logic used.",
    backstory="You make complex concepts easy to understand for junior developers.",
    llm=gemini_flash,
    allow_delegation=False,
    verbose=True
)