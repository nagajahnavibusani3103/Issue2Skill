"""
Tests for Phase 2: Interactive Human-in-the-Loop Ambiguity and Conflict Resolution
- Validates pipeline pausing on BLOCKED_AMBIGUITY
- Validates resuming pipeline with clarification to VALIDATED
- Validates pipeline pausing on BLOCKED_CONFLICT
- Validates resuming pipeline with keep_a, keep_b, and merge strategies
- Validates FastAPI endpoints
"""

import pytest
from fastapi.testclient import TestClient
from backend.services import TursoClient, LLMClient, DockerExecutionSandbox, SkillHarness
from backend.pipeline import PipelineOrchestrator, SkillIR
from backend.main import app, ACTIVE_PIPELINES


@pytest.fixture
def mock_orchestrator():
    turso = TursoClient(auth_token="")
    llm = LLMClient()
    sandbox = DockerExecutionSandbox(mock_mode=True)
    harness = SkillHarness(sandbox=sandbox)
    return PipelineOrchestrator(db=turso, llm=llm, harness=harness)


def test_ambiguity_blocking_and_interactive_resolution(mock_orchestrator):
    # 1. Start pipeline with deliberately ambiguous issue
    res = mock_orchestrator.process_issue(
        issue_id="issue-amb-001",
        title="Make the caching layer faster",
        body="The current cache is slow. Optimize the caching layer and speed up performance across the system."
    )
    assert res["final_state"] == "BLOCKED_AMBIGUITY"
    assert res["skill_ir"].classification == "AMBIGUOUS"
    assert len(res["skill_ir"].ambiguities) > 0
    assert res["skill_ir"].ambiguities[0].is_blocking is True

    # 2. Provide human clarification to resolve ambiguity
    resumed = mock_orchestrator.resume_pipeline_with_ambiguity_resolution(
        pipeline_state=res,
        ambiguity_id=res["skill_ir"].ambiguities[0].id,
        user_resolution="Use in-memory LRU cache with max 1000 items and 60s TTL"
    )
    assert resumed["final_state"] == "VALIDATED"
    assert resumed["skill_ir"].ambiguities[0].is_blocking is False
    assert resumed["skill_ir"].ambiguities[0].user_resolution is not None
    assert "Clarification" in resumed["skill_ir"].requirements[0].statement
    assert "SKILL.md" in resumed["skill_md"] or "name:" in resumed["skill_md"]
    assert len(resumed["test_results"]) > 0


def test_conflict_blocking_and_interactive_resolution_merge(mock_orchestrator):
    # 1. Start pipeline with conflicting requirements
    res = mock_orchestrator.process_issue(
        issue_id="issue-conf-001",
        title="In-memory cache with durable persistent recovery across reboots",
        body="The skill must store state purely in-memory without disk writes, but also require durable persistent recovery across reboots."
    )
    assert res["final_state"] == "BLOCKED_CONFLICT"
    assert res["skill_ir"].classification == "CONFLICTING"
    assert len(res["skill_ir"].conflicts) > 0
    assert res["skill_ir"].conflicts[0].is_blocking is True

    # 2. Resolve conflict using merge strategy
    resumed = mock_orchestrator.resume_pipeline_with_conflict_resolution(
        pipeline_state=res,
        conflict_id=res["skill_ir"].conflicts[0].id,
        resolution_strategy="merge",
        user_resolution="Use in-memory volatile memory with async background snapshotting to disk"
    )
    assert resumed["final_state"] == "VALIDATED"
    assert resumed["skill_ir"].conflicts[0].is_blocking is False
    assert len(resumed["skill_ir"].requirements) == 1
    assert "Merged resolution" in resumed["skill_ir"].requirements[0].statement


def test_conflict_resolution_strategies(mock_orchestrator):
    # Test keep_a strategy
    res = mock_orchestrator.process_issue(
        issue_id="issue-conf-002",
        title="In-memory cache with durable persistent recovery across reboots",
        body="Contradictory constraints test."
    )
    resumed_a = mock_orchestrator.resume_pipeline_with_conflict_resolution(
        pipeline_state=res,
        conflict_id="CONF-001",
        resolution_strategy="keep_a"
    )
    assert resumed_a["final_state"] == "VALIDATED"
    assert any(r.id == "REQ-001" for r in resumed_a["skill_ir"].requirements)
    assert not any(r.id == "REQ-002" for r in resumed_a["skill_ir"].requirements)

    # Test keep_b strategy
    res2 = mock_orchestrator.process_issue(
        issue_id="issue-conf-003",
        title="In-memory cache with durable persistent recovery across reboots",
        body="Contradictory constraints test."
    )
    resumed_b = mock_orchestrator.resume_pipeline_with_conflict_resolution(
        pipeline_state=res2,
        conflict_id="CONF-001",
        resolution_strategy="keep_b"
    )
    assert resumed_b["final_state"] == "VALIDATED"
    assert any(r.id == "REQ-002" for r in resumed_b["skill_ir"].requirements)
    assert not any(r.id == "REQ-001" for r in resumed_b["skill_ir"].requirements)


def test_fastapi_interactive_endpoints(monkeypatch):
    monkeypatch.setattr("backend.main.sandbox.mock_mode", True)
    client = TestClient(app)
    
    # 1. Start pipeline via API that triggers ambiguity
    resp = client.post("/api/v1/pipelines/start", json={
        "issue_id": "test-api-amb-1",
        "title": "Make the caching layer faster",
        "body": "Optimize performance without clear metrics"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["final_state"] == "BLOCKED_AMBIGUITY"
    pipeline_id = data["pipeline_id"]

    # 2. Call resolve-ambiguity endpoint
    resolve_resp = client.post(f"/api/v1/pipelines/{pipeline_id}/resolve-ambiguity", json={
        "ambiguity_id": "auto",
        "resolution": "Cap LRU cache at 50MB with 30s eviction window"
    })
    assert resolve_resp.status_code == 200
    res_data = resolve_resp.json()
    assert res_data["final_state"] == "VALIDATED"

    # 3. Start pipeline via API that triggers conflict
    resp2 = client.post("/api/v1/pipelines/start", json={
        "issue_id": "test-api-conf-1",
        "title": "In-memory cache with durable persistent recovery across reboots",
        "body": "Purely transient in-memory but durable persistent recovery"
    })
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["final_state"] == "BLOCKED_CONFLICT"
    pipeline_id2 = data2["pipeline_id"]

    # 4. Call resolve-conflict endpoint
    resolve_conf_resp = client.post(f"/api/v1/pipelines/{pipeline_id2}/resolve-conflict", json={
        "conflict_id": "auto",
        "resolution_strategy": "merge",
        "resolution": "Write-ahead log to disk for crash recovery"
    })
    assert resolve_conf_resp.status_code == 200
    conf_data = resolve_conf_resp.json()
    assert conf_data["final_state"] == "VALIDATED"
