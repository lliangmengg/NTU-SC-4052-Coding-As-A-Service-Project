# AlgoTutor CaaS - AI Coding Assistant Blueprint

## 1. Project Context & Objectives
**Project:** AlgoTutor CaaS (Coding-as-a-Service)
**Academic Context:** NTU Cloud Computing Project (Topic 7). Deadline: April 17th.
**Goal:** Build an agentic software factory that generates, safely executes, evaluates, and explains algorithmic code (Data Structures & Algorithms). 
**Grading Priority:** The system MUST be quantitatively evaluated using the **Pass@k** metric against the HumanEval dataset (or a classic LeetCode subset). Subjective evaluation is not acceptable.

## 2. Tech Stack (Strict)
* **Backend / API Gateway:** `FastAPI` (Asynchronous), `Uvicorn`
* **AI Orchestration:** `CrewAI`
* **Execution Sandbox:** Native Python `subprocess` (No external sandbox APIs)
* **Frontend / UI:** `Streamlit`
* **Testing/Evaluation:** `pytest`, `HumanEval` dataset
* **LLM Provider:** `Gemini 2.5 Flash` (Configured in CrewAI using `model="gemini/gemini-2.5-flash"` and the `GEMINI_API_KEY` environment variable).

## 3. System Architecture
The application follows a strictly decoupled microservice architecture:

1.  **The API Gateway (FastAPI - Port 8000):** Receives code generation requests. Instantly returns a `job_id` (HTTP 202) and processes the CrewAI loop in a FastAPI `BackgroundTask`. Exposes a `GET /status/{job_id}` polling endpoint.
2.  **The Cognitive Engine (CrewAI):** 
    * *Developer Agent:* Writes the initial Python algorithm.
    * *QA Agent:* Writes adversarial `pytest` edge-case tests.
    * *Reflection Agent (Critic):* Analyzes tracebacks if tests fail, providing a strategic critique for the Developer to retry (Reflexion pattern).
    * *Tutor Agent:* Explains the Big O time/space complexity and logic of the final passing code.
3.  **The Execution Sandbox:** A secure Python utility utilizing `tempfile` and `subprocess.run` with strict timeouts to physically execute the QA Agent's tests against the Developer's code.
4.  **The Frontend (Streamlit - Port 8501):** A "dumb" client. It ONLY makes REST HTTP requests to the FastAPI backend and polls for status updates. It contains zero LLM/CrewAI logic.

## 4. Critical Rules & Anti-Patterns (DO NOT DO THESE)
* **CRITICAL:** DO NOT import or run `crewai` inside the Streamlit frontend. Streamlit reruns its script on every UI interaction; doing so will destroy the agent state and cause massive API billing spikes. Streamlit must only use the `requests` library.
* **CRITICAL:** DO NOT make the FastAPI `/solve` endpoint synchronous. Multi-agent loops take 60+ seconds and will cause standard HTTP timeouts. Always use background tasks and job status polling.
* **CRITICAL:** DO NOT fake code execution. The generated code MUST be written to a temporary file and run via `subprocess`. Physical traceback errors must be caught and fed back to the Reflection Agent.
* **CRITICAL:** DO NOT overcomplicate state management. Use a simple in-memory dictionary or local `SQLite` to track the status of async `job_id`s to save development time.

## 5. Implementation Roadmap (Iterative Generation)
When prompted to build a new feature, consult this roadmap and do not jump ahead.
* **Phase 1: The Sandbox.** Build `execution_sandbox.py` first. Verify it catches infinite loops, `IndexErrors`, and standard outputs properly.
* **Phase 2: The Async API.** Build the FastAPI scaffolding (`/solve` and `/status`) using a mock delay to test the background task architecture.
* **Phase 3: The Brains.** Implement the CrewAI agents and wire the self-healing routing loop (Dev -> QA -> Sandbox -> Reflect -> Dev).
* **Phase 4: The UI.** Build the Streamlit polling client to visualize the agent handoffs. 
* **Phase 5: The Evaluation.** Write the standalone script to loop dataset questions through the API and calculate the final Pass@k score.

A complete architecture diagram is included in this repo for reference as Architecture_Diagram.png. 