"""
Unit and Integration Tests for Issue2Skill Pipeline & Compiler
- Eligibility classification
- Level 1 deterministic spec validation
- Level 2 semantic traceability validation
- End-to-end pipeline execution
- Bounded repair and regression gate
"""

import pytest
from backend.services import TursoClient, LLMClient, DockerExecutionSandbox, SkillHarness
from backend.pipeline import (
    PipelineOrchestrator, ValidationEngine, SkillIR, Requirement,
    SkillInstruction, SkillPlan, TestCase, TestAssertion, TraceabilityMatrix
)


@pytest.fixture
def orchestrator():
    db = TursoClient()  # Uses local in-memory fallback during tests
    llm = LLMClient()
    sandbox = DockerExecutionSandbox(timeout_seconds=5, mock_mode=True)
    harness = SkillHarness(sandbox=sandbox)
    return PipelineOrchestrator(db=db, llm=llm, harness=harness)


def test_issue_eligibility_classification(orchestrator):
    """Verifies that non-skill issues are classified as UNSUPPORTED."""
    # 1. Unsupported bug ticket
    res_unsupported = orchestrator.process_issue(
        issue_id="issue-001",
        title="Fix CSS React button alignment bug",
        body="The submit button is slightly shifted to the left on mobile viewports."
    )
    assert res_unsupported["final_state"] == "UNSUPPORTED_ISSUE"
    assert "unsupported_reason" in res_unsupported["analysis"]

    # 2. Supported skill requirement
    res_supported = orchestrator.process_issue(
        issue_id="issue-002",
        title="Create a CSV schema validation skill",
        body="Build a skill that validates CSV records against a provided JSON schema specification."
    )
    assert res_supported["final_state"] == "VALIDATED"
    assert res_supported["skill_ir"].classification == "SKILL_COMPATIBLE"


def test_level_1_spec_validation():
    """Deterministic validation against Agent Skills Open Standard."""
    # Valid Skill (standard name)
    valid_skill = """---
name: csv-validator
description: Validates CSV columns against schemas.
---
# CSV Validator
Instructions go here.
"""
    valid, errors, meta = ValidationEngine.validate_level_1_spec(valid_skill)
    assert valid is True
    assert len(errors) == 0
    assert meta["name"] == "csv-validator"

    # Valid Skill: 1-character name (allowed by Agent Skills spec)
    valid_1char = "---\nname: a\ndescription: Single letter skill name.\n---\n# A"
    valid, errors, _ = ValidationEngine.validate_level_1_spec(valid_1char)
    assert valid is True

    # Invalid Skill: Missing frontmatter
    invalid_no_fm = "# Just Markdown\nNo frontmatter here."
    valid, errors, _ = ValidationEngine.validate_level_1_spec(invalid_no_fm)
    assert valid is False
    assert any("frontmatter" in e.lower() for e in errors)

    # Invalid Skill: Consecutive hyphens (violates spec)
    invalid_consecutive = "---\nname: csv--validator\ndescription: Desc.\n---\n# Body"
    valid, errors, _ = ValidationEngine.validate_level_1_spec(invalid_consecutive)
    assert valid is False

    # Invalid Skill: Name with uppercase and spaces
    invalid_name = """---
name: Invalid Name With Spaces!
description: A description.
---
# Body
"""
    valid, errors, _ = ValidationEngine.validate_level_1_spec(invalid_name)
    assert valid is False
    assert any("naming standard" in e.lower() for e in errors)

    # Issue2Skill Security Validation: Dangerous path traversal
    invalid_path = """---
name: safe-name
description: A description.
---
# Body
Check this file: ../../etc/passwd
"""
    sec_valid, sec_errors = ValidationEngine.validate_security(invalid_path)
    assert sec_valid is False
    assert any("parent directory" in e.lower() for e in sec_errors)


def test_level_2_traceability_validation():
    """Checks requirement-to-instruction and requirement-to-test mapping."""
    req1 = Requirement(id="REQ-001", statement="Must parse CSV rows", type="FUNCTIONAL")
    req2 = Requirement(id="REQ-002", statement="Must emit JSON output", type="FUNCTIONAL")

    skill_ir = SkillIR(
        requirements=[req1, req2],
        traceability=TraceabilityMatrix(
            mappings={
                "REQ-001": {"instructions": ["INS-001"], "tests": ["TEST-001"]}
                # REQ-002 is unmapped
            }
        )
    )

    valid, errors, metrics = ValidationEngine.validate_level_2_traceability(skill_ir)
    assert valid is False
    assert metrics["traceability_coverage"] == 0.5
    assert any("uncovered requirement" in e.lower() for e in errors)

    # Map REQ-002
    skill_ir.traceability.mappings["REQ-002"] = {"instructions": ["INS-002"], "tests": ["TEST-002"]}
    valid, errors, metrics = ValidationEngine.validate_level_2_traceability(skill_ir)
    assert valid is True
    assert metrics["traceability_coverage"] == 1.0


def test_end_to_end_pipeline_execution(orchestrator):
    """Validates complete compilation from issue to validated skill."""
    result = orchestrator.process_issue(
        issue_id="issue-test-01",
        title="Generate release notes from git commits",
        body="Extract commit messages, categorize them into features and bugfixes, and write release_notes.md."
    )
    assert result["final_state"] == "VALIDATED"
    assert "skill_ir" in result
    assert "skill_md" in result
    assert len(result["test_results"]) > 0
    for tr in result["test_results"]:
        assert tr["status"] == "PASSED"
