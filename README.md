# Issue2Skill

> **Compiler transforming unstructured GitHub Issues into validated, traceable, and self-repairing Agent Skills conforming to the Agent Skills Open Standard.**

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18+-61DAFB.svg?logo=react&logoColor=black)](https://react.dev/)
[![Database](https://img.shields.io/badge/Database-Turso%20%2F%20libSQL-00FFE0.svg?logo=sqlite&logoColor=black)](https://turso.tech/)
[![Model](https://img.shields.io/badge/Model-Qwen3--8B-purple.svg)](https://github.com/QwenLM)

---

## 1. Project Overview

**Issue2Skill** treats Agent Skill creation not as an unconstrained generative prompt, but as a **schema-constrained compiler and verification pipeline**.

An Agent Skill is not an executable binary; it is an instruction and resource package that guides autonomous agents. Testing an Agent Skill requires a dedicated **Skill Harness** that presents synthetic tasks to an agent adhering to `SKILL.md` instructions and evaluates the induced behavior against requirement-derived assertions inside an **Isolated Docker Execution Sandbox**.

---

## 2. Core Pipeline

```text
GitHub Issue
     │
     ▼
Issue Ingestion (URL or Raw Text + SHA-256 Content Digest)
     │
     ▼
Eligibility Classification (SKILL_COMPATIBLE vs UNSUPPORTED_ISSUE)
     │
     ▼
Requirement Extraction (REQ-xxx Formulation + Constraints + Acceptance Criteria)
     │
     ▼
Ambiguity & Conflict Detection (Blocking vs Non-Blocking Identification)
     │
     ▼
SkillIR Formulation (Schema-Constrained Intermediate Representation)
     │
     ▼
SKILL.md Generation (YAML Frontmatter + Sequential Instructions INS-xxx)
     │
     ▼
Deterministic Spec Validation (Level 1: Agent Skills Open Standard Conformance)
     │
     ▼
Requirement-Linked Test Generation (TEST-xxx with Deterministic Assertions)
     │
     ▼
Test & Traceability Validation (Level 2: Semantic & Graph Linkage Audit)
     │
     ▼
Skill Harness Initialization (Task Prompt + Fixtures + Approved Mock Tools)
     │
     ▼
Docker Sandbox Execution (Level 3: Isolated Containerized Run or SANDBOX_UNAVAILABLE)
     │
     ▼
Behavioral Evaluation (Exit Codes, Output Regex, File Changes)
     │
     ├─ All Tests Pass ──► Final Validation ──► Validated Skill ──► Export / GitHub PR
     │
     └─ Failure Detected ──► Failure Diagnosis (Fault Localization to REQ & INS)
                                  │
                                  ▼
                             Bounded Patch Repair (Unified Diff on Candidate Skill)
                                  │
                                  ▼
                             Regression Testing (Failing Test + All Previous Passes)
                                  │
                                  ├── Pass ──► Promote Candidate ──► Validated Skill
                                  └── Fail ──► Next Iteration (Max 3) or REPAIR_FAILED
```

---

## 3. Technical Differentiation

1. **Eligibility Classification:** Classifies incoming issues before synthesis. Non-skill requests (e.g. codebase bug fixes, CSS styling issues, database schema migrations, hardware bugs) return `UNSUPPORTED_ISSUE` with structured rationales rather than hallucinating an invalid skill.
2. **Schema-Constrained SkillIR:** A typed intermediate representation (Pydantic v2 models) that provides bidirectional traceability between natural language requirements (`REQ-xxx`), compiled instructions (`INS-xxx`), and test cases (`TEST-xxx`).
3. **Three-Level Validation Architecture:**
   * **Level 1 (Deterministic Spec Validation):** Enforces syntactic and structural rules defined by the Agent Skills Open Standard.
   * **Level 2 (Semantic & Traceability Validation):** Combines LLM semantic alignment with graph analysis to audit requirement coverage.
   * **Level 3 (Behavioral Validation):** Asserts observable behavior when the skill is exercised by the Skill Harness in an isolated execution sandbox.
4. **Isolated Docker Execution Sandbox:** Untrusted code execution is strictly containerized using Docker with dropped privileges, disabled networking, and memory/CPU caps. If Docker is unavailable, the pipeline returns `SANDBOX_UNAVAILABLE` and refuses to run untrusted code on the host.
5. **Bounded Patch-Based Repair with Regression Gate:** Failures produce minimal unified diff patches applied to candidate versions (`Skill-V2-Candidate`). A candidate is accepted only if it resolves the failing test while passing all historical tests (capped at 3 repair iterations).

---

## 4. Architecture

Issue2Skill is structured as a **Modular Monolith**:

```text
[Frontend: React + Vite + Monaco]
         │ (HTTP REST / SSE Stream)
         ▼
[Backend: FastAPI Modular Monolith]
   ├── API Router (main.py)
   ├── Pipeline State Machine (pipeline.py)
   │     ├── Eligibility Classifier
   │     ├── SkillIR Compiler
   │     ├── Three-Level Validator
   │     └── Diagnostic & Repair Engine
   └── Core Services (services.py)
         ├── TursoClient (Hrana HTTP Pipeline + In-Memory Fallback)
         ├── LLMClient (Qwen3-8B via vLLM / Ollama)
         ├── SkillHarness (Behavioral Evaluation Runtime)
         ├── DockerExecutionSandbox (Isolated Container Boundary)
         └── GitHubClient (Least-Privilege REST Client)
```

---

## 5. SkillIR & Traceability Metrics

SkillIR normalizes unstructured requirements into structured entities with stable identifiers:

$$\text{REQ-xxx} \longleftrightarrow \text{INS-xxx} \longleftrightarrow \text{TEST-xxx} \longleftrightarrow \text{RUN-xxx}$$

### Verification Metrics Defined
A requirement being mapped does **not** imply that it is satisfied. The system separately measures:

* **Traceability Coverage:** $\frac{|\text{Requirements Mapped to Instructions}|}{|\text{Total Extracted Requirements}|}$
* **Test Coverage:** $\frac{|\text{Requirements Linked to Executable Tests}|}{|\text{Total Extracted Requirements}|}$
* **Behavioral Pass Rate:** $\frac{|\text{Passing Requirement-Linked Tests}|}{|\text{Total Executed Tests}|}$
* **Regression Pass Rate:** $\frac{|\text{Historical Passing Tests Retained After Repair}|}{|\text{Total Historical Passing Tests}|}$

---

## 6. Validation & Testing

### Level 1 — Deterministic Spec Validation (Agent Skills Open Standard)
* **Frontmatter:** Valid YAML enclosed by `---` delimiters.
* **Mandatory Fields:** `name` and `description`.
* **Name Syntax:** 1–64 characters, lowercase alphanumeric and hyphens (`[a-z0-9-]`), no leading hyphen, no trailing hyphen, no consecutive hyphens (`--`). Matching regex: `^(?!.*--)[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$`.
* **Description Syntax:** Non-empty string, maximum 500 characters.

### Issue2Skill Security Validation (Defense-in-Depth)
* **Path Traversal Prevention:** Rejects parent directory traversal (`..`) or absolute path injection in referenced assets.
* **File Size Limits:** Maximum 64KB per `SKILL.md`.
* **Credential Isolation:** Scans for and rejects exposed token patterns.

### Level 2 — Semantic & Traceability Validation
Audits requirement completeness, flags unmapped requirements, and checks for unresolved blocking ambiguities or conflicting constraints.

### Level 3 — Behavioral Validation (Skill Harness)
The **Skill Harness** loads `SKILL.md`, configures task fixtures, injects approved tools, runs the agent, and verifies deterministic assertions (`EXIT_CODE_EQUALS`, `STDOUT_CONTAINS`, `FILE_EXISTS`, `JSON_SCHEMA_MATCHES`).

---

## 7. Security Architecture

### 7.1 Isolated Docker Execution Sandbox
Untrusted generated skill scripts are executed inside a resource-constrained Docker container:
* **User Isolation:** Non-root execution (`--user 1000:1000`).
* **Network Isolation:** Networking disabled (`--network none`).
* **Filesystem Isolation:** Read-only root filesystem (`--read-only`), dedicated writable workspace (`-v <workspace>:/workspace:rw -w /workspace`).
* **Privilege Reduction:** Dropped capabilities (`--cap-drop ALL`), `no-new-privileges` flag enabled. No Docker socket mounted.
* **Resource Limits:** CPU cap (`--cpus 1.0`), memory cap (`--memory 512m`), process cap (`--pids-limit 64`), timeout (15s).
* **Package Manager Ban:** Commands invoking `pip`, `npm`, `curl`, `wget`, or `apt` are blocked.

> [!IMPORTANT]
> **No Unsafe Native Fallback:** If Docker is not installed or the Docker daemon is unreachable, the system returns `SANDBOX_UNAVAILABLE` and blocks execution of untrusted generated code.

### 7.2 Cryptographic Content Digests (SHA-256)
SHA-256 hashes are used for **artifact identity, version tracking, reproducibility, content-change detection, and cache keys**. Hashes provide change detection when the trusted reference is protected; they are not presented as standalone tamper-proof security.

### 7.3 Database & Secret Protection
* `TURSO_AUTH_TOKEN` is read strictly from environment variables and is scrubbed from logs and client responses.
* **Database Fallback:** If `TURSO_AUTH_TOKEN` is not provisioned or the network is unreachable, `TursoClient` activates an in-memory SQLite store (`:memory:`) to allow local development and testing. (Remote cloud replication requires provisioned credentials).

### 7.4 Least-Privilege GitHub Access
* Public issues are ingested via the unauthenticated GitHub REST API.
* Pull Request export uses fine-grained permissions limited strictly to `contents:write` and `pull_requests:write`. No workflow permissions are requested.

---

## 8. Repository Structure

```text
Issue2Skill/
├── .env.example                 # Sanitized environment template (no credentials)
├── .gitignore                   # Excludes .env, __pycache__, node_modules, dist, artifacts
├── LICENSE                      # Apache-2.0 License
├── README.md                    # System documentation and architecture guide
│
├── backend/
│   ├── main.py                  # FastAPI REST API, SSE telemetry streaming, CORS, error handling
│   ├── pipeline.py              # State machine (18 states), SkillIR compiler, 3-level validation, repair
│   ├── services.py              # TursoClient (Hrana HTTP + SQLite fallback), LLMClient, DockerExecutionSandbox, SkillHarness
│   └── requirements.txt         # Pinned backend dependencies
│
├── frontend/
│   ├── index.html               # Developer console root
│   ├── vite.config.ts           # Vite build config with dev proxy to backend port 8000
│   ├── tsconfig.json            # TypeScript compiler configuration
│   ├── tailwind.config.js       # Developer dark theme configuration
│   ├── package.json             # Pinned React dependencies
│   └── src/
│       ├── main.tsx             # React mount, base styles, error boundary
│       ├── App.tsx              # High-density Developer Console (Pipeline stepper, Monaco, Traceability)
│       ├── api.ts               # API client, TypeScript definitions, SSE stream listener
│       └── index.css            # Tailwind directives and dark styling
│
├── benchmark/
│   ├── dataset.json             # 35 curated benchmark issues across 7 categories
│   ├── evaluate.py              # Automated evaluation harness comparing against Direct LLM Baseline
│   ├── benchmark_results.json   # Machine-readable evaluation metrics
│   └── benchmark_results.md     # Formatted markdown benchmark report
│
└── tests/
    ├── test_pipeline.py         # Unit tests for eligibility, spec validation, and end-to-end compiler
    ├── test_security.py         # OWASP Top 10 tests (Docker sandbox requirement, path traversal, banned tools)
    ├── test_interactive_resolution.py # Tests for human-in-the-loop ambiguity and conflict resolution
    └── test_benchmark_dataset.py # Tests verifying schema and integrity of 35-issue benchmark dataset
```

---

## 9. Quickstart Guide

### 9.1 Prerequisites
* Python 3.11+
* Node.js 20+
* Docker Engine (required for Level 3 untrusted behavioral execution)

### 9.2 Configuration
```bash
git clone https://github.com/nagajahnavibusani3103/Issue2Skill.git
cd Issue2Skill
cp .env.example .env
```

### 9.3 Run Backend
```bash
python -m pip install -r backend/requirements.txt
python -m uvicorn backend.main:app --port 8000 --reload
```
Interactive API documentation: `http://localhost:8000/docs`.

### 9.4 Run Frontend
```bash
cd frontend
npm.cmd install
npm.cmd run dev
```
Open `http://localhost:5173` to launch the Developer Console.

---

## 10. Verification & Test Commands

```bash
# Execute full automated test suite (14 tests)
python -m pytest tests/ -v

# Run the 35-issue automated comparative benchmark
python benchmark/evaluate.py

# Verify frontend production build
cd frontend
npm.cmd run build
```

---

## 11. Empirical Evaluation & Benchmark Results

The system was evaluated against a curated reference suite of 35 GitHub issues across 7 balanced categories (5 per category):
1. `bug_fix_skill` (RFC 4180 CSV parsing, JWT clock skew, JSON null traversal, rate limiter, ReDoS-safe email validation)
2. `feature_addition_skill` (OpenAPI from Fastify, conventional commit release notes, GHA validator, S3 pre-signed upload, SQLite to Parquet)
3. `refactoring_skill` (Express repository decouple, sync to async file I/O, Pydantic BaseSettings, Redux Toolkit slices, async backoff)
4. `performance_optimization_skill` (N+1 query loader, LRU embedding cache, streaming JSONL processor, Redis pipeline batching, submodule fetcher)
5. `security_vulnerability_skill` (SQL injection parameterizer, SSRF image fetcher guard, zip path traversal guard, log PII redactor, constant-time HMAC)
6. `tool_automation_skill` (multi-stage Dockerfile optimizer, Gitleaks pre-commit installer, TS dead code scanner, K8s manifest auditor, Dependabot triage)
7. `ambiguous_and_conflicting_issues` (vague caching speedup, unbounded database scope, in-memory vs durable disk conflict, public access vs strict auth conflict, empty update)

### Comparative Benchmark Results (Issue2Skill vs. Direct LLM Baseline)

| Evaluation Metric | Direct LLM Baseline | Issue2Skill Compiler | Delta / Gain |
| :--- | :---: | :---: | :---: |
| **Level 1 Spec Compliance Rate** (Agent Skills Open Standard) | 80.0% | **100.0%** | **+20.0%** |
| **Ambiguity & Conflict Gate Accuracy** | 0.0% | **100.0%** | **+100.0%** |
| **Level 2 Traceability Coverage** (Requirement $\to$ Code) | 0.0% | **100.0%** | **+100.0%** |
| **Level 3 Behavioral Sandbox Pass Rate** | 0.0% | **100.0%** | **+100.0%** |
| **Zero-Regression Gate Rate** | N/A | **100.0%** | **Guaranteed** |

---

## 12. License

Licensed under the [Apache License, Version 2.0](LICENSE).