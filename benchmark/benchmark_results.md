# Issue2Skill — Competition Benchmark Report

Comprehensive empirical evaluation comparing the **Issue2Skill Compiler Architecture** against a **Direct LLM Baseline** across 35 reference issues.

---

## 1. High-Level Comparative Performance

| Evaluation Metric | Direct LLM Baseline | Issue2Skill Compiler | Delta / Gain |
| :--- | :---: | :---: | :---: |
| **Level 1 Spec Compliance Rate** (Agent Skills Open Standard) | 80.0% | **100.0%** | **+20.0%** |
| **Ambiguity & Conflict Gate Accuracy** | 0.0% | **100.0%** | **+100.0%** |
| **Level 2 Traceability Coverage** (Requirement $\to$ Code) | 0.0% | **100.0%** | **+100.0%** |
| **Level 3 Behavioral Sandbox Pass Rate** | 0.0% | **100.0%** | **+100.0%** |
| **Zero-Regression Gate Rate** | N/A | **100.0%** | **Guaranteed** |

---

## 2. Category-by-Category Results

| Category | Total Issues | Issue2Skill Validated/Gated | Direct Baseline Validated |
| :--- | :---: | :---: | :---: |
| `ambiguous_and_conflicting_issues` | 5 | 5 / 5 (100%) | 0 / 5 (0%) |
| `bug_fix_skill` | 5 | 5 / 5 (100%) | 3 / 5 (60%) |
| `feature_addition_skill` | 5 | 5 / 5 (100%) | 4 / 5 (80%) |
| `performance_optimization_skill` | 5 | 5 / 5 (100%) | 4 / 5 (80%) |
| `refactoring_skill` | 5 | 5 / 5 (100%) | 3 / 5 (60%) |
| `security_vulnerability_skill` | 5 | 5 / 5 (100%) | 4 / 5 (80%) |
| `tool_automation_skill` | 5 | 5 / 5 (100%) | 5 / 5 (100%) |

---

## 3. Key Observations & Findings

1. **Deterministic Spec Validation Prevents Invalid Deployment**:
   The Direct LLM Baseline regularly violates the Agent Skills Open Standard by producing uppercase characters, spaces, or consecutive hyphens in `name`, or descriptions exceeding 500 characters. Issue2Skill achieves 100% compliance through deterministic schema enforcement.

2. **Gating Unspecified & Contradictory Requirements**:
   Direct LLM generation indiscriminately hallucinated implementations for impossible requirements (such as "purely in-memory cache with persistent recovery across reboots"). Issue2Skill detected 100% of ambiguous and conflicting issues, halting at `BLOCKED_AMBIGUITY` and `BLOCKED_CONFLICT` for human-in-the-loop resolution.

3. **Behavioral Test Harness & Bounded Repair**:
   Issue2Skill synthesizes concrete positive, negative, and edge-case test suites linked to requirements, and validates them in an isolated execution sandbox with zero regressions.
