/**
 * Issue2Skill — Frontend API Client & TypeScript Interfaces
 * Strictly typed against the backend SkillIR and State Machine schemas.
 */

export interface Requirement {
  id: string;
  statement: string;
  type: 'FUNCTIONAL' | 'NON_FUNCTIONAL' | 'CONSTRAINT';
  priority: 'HIGH' | 'MEDIUM' | 'LOW';
  confidence: number;
  constraints: string[];
  acceptance_criteria: string[];
  ambiguity_refs: string[];
  conflict_refs: string[];
}

export interface Ambiguity {
  id: string;
  affected_req: string;
  description: string;
  is_blocking: boolean;
  resolution_assumption?: string;
  user_resolution?: string;
}

export interface Conflict {
  id: string;
  req_a: string;
  req_b: string;
  description: string;
  is_blocking: boolean;
  user_resolution?: string;
}

export interface SkillInstruction {
  id: string;
  title: string;
  content: string;
  requirement_refs: string[];
}

export interface SkillPlan {
  name: string;
  description: string;
  instructions: SkillInstruction[];
  artifacts: string[];
}

export interface TestAssertion {
  type: string;
  expected: any;
  file?: string;
}

export interface TestCase {
  id: string;
  requirement_refs: string[];
  type: string;
  task_prompt: string;
  assertions: TestAssertion[];
  timeout_seconds: number;
}

export interface TraceabilityMatrix {
  mappings: Record<string, { instructions: string[]; tests: string[] }>;
}

export interface SkillIR {
  skill_ir_version: string;
  issue_source: string;
  issue_title: string;
  issue_hash: string;
  classification: 'SKILL_COMPATIBLE' | 'AMBIGUOUS' | 'CONFLICTING' | 'UNSUPPORTED';
  unsupported_reason?: string;
  requirements: Requirement[];
  ambiguities: Ambiguity[];
  conflicts: Conflict[];
  assumptions: string[];
  skill_plan?: SkillPlan;
  tests: TestCase[];
  traceability: TraceabilityMatrix;
  spec_validation_passed: boolean;
}

export interface PipelineEvent {
  timestamp: number;
  state: string;
  details: string;
  terminal?: boolean;
}

export interface TestRunResult {
  test_id: string;
  status: 'PASSED' | 'FAILED' | 'TIMEOUT' | 'SECURITY_BLOCKED';
  exit_code: number;
  stdout: string;
  stderr: string;
  duration_ms: number;
  assertions: {
    assertion: TestAssertion;
    passed: boolean;
    message: string;
  }[];
}

export interface PipelineResult {
  pipeline_id: string;
  issue_id: string;
  final_state: string;
  duration_ms: number;
  events: PipelineEvent[];
  skill_ir?: SkillIR;
  skill_md?: string;
  test_results?: TestRunResult[];
  repair_attempts?: number;
  analysis?: any;
  errors?: string[];
}

export interface SystemHealth {
  status: string;
  timestamp: number;
  services: {
    database: string;
    model_provider: string;
    sandbox: string;
    docker_required: boolean;
  };
}

const API_BASE = '/api/v1';

export async function fetchHealth(): Promise<SystemHealth> {
  const res = await fetch(`${API_BASE}/health`);
  return res.json();
}

export async function importIssue(data: { url?: string; title?: string; body?: string }): Promise<any> {
  const res = await fetch(`${API_BASE}/issues/import`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || 'Failed to import issue');
  }
  return res.json();
}

export async function startPipeline(payload: { issue_id: string; title: string; body: string; source_url?: string }): Promise<PipelineResult> {
  const res = await fetch(`${API_BASE}/pipelines/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || 'Pipeline execution failed');
  }
  return res.json();
}

export async function getPipelineStatus(pipelineId: string): Promise<PipelineResult> {
  const res = await fetch(`${API_BASE}/pipelines/${pipelineId}/status`);
  if (!res.ok) throw new Error('Failed to fetch status');
  return res.json();
}

export async function resolvePipelineAmbiguity(
  pipelineId: string,
  ambiguityId: string,
  resolution: string
): Promise<PipelineResult> {
  const res = await fetch(`${API_BASE}/pipelines/${pipelineId}/resolve-ambiguity`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ambiguity_id: ambiguityId, resolution }),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || 'Failed to resolve ambiguity');
  }
  return res.json();
}

export async function resolvePipelineConflict(
  pipelineId: string,
  conflictId: string,
  resolutionStrategy: 'keep_a' | 'keep_b' | 'merge',
  resolution?: string
): Promise<PipelineResult> {
  const res = await fetch(`${API_BASE}/pipelines/${pipelineId}/resolve-conflict`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      conflict_id: conflictId,
      resolution_strategy: resolutionStrategy,
      resolution: resolution || '',
    }),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || 'Failed to resolve conflict');
  }
  return res.json();
}

export async function resolveAmbiguity(reqId: string, resolution: string): Promise<any> {
  const res = await fetch(`${API_BASE}/requirements/${reqId}/resolve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ resolution }),
  });
  return res.json();
}

export async function exportPR(skillId: string, payload: { repo_url: string; skill_name: string }): Promise<any> {
  const res = await fetch(`${API_BASE}/skills/${skillId}/export-pr`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return res.json();
}

export function subscribePipelineEvents(pipelineId: string, onEvent: (evt: PipelineEvent) => void): () => void {
  const es = new EventSource(`${API_BASE}/pipelines/${pipelineId}/events`);
  es.onmessage = (e) => {
    try {
      const data: PipelineEvent = JSON.parse(e.data);
      onEvent(data);
      if (data.terminal) {
        es.close();
      }
    } catch (err) {
      console.error('SSE JSON parse error', err);
    }
  };
  es.onerror = () => {
    es.close();
  };
  return () => es.close();
}
