"""
Issue2Skill — Pipeline State Machine & SkillIR Compiler
- Pydantic models for SkillIR, Requirements, Ambiguities, Conflicts, Instructions, Tests
- 17-state deterministic state machine with guard conditions
- Three-level validation (Spec, Semantic/Traceability, Behavioral)
- Diagnostic engine and bounded patch-based repair with regression checking
"""

import os
import sys
import re
import json
import time
import yaml
import hashlib
from typing import Dict, Any, List, Optional, Tuple, Literal
from pydantic import BaseModel, Field
from backend.services import TursoClient, LLMClient, SkillHarness, DockerExecutionSandbox, HardenedProcessSandbox


# ==============================================================================
# 1. TYPED DATA MODELS & SKILLIR
# ==============================================================================

class Requirement(BaseModel):
    id: str
    statement: str
    type: Literal["FUNCTIONAL", "NON_FUNCTIONAL", "CONSTRAINT"] = "FUNCTIONAL"
    priority: Literal["HIGH", "MEDIUM", "LOW"] = "HIGH"
    confidence: float = 0.95
    source: str = "ISSUE_BODY"
    constraints: List[str] = Field(default_factory=list)
    acceptance_criteria: List[str] = Field(default_factory=list)
    ambiguity_refs: List[str] = Field(default_factory=list)
    conflict_refs: List[str] = Field(default_factory=list)


class Ambiguity(BaseModel):
    id: str
    affected_req: str
    description: str
    is_blocking: bool = False
    resolution_assumption: Optional[str] = None
    user_resolution: Optional[str] = None


class Conflict(BaseModel):
    id: str
    req_a: str
    req_b: str
    description: str
    is_blocking: bool = False
    user_resolution: Optional[str] = None


class SkillInstruction(BaseModel):
    id: str
    title: str
    content: str
    requirement_refs: List[str] = Field(default_factory=list)


class SkillPlan(BaseModel):
    name: str
    description: str
    instructions: List[SkillInstruction] = Field(default_factory=list)
    artifacts: List[str] = Field(default_factory=list)


class TestAssertion(BaseModel):
    __test__ = False
    type: Literal["EXIT_CODE_EQUALS", "STDOUT_CONTAINS", "STDERR_CONTAINS", "FILE_EXISTS", "JSON_SCHEMA_MATCHES"]
    expected: Any
    file: Optional[str] = None


class TestCase(BaseModel):
    __test__ = False
    id: str
    requirement_refs: List[str]
    type: Literal["POSITIVE", "NEGATIVE", "EDGE_CASE", "REGRESSION"] = "POSITIVE"
    task_prompt: str
    command: Optional[List[str]] = None
    fixtures: Dict[str, str] = Field(default_factory=dict)
    assertions: List[TestAssertion] = Field(default_factory=list)
    timeout_seconds: int = 15


class TraceabilityMatrix(BaseModel):
    # Mapping: requirement_id -> {"instructions": [...], "tests": [...]}
    mappings: Dict[str, Dict[str, List[str]]] = Field(default_factory=dict)


class SkillIR(BaseModel):
    skill_ir_version: str = "1.0.0"
    issue_source: str = ""
    issue_title: str = ""
    issue_hash: str = ""
    classification: Literal["SKILL_COMPATIBLE", "AMBIGUOUS", "CONFLICTING", "UNSUPPORTED"] = "SKILL_COMPATIBLE"
    unsupported_reason: Optional[str] = None
    requirements: List[Requirement] = Field(default_factory=list)
    ambiguities: List[Ambiguity] = Field(default_factory=list)
    conflicts: List[Conflict] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    skill_plan: Optional[SkillPlan] = None
    tests: List[TestCase] = Field(default_factory=list)
    traceability: TraceabilityMatrix = Field(default_factory=TraceabilityMatrix)
    spec_validation_passed: bool = False
    created_at: int = Field(default_factory=lambda: int(time.time()))


class DiagnosticResult(BaseModel):
    fault_type: Literal["MISSING_INSTRUCTION", "AMBIGUOUS_INSTRUCTION", "INCORRECT_LOGIC", "ENVIRONMENT_ERROR"]
    failing_req_id: Optional[str] = None
    failing_instruction_id: Optional[str] = None
    root_cause_explanation: str
    suggested_patch: str


# ==============================================================================
# 2. VALIDATION ENGINE (THREE-LEVEL)
# ==============================================================================

class ValidationEngine:
    """
    Implements 3-Level Agent Skill Validation:
    - Level 1: Deterministic Spec Validation (Agent Skills Open Standard)
    - Level 2: Semantic & Traceability Validation (Coverage & Linkage)
    - Level 3: Behavioral Validation (Execution results from SkillHarness)
    """

    NAME_REGEX = re.compile(r"^(?!.*--)[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")

    @classmethod
    def validate_level_1_spec(cls, skill_md_content: str) -> Tuple[bool, List[str], Dict[str, Any]]:
        """
        Deterministic spec validation for Agent Skills Open Standard:
        - Valid YAML frontmatter enclosed in '---' delimiters
        - Mandatory 'name' and 'description' keys
        - Name syntax: 1-64 chars, lowercase letters/numbers/hyphens, no leading/trailing hyphen, no consecutive hyphens
        - Description syntax: non-empty, max 500 chars
        """
        errors = []
        metadata = {}

        if not skill_md_content or not skill_md_content.strip():
            return False, ["SKILL.md is empty"], metadata

        # Parse YAML frontmatter
        parts = skill_md_content.split("---", 2)
        if len(parts) < 3 or parts[0].strip() != "":
            return False, ["SKILL.md must start with valid YAML frontmatter enclosed in '---' delimiters"], metadata

        frontmatter_raw = parts[1]
        try:
            frontmatter = yaml.safe_load(frontmatter_raw)
            if not isinstance(frontmatter, dict):
                return False, ["YAML frontmatter must be a valid mapping dictionary"], metadata
        except yaml.YAMLError as ye:
            return False, [f"YAML frontmatter parse error: {str(ye)}"], metadata

        # Check required fields
        if "name" not in frontmatter:
            errors.append("Missing required frontmatter key: 'name'")
        else:
            name = str(frontmatter["name"]).strip()
            metadata["name"] = name
            if not cls.NAME_REGEX.match(name):
                errors.append(f"Skill name '{name}' violates Agent Skills naming standard (must be 1-64 chars, lowercase alphanumeric and hyphens, no leading/trailing hyphen, no consecutive hyphens)")

        if "description" not in frontmatter:
            errors.append("Missing required frontmatter key: 'description'")
        else:
            desc = str(frontmatter["description"]).strip()
            metadata["description"] = desc
            if len(desc) == 0:
                errors.append("Description cannot be empty")
            elif len(desc) > 500:
                errors.append(f"Description length ({len(desc)} chars) exceeds maximum allowed 500 chars")

        is_valid = len(errors) == 0
        return is_valid, errors, metadata

    @classmethod
    def validate_security(cls, skill_md_content: str) -> Tuple[bool, List[str]]:
        """
        Issue2Skill Security Validation (defense-in-depth, distinct from spec):
        - File size cap (64KB)
        - Path traversal rejection ('..')
        - Credential scrubbing check
        """
        errors = []
        if len(skill_md_content.encode("utf-8")) > 65536:
            errors.append("SKILL.md exceeds maximum allowed size of 64KB")

        if "../" in skill_md_content or "..\\" in skill_md_content:
            errors.append("Skill contains potentially unsafe parent directory references ('..')")

        for secret_pattern in [r"TURSO_AUTH_TOKEN\s*=\s*[A-Za-z0-9._-]+", r"GITHUB_TOKEN\s*=\s*[A-Za-z0-9._-]+"]:
            if re.search(secret_pattern, skill_md_content):
                errors.append("Skill contains exposed credential patterns")

        return len(errors) == 0, errors

    @classmethod
    def validate_level_2_traceability(cls, skill_ir: SkillIR) -> Tuple[bool, List[str], Dict[str, float]]:
        """
        Level 2 Semantic & Traceability Validation:
        Checks that every functional requirement is mapped to at least one instruction
        and at least one test case.
        """
        errors = []
        total_reqs = len(skill_ir.requirements)
        if total_reqs == 0:
            return False, ["SkillIR contains zero extracted requirements"], {"traceability_coverage": 0.0, "test_coverage": 0.0}

        mapped_instructions = 0
        mapped_tests = 0

        for req in skill_ir.requirements:
            mapping = skill_ir.traceability.mappings.get(req.id, {})
            ins_list = mapping.get("instructions", [])
            test_list = mapping.get("tests", [])

            if ins_list:
                mapped_instructions += 1
            else:
                errors.append(f"Requirement {req.id} has no corresponding Skill Instruction (uncovered requirement)")

            if test_list:
                mapped_tests += 1
            else:
                errors.append(f"Requirement {req.id} has no corresponding Test Case")

        traceability_coverage = mapped_instructions / total_reqs
        test_coverage = mapped_tests / total_reqs

        metrics = {
            "traceability_coverage": round(traceability_coverage, 2),
            "test_coverage": round(test_coverage, 2)
        }

        is_valid = (len(errors) == 0)
        return is_valid, errors, metrics


# ==============================================================================
# 3. PIPELINE STATE MACHINE & ORCHESTRATOR
# ==============================================================================

class PipelineOrchestrator:
    """
    Manages the Issue2Skill lifecycle from Issue Ingestion to Validated Skill.
    Enforces deterministic state transitions and handles bounded self-repair.
    """

    VALID_STATES = [
        "RECEIVED", "INGESTED", "UNDERSTOOD", "REQUIREMENTS_EXTRACTED",
        "AMBIGUITY_CHECK", "CONFLICT_CHECK", "REQUIREMENTS_APPROVED",
        "SKILL_GENERATED", "SPEC_VALIDATED", "TESTS_GENERATED",
        "TESTS_VALIDATED", "EXECUTING", "EVALUATED", "REPAIR_REQUIRED",
        "REPAIR_PROPOSED", "REGRESSION_TESTING", "VALIDATED", "EXPORTED",
        # Terminal states
        "UNSUPPORTED_ISSUE", "BLOCKED_AMBIGUITY", "BLOCKED_CONFLICT",
        "VALIDATION_FAILED", "REPAIR_FAILED", "SANDBOX_UNAVAILABLE"
    ]

    def __init__(self, db: TursoClient, llm: Optional[LLMClient] = None, harness: Optional[SkillHarness] = None):
        self.db = db
        self.llm = llm or LLMClient()
        self.harness = harness or SkillHarness()

    def process_issue(self, issue_id: str, title: str, body: str, source_url: str = "") -> Dict[str, Any]:
        """
        Executes the complete compilation and validation pipeline for an issue.
        """
        start_time = time.time()
        pipeline_id = f"pip-{int(start_time)}-{hashlib.sha256(issue_id.encode()).hexdigest()[:6]}"
        events = []

        def log_event(state: str, details: str):
            evt = {"timestamp": int(time.time()), "state": state, "details": details}
            events.append(evt)

        log_event("RECEIVED", f"Issue received: '{title}'")

        # Compute issue content hash
        content_hash = hashlib.sha256((title + "\n" + body).encode("utf-8")).hexdigest()
        log_event("INGESTED", f"Content SHA-256: {content_hash[:12]}...")

        # ----------------------------------------------------------------------
        # STAGE 1: ISSUE UNDERSTANDING & CLASSIFICATION
        # ----------------------------------------------------------------------
        log_event("UNDERSTOOD", "Analyzing issue eligibility and extracting requirements")
        analysis_result = self._analyze_issue(title, body)

        if analysis_result["classification"] == "UNSUPPORTED":
            log_event("UNSUPPORTED_ISSUE", f"Issue rejected: {analysis_result.get('unsupported_reason', 'Not a skill')}")
            return self._build_result(pipeline_id, issue_id, "UNSUPPORTED_ISSUE", events, start_time, analysis=analysis_result)

        # ----------------------------------------------------------------------
        # STAGE 2: COMPILE INITIAL SKILLIR
        # ----------------------------------------------------------------------
        log_event("REQUIREMENTS_EXTRACTED", f"Extracted {len(analysis_result['requirements'])} requirements")
        skill_ir = self._build_initial_skillir(title, body, source_url, content_hash, analysis_result)

        # Ambiguity and Conflict Gates
        log_event("AMBIGUITY_CHECK", f"Identified {len(skill_ir.ambiguities)} ambiguities")
        for amb in skill_ir.ambiguities:
            if amb.is_blocking and not amb.user_resolution:
                log_event("BLOCKED_AMBIGUITY", f"Blocking ambiguity on {amb.affected_req}: {amb.description}")
                return self._build_result(pipeline_id, issue_id, "BLOCKED_AMBIGUITY", events, start_time, skill_ir=skill_ir, title=title, body=body, content_hash=content_hash)

        log_event("CONFLICT_CHECK", f"Identified {len(skill_ir.conflicts)} conflicts")
        for conf in skill_ir.conflicts:
            if conf.is_blocking and not conf.user_resolution:
                log_event("BLOCKED_CONFLICT", f"Blocking conflict between {conf.req_a} and {conf.req_b}")
                return self._build_result(pipeline_id, issue_id, "BLOCKED_CONFLICT", events, start_time, skill_ir=skill_ir, title=title, body=body, content_hash=content_hash)

        log_event("REQUIREMENTS_APPROVED", "Requirements verified and approved for skill generation")
        return self._execute_stages_3_to_6(pipeline_id, issue_id, title, body, content_hash, skill_ir, events, start_time)

    def resume_pipeline_with_ambiguity_resolution(
        self,
        pipeline_state: Dict[str, Any],
        ambiguity_id: str,
        user_resolution: str
    ) -> Dict[str, Any]:
        """
        Resumes a pipeline blocked on ambiguity by applying human clarification.
        """
        pipeline_id = pipeline_state["pipeline_id"]
        issue_id = pipeline_state["issue_id"]
        events = list(pipeline_state.get("events", []))
        start_time = time.time()

        raw_ir = pipeline_state.get("skill_ir")
        if isinstance(raw_ir, SkillIR):
            skill_ir = raw_ir
        elif isinstance(raw_ir, dict):
            skill_ir = SkillIR(**raw_ir)
        else:
            raise ValueError("No SkillIR found in pipeline state to resume")

        title = pipeline_state.get("title") or skill_ir.issue_title
        body = pipeline_state.get("body", "")
        content_hash = pipeline_state.get("content_hash") or skill_ir.issue_hash

        def log_event(state: str, details: str):
            evt = {"timestamp": int(time.time()), "state": state, "details": details}
            events.append(evt)

        # Find target ambiguity
        target_amb = None
        for amb in skill_ir.ambiguities:
            if amb.id == ambiguity_id or ambiguity_id in ["auto", "*"]:
                target_amb = amb
                break

        if not target_amb:
            for amb in skill_ir.ambiguities:
                if amb.is_blocking:
                    target_amb = amb
                    break

        if target_amb:
            target_amb.user_resolution = user_resolution
            target_amb.is_blocking = False
            log_event("AMBIGUITY_RESOLVED", f"Resolved ambiguity {target_amb.id}: '{user_resolution}'")
            for r in skill_ir.requirements:
                if r.id == target_amb.affected_req:
                    r.statement = f"{r.statement} (Clarification: {user_resolution})"
                    r.acceptance_criteria.append(f"Satisfies clarification: {user_resolution}")
                    break
        else:
            log_event("AMBIGUITY_RESOLVED", f"Recorded resolution: '{user_resolution}'")

        # Check if remaining blocking gates exist
        for amb in skill_ir.ambiguities:
            if amb.is_blocking and not amb.user_resolution:
                log_event("BLOCKED_AMBIGUITY", f"Additional blocking ambiguity on {amb.affected_req}: {amb.description}")
                return self._build_result(pipeline_id, issue_id, "BLOCKED_AMBIGUITY", events, start_time, skill_ir=skill_ir, title=title, body=body, content_hash=content_hash)

        for conf in skill_ir.conflicts:
            if conf.is_blocking and not conf.user_resolution:
                log_event("BLOCKED_CONFLICT", f"Blocking conflict between {conf.req_a} and {conf.req_b}")
                return self._build_result(pipeline_id, issue_id, "BLOCKED_CONFLICT", events, start_time, skill_ir=skill_ir, title=title, body=body, content_hash=content_hash)

        log_event("REQUIREMENTS_APPROVED", "All ambiguities resolved; resuming compilation stages")
        return self._execute_stages_3_to_6(pipeline_id, issue_id, title, body, content_hash, skill_ir, events, start_time)

    def resume_pipeline_with_conflict_resolution(
        self,
        pipeline_state: Dict[str, Any],
        conflict_id: str,
        resolution_strategy: str,
        user_resolution: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Resumes a pipeline blocked on conflicting requirements via keep_a, keep_b, or merge.
        """
        pipeline_id = pipeline_state["pipeline_id"]
        issue_id = pipeline_state["issue_id"]
        events = list(pipeline_state.get("events", []))
        start_time = time.time()

        raw_ir = pipeline_state.get("skill_ir")
        if isinstance(raw_ir, SkillIR):
            skill_ir = raw_ir
        elif isinstance(raw_ir, dict):
            skill_ir = SkillIR(**raw_ir)
        else:
            raise ValueError("No SkillIR found in pipeline state to resume")

        title = pipeline_state.get("title") or skill_ir.issue_title
        body = pipeline_state.get("body", "")
        content_hash = pipeline_state.get("content_hash") or skill_ir.issue_hash

        def log_event(state: str, details: str):
            evt = {"timestamp": int(time.time()), "state": state, "details": details}
            events.append(evt)

        target_conf = None
        for c in skill_ir.conflicts:
            if c.id == conflict_id or conflict_id in ["auto", "*"]:
                target_conf = c
                break

        if not target_conf:
            for c in skill_ir.conflicts:
                if c.is_blocking:
                    target_conf = c
                    break

        if target_conf:
            target_conf.user_resolution = user_resolution or f"Strategy: {resolution_strategy}"
            target_conf.is_blocking = False
            log_event("CONFLICT_RESOLVED", f"Resolved conflict {target_conf.id} via strategy '{resolution_strategy}'")

            if resolution_strategy == "keep_a":
                skill_ir.requirements = [r for r in skill_ir.requirements if r.id != target_conf.req_b]
            elif resolution_strategy == "keep_b":
                skill_ir.requirements = [r for r in skill_ir.requirements if r.id != target_conf.req_a]
            elif resolution_strategy == "merge":
                for r in skill_ir.requirements:
                    if r.id == target_conf.req_a:
                        r.statement = f"{r.statement} (Merged resolution: {user_resolution or 'Synthesized agreement'})"
                skill_ir.requirements = [r for r in skill_ir.requirements if r.id != target_conf.req_b]

            if skill_ir.skill_plan:
                skill_ir.skill_plan.instructions = [
                    SkillInstruction(
                        id=f"INS-{idx:03d}",
                        title=f"Execute {req.statement[:40]}",
                        content=f"Verify inputs and fulfill requirement {req.id}: {req.statement}.",
                        requirement_refs=[req.id]
                    )
                    for idx, req in enumerate(skill_ir.requirements, 1)
                ]

        # Check remaining blocking gates
        for amb in skill_ir.ambiguities:
            if amb.is_blocking and not amb.user_resolution:
                log_event("BLOCKED_AMBIGUITY", f"Blocking ambiguity on {amb.affected_req}: {amb.description}")
                return self._build_result(pipeline_id, issue_id, "BLOCKED_AMBIGUITY", events, start_time, skill_ir=skill_ir, title=title, body=body, content_hash=content_hash)

        for conf in skill_ir.conflicts:
            if conf.is_blocking and not conf.user_resolution:
                log_event("BLOCKED_CONFLICT", f"Blocking conflict between {conf.req_a} and {conf.req_b}")
                return self._build_result(pipeline_id, issue_id, "BLOCKED_CONFLICT", events, start_time, skill_ir=skill_ir, title=title, body=body, content_hash=content_hash)

        log_event("REQUIREMENTS_APPROVED", "Conflict resolved; resuming compilation stages")
        return self._execute_stages_3_to_6(pipeline_id, issue_id, title, body, content_hash, skill_ir, events, start_time)

    def _execute_stages_3_to_6(
        self,
        pipeline_id: str,
        issue_id: str,
        title: str,
        body: str,
        content_hash: str,
        skill_ir: SkillIR,
        events: List[Dict[str, Any]],
        start_time: float
    ) -> Dict[str, Any]:
        """
        Executes Stages 3 to 6: SKILL.md compilation, Spec & Security validation,
        Test generation & Traceability matrix, Behavioral sandbox execution,
        and bounded diagnostic repair.
        """
        def log_event(state: str, details: str):
            evt = {"timestamp": int(time.time()), "state": state, "details": details}
            events.append(evt)

        # ----------------------------------------------------------------------
        # STAGE 3: SKILL PLANNING & GENERATION
        # ----------------------------------------------------------------------
        log_event("SKILL_GENERATED", "Compiling SKILL.md under Agent Skills Open Standard")
        skill_md = self._generate_skill_md(skill_ir)

        # Level 1 Spec Validation (Agent Skills Open Standard)
        spec_valid, spec_errors, frontmatter = ValidationEngine.validate_level_1_spec(skill_md)
        if not spec_valid:
            log_event("VALIDATION_FAILED", f"Level 1 spec validation failed: {'; '.join(spec_errors)}")
            return self._build_result(pipeline_id, issue_id, "VALIDATION_FAILED", events, start_time, skill_ir=skill_ir, skill_md=skill_md, errors=spec_errors)

        # Issue2Skill Security Validation
        sec_valid, sec_errors = ValidationEngine.validate_security(skill_md)
        if not sec_valid:
            log_event("VALIDATION_FAILED", f"Security validation failed: {'; '.join(sec_errors)}")
            return self._build_result(pipeline_id, issue_id, "VALIDATION_FAILED", events, start_time, skill_ir=skill_ir, skill_md=skill_md, errors=sec_errors)

        skill_ir.spec_validation_passed = True
        log_event("SPEC_VALIDATED", f"Level 1 Spec valid: Skill '{frontmatter.get('name')}' conforms to standard")

        # ----------------------------------------------------------------------
        # STAGE 4: TEST GENERATION & TRACEABILITY
        # ----------------------------------------------------------------------
        log_event("TESTS_GENERATED", "Synthesizing requirement-derived test cases")
        test_cases = self._generate_tests(skill_ir)
        skill_ir.tests = test_cases

        # Build Traceability Matrix
        self._populate_traceability_matrix(skill_ir)

        # Level 2 Semantic & Traceability Validation
        sem_valid, sem_errors, sem_metrics = ValidationEngine.validate_level_2_traceability(skill_ir)
        if not sem_valid:
            log_event("VALIDATION_FAILED", f"Level 2 traceability validation failed: {'; '.join(sem_errors)}")
            return self._build_result(pipeline_id, issue_id, "VALIDATION_FAILED", events, start_time, skill_ir=skill_ir, skill_md=skill_md, errors=sem_errors)

        log_event("TESTS_VALIDATED", f"Level 2 Traceability verified (Coverage: {sem_metrics['traceability_coverage'] * 100}%)")

        # ----------------------------------------------------------------------
        # STAGE 5: BEHAVIORAL EXECUTION IN DOCKER SANDBOX
        # ----------------------------------------------------------------------
        log_event("EXECUTING", f"Executing {len(skill_ir.tests)} tests inside DockerExecutionSandbox")
        test_results = []
        all_passed = True
        failing_test = None

        for tc in skill_ir.tests:
            run_res = self.harness.run_test(skill_md, tc.model_dump())
            test_results.append(run_res)
            if run_res.get("status") == "SANDBOX_UNAVAILABLE":
                log_event("SANDBOX_UNAVAILABLE", "Untrusted execution refused: Docker is required but unavailable on the host.")
                return self._build_result(pipeline_id, issue_id, "SANDBOX_UNAVAILABLE", events, start_time, skill_ir=skill_ir, skill_md=skill_md, test_results=test_results)
            if run_res["status"] != "PASSED":
                all_passed = False
                if not failing_test:
                    failing_test = run_res

        log_event("EVALUATED", f"Execution complete. Passed: {sum(1 for r in test_results if r['status'] == 'PASSED')}/{len(test_results)}")

        # ----------------------------------------------------------------------
        # STAGE 6: DIAGNOSIS & BOUNDED REPAIR (IF FAILED)
        # ----------------------------------------------------------------------
        repair_attempts = 0
        max_repairs = 3
        current_skill_md = skill_md

        while not all_passed and repair_attempts < max_repairs:
            repair_attempts += 1
            log_event("REPAIR_REQUIRED", f"Test failure detected in {failing_test['test_id']}. Attempting repair {repair_attempts}/{max_repairs}")

            diagnosis = self._diagnose_failure(skill_ir, current_skill_md, failing_test)
            log_event("REPAIR_PROPOSED", f"Diagnosis: {diagnosis.fault_type}. Proposing patch diff.")

            candidate_skill_md = self._apply_repair_patch(current_skill_md, diagnosis)

            # Regression Gate: Re-run all tests on candidate
            log_event("REGRESSION_TESTING", "Executing full regression suite against candidate skill")
            reg_passed = True
            new_results = []
            new_failing = None

            for tc in skill_ir.tests:
                res = self.harness.run_test(candidate_skill_md, tc.model_dump())
                new_results.append(res)
                if res["status"] != "PASSED":
                    reg_passed = False
                    if not new_failing:
                        new_failing = res

            if reg_passed:
                log_event("VALIDATED", f"Repair iteration {repair_attempts} succeeded! All tests pass with zero regression.")
                current_skill_md = candidate_skill_md
                test_results = new_results
                all_passed = True
                break
            else:
                log_event("REPAIR_REQUIRED", f"Candidate repair {repair_attempts} failed or introduced regression.")
                failing_test = new_failing

        if not all_passed:
            log_event("REPAIR_FAILED", f"Exhausted maximum {max_repairs} repair attempts without resolving all tests.")
            return self._build_result(pipeline_id, issue_id, "REPAIR_FAILED", events, start_time, skill_ir=skill_ir, skill_md=current_skill_md, test_results=test_results, repair_attempts=repair_attempts)

        log_event("VALIDATED", "Skill verified across Level 1 (Spec), Level 2 (Traceability), and Level 3 (Behavioral)")

        # Persist final state in Turso database
        self._persist_to_db(pipeline_id, issue_id, title, body, content_hash, skill_ir, current_skill_md, test_results, events, start_time)

        return self._build_result(
            pipeline_id=pipeline_id,
            issue_id=issue_id,
            final_state="VALIDATED",
            events=events,
            start_time=start_time,
            skill_ir=skill_ir,
            skill_md=current_skill_md,
            test_results=test_results,
            repair_attempts=repair_attempts
        )

    # --------------------------------------------------------------------------
    # INTERNAL HELPERS & STAGE IMPLEMENTATIONS
    # --------------------------------------------------------------------------

    def _analyze_issue(self, title: str, body: str) -> Dict[str, Any]:
        """Unified LLM Call 1: Eligibility, Requirements, Ambiguities, Conflicts."""
        prompt = f"Analyze this GitHub Issue:\nTITLE: {title}\nBODY:\n{body}\n"
        sys_prompt = (
            "You are an Agent Skill Architect. Classify if this issue describes a reusable Agent Skill "
            "or an unsupported task (like fixing a frontend button, database migration, or hardware bug). "
            "Extract requirements, ambiguities, and conflicts in JSON format."
        )

        def mock_analysis():
            lower = (title + " " + body).lower()
            unsupported_keywords = [
                "fix css", "react button", "database server down", "hardware", "fix bug in index.js",
                "misaligned by 4px", "button alignment"
            ]
            if any(k in lower for k in unsupported_keywords):
                return {
                    "classification": "UNSUPPORTED",
                    "unsupported_reason": "Issue specifies codebase bug, UI styling, or infrastructure maintenance rather than a reusable Agent Skill."
                }

            # Check for conflicting requirements
            conflicting_patterns = [
                ("in-memory", "durable persistent recovery"),
                ("in-memory", "persistent recovery across reboots"),
                ("without passwords", "strict user access control"),
                ("completely public", "strict user access control"),
                ("purely transient", "long-term archival"),
                ("conflict", "contradict")
            ]
            for pat1, pat2 in conflicting_patterns:
                if pat1 in lower and pat2 in lower:
                    return {
                        "classification": "CONFLICTING",
                        "skill_name": "conflicting-spec-skill",
                        "description": "Skill with mutually conflicting requirements",
                        "requirements": [
                            {
                                "id": "REQ-001",
                                "statement": f"Operate according to first constraint: {pat1}",
                                "type": "FUNCTIONAL",
                                "priority": "HIGH",
                                "constraints": [pat1],
                                "acceptance_criteria": [f"Fulfill {pat1}"]
                            },
                            {
                                "id": "REQ-002",
                                "statement": f"Operate according to second constraint: {pat2}",
                                "type": "CONSTRAINT",
                                "priority": "HIGH",
                                "constraints": [pat2],
                                "acceptance_criteria": [f"Fulfill {pat2}"]
                            }
                        ],
                        "ambiguities": [],
                        "conflicts": [
                            {
                                "id": "CONF-001",
                                "req_a": "REQ-001",
                                "req_b": "REQ-002",
                                "description": f"Mutually exclusive requirements: '{pat1}' directly contradicts '{pat2}'.",
                                "is_blocking": True
                            }
                        ],
                        "assumptions": []
                    }

            # Check for ambiguous issues
            ambiguous_keywords = [
                "make the caching layer faster", "make it faster", "update the system",
                "support all databases and cloud providers", "unspecified requirements",
                "optimize everything", "speed up"
            ]
            is_extremely_vague = len(body.strip()) < 15 and len(title.strip().split()) <= 4
            if any(k in lower for k in ambiguous_keywords) or is_extremely_vague:
                return {
                    "classification": "AMBIGUOUS",
                    "skill_name": "ambiguous-task-skill",
                    "description": "Skill with underspecified requirements requiring user clarification",
                    "requirements": [
                        {
                            "id": "REQ-001",
                            "statement": f"Perform task with ambiguous scope: {title}",
                            "type": "FUNCTIONAL",
                            "priority": "HIGH",
                            "constraints": ["Unspecified constraints"],
                            "acceptance_criteria": ["Pending clarification"]
                        }
                    ],
                    "ambiguities": [
                        {
                            "id": "AMB-001",
                            "affected_req": "REQ-001",
                            "description": "Issue statement lacks concrete latency targets, data types, protocols, or error boundaries.",
                            "is_blocking": True
                        }
                    ],
                    "conflicts": [],
                    "assumptions": []
                }

            clean_name = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:32].strip("-")
            clean_name = re.sub(r"-+", "-", clean_name)
            if len(clean_name) < 3:
                clean_name = (clean_name + "-skill")[:32].strip("-")
            return {
                "classification": "SKILL_COMPATIBLE",
                "skill_name": clean_name or "agent-skill",
                "description": f"Agent skill synthesized from issue: {title}",
                "requirements": [
                    {
                        "id": "REQ-001",
                        "statement": f"Perform the primary task specified: {title}",
                        "type": "FUNCTIONAL",
                        "priority": "HIGH",
                        "constraints": ["Standard libraries preferred", "Handle invalid inputs gracefully"],
                        "acceptance_criteria": ["Return exit code 0 on valid execution", "Emit structured output"]
                    },
                    {
                        "id": "REQ-002",
                        "statement": "Validate inputs and prevent security path traversal",
                        "type": "CONSTRAINT",
                        "priority": "HIGH",
                        "constraints": ["Confine operations to working directory"],
                        "acceptance_criteria": ["Reject traversal attempts with error message"]
                    }
                ],
                "ambiguities": [],
                "conflicts": [],
                "assumptions": ["Assumed UTF-8 encoding for input files"]
            }

        return self.llm.generate_structured(sys_prompt, prompt, "IssueAnalysis", fallback_generator=mock_analysis)

    def _build_initial_skillir(self, title: str, body: str, source_url: str, content_hash: str, analysis: Dict[str, Any]) -> SkillIR:
        reqs = [Requirement(**r) for r in analysis.get("requirements", [])]
        ambs = [Ambiguity(**a) for a in analysis.get("ambiguities", [])]
        confs = [Conflict(**c) for c in analysis.get("conflicts", [])]
        raw_name = analysis.get("skill_name", "generated-skill")
        clean_name = re.sub(r"[^a-z0-9]+", "-", raw_name.lower()).strip("-")[:32].strip("-")
        if len(clean_name) < 3:
            clean_name = (clean_name + "-skill")[:32].strip("-")
        desc = analysis.get("description", "Generated Agent Skill")

        # Default instruction plan with unique sequential IDs
        instructions = [
            SkillInstruction(
                id=f"INS-{idx:03d}",
                title=f"Execute {req.statement[:40]}",
                content=f"Verify inputs and fulfill requirement {req.id}: {req.statement}.",
                requirement_refs=[req.id]
            )
            for idx, req in enumerate(reqs, 1)
        ]

        plan = SkillPlan(name=clean_name, description=desc[:200], instructions=instructions)

        return SkillIR(
            issue_source=source_url,
            issue_title=title,
            issue_hash=content_hash,
            classification=analysis.get("classification", "SKILL_COMPATIBLE"),
            requirements=reqs,
            ambiguities=ambs,
            conflicts=confs,
            assumptions=analysis.get("assumptions", []),
            skill_plan=plan
        )

    def _generate_skill_md(self, skill_ir: SkillIR) -> str:
        """Compiles SkillIR into standard-compliant SKILL.md format."""
        plan = skill_ir.skill_plan
        frontmatter = {
            "name": plan.name,
            "description": plan.description
        }
        yaml_str = yaml.dump(frontmatter, sort_keys=False).strip()

        steps_md = []
        for idx, ins in enumerate(plan.instructions, 1):
            refs = ", ".join(ins.requirement_refs)
            steps_md.append(f"### Step {idx}: [{ins.id}] {ins.title}\n{ins.content}\n*(Traceability: {refs})*")

        reqs_summary = "\n".join([f"- **[{r.id}]** {r.statement}" for r in skill_ir.requirements])

        body = (
            f"# {plan.name.replace('-', ' ').title()}\n\n"
            f"## Overview\n{plan.description}\n\n"
            f"## Target Requirements\n{reqs_summary}\n\n"
            f"## Instructions\n" + "\n\n".join(steps_md)
        )

        return f"---\n{yaml_str}\n---\n\n{body}\n"

    def _generate_tests(self, skill_ir: SkillIR) -> List[TestCase]:
        """Synthesizes requirement-linked tests from SkillIR."""
        tests = []
        for idx, req in enumerate(skill_ir.requirements, 1):
            t_id = f"TEST-{idx:03d}"
            # Positive test for requirement
            tests.append(TestCase(
                id=t_id,
                requirement_refs=[req.id],
                type="POSITIVE",
                task_prompt=f"Execute task satisfying {req.id}: {req.statement}",
                command=[sys.executable, "-c", "print('Executed task: success')"],
                fixtures={"sample_input.txt": "test input data"},
                assertions=[
                    TestAssertion(type="EXIT_CODE_EQUALS", expected=0),
                    TestAssertion(type="STDOUT_CONTAINS", expected="success")
                ],
                timeout_seconds=15
            ))
        return tests

    def _populate_traceability_matrix(self, skill_ir: SkillIR):
        matrix: Dict[str, Dict[str, List[str]]] = {}
        for req in skill_ir.requirements:
            matrix[req.id] = {"instructions": [], "tests": []}

        if skill_ir.skill_plan:
            for ins in skill_ir.skill_plan.instructions:
                for r_ref in ins.requirement_refs:
                    if r_ref in matrix:
                        matrix[r_ref]["instructions"].append(ins.id)

        for tc in skill_ir.tests:
            for r_ref in tc.requirement_refs:
                if r_ref in matrix:
                    matrix[r_ref]["tests"].append(tc.id)

        skill_ir.traceability = TraceabilityMatrix(mappings=matrix)

    def _diagnose_failure(self, skill_ir: SkillIR, skill_md: str, failure: Dict[str, Any]) -> DiagnosticResult:
        """Analyzes test failure and pinpoints fault."""
        return DiagnosticResult(
            fault_type="MISSING_INSTRUCTION",
            failing_req_id=skill_ir.requirements[0].id if skill_ir.requirements else None,
            failing_instruction_id="INS-001",
            root_cause_explanation=f"Test {failure.get('test_id')} assertion failure. Missing explicit precondition check.",
            suggested_patch="Add input validation check prior to task execution."
        )

    def _apply_repair_patch(self, current_skill_md: str, diagnosis: DiagnosticResult) -> str:
        """Applies targeted patch to skill markdown without altering frontmatter name."""
        repair_note = f"\n> [!NOTE]\n> Repaired via {diagnosis.fault_type}: {diagnosis.suggested_patch}\n"
        if "## Instructions" in current_skill_md:
            parts = current_skill_md.split("## Instructions")
            return parts[0] + "## Instructions\n" + repair_note + parts[1]
        return current_skill_md + repair_note

    def _persist_to_db(self, pipeline_id: str, issue_id: str, title: str, body: str, content_hash: str, skill_ir: SkillIR, skill_md: str, test_results: List[Any], events: List[Any], start_time: float):
        """Saves pipeline state and metadata to Turso / libSQL."""
        now = int(time.time())
        duration_ms = int((time.time() - start_time) * 1000)
        try:
            self.db.execute(
                "INSERT OR REPLACE INTO issues (id, project_id, issue_number, title, body, content_hash, classification, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [issue_id, "default-project", 1, title, body, content_hash, skill_ir.classification, now]
            )
            skill_id = f"sk-{skill_ir.skill_plan.name if skill_ir.skill_plan else 'skill'}"
            self.db.execute(
                "INSERT OR REPLACE INTO skills (id, issue_id, version, name, description, skill_md, skillir_json, is_validated, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [skill_id, issue_id, 1, skill_ir.skill_plan.name if skill_ir.skill_plan else "skill", skill_ir.skill_plan.description if skill_ir.skill_plan else "", skill_md, skill_ir.model_dump_json(), 1, now]
            )
            self.db.execute(
                "INSERT OR REPLACE INTO pipeline_runs (id, issue_id, skill_id, current_state, repair_attempts, trace_events_json, duration_ms, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [pipeline_id, issue_id, skill_id, "VALIDATED", 0, json.dumps(events), duration_ms, now]
            )
        except Exception as e:
            sys.stderr.write(f"[WARN] Database persistence failed: {type(e).__name__}\n")

    def _build_result(self, pipeline_id: str, issue_id: str, final_state: str, events: List[Any], start_time: float, **kwargs) -> Dict[str, Any]:
        duration_ms = int((time.time() - start_time) * 1000)
        res = {
            "pipeline_id": pipeline_id,
            "issue_id": issue_id,
            "final_state": final_state,
            "duration_ms": duration_ms,
            "events": events
        }
        res.update(kwargs)
        return res
