import React, { useState, useEffect } from 'react';
import Editor from '@monaco-editor/react';
import {
  ShieldCheck,
  Cpu,
  Database,
  Terminal,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Play,
  Download,
  GitPullRequest,
  RefreshCw,
  ExternalLink,
  Layers,
  ArrowRight,
  HelpCircle,
  GitMerge,
  Split
} from 'lucide-react';
import {
  fetchHealth,
  importIssue,
  startPipeline,
  exportPR,
  resolvePipelineAmbiguity,
  resolvePipelineConflict,
  SkillIR,
  PipelineResult,
  SystemHealth,
  PipelineEvent
} from './api';

const SAMPLE_PRESETS = [
  {
    label: "CSV Schema Validator",
    title: "Create a CSV Schema Validation Skill",
    body: "Build an agent skill that validates CSV column headers and data types against a user-defined JSON schema specification. Reject invalid formats gracefully."
  },
  {
    label: "Release Notes Compiler",
    title: "Generate Release Notes from Git Commits",
    body: "Parse conventional commit logs (feat, fix, docs), group them into categorised sections, and write a formatted release_notes.md document."
  },
  {
    label: "Ambiguous Spec (Needs Clarification)",
    title: "Make the caching layer faster",
    body: "The current cache is slow. Optimize the caching layer and speed up performance across the system without clear latency targets."
  },
  {
    label: "Conflicting Spec (Needs Resolution)",
    title: "Implement purely in-memory cache with durable persistent recovery across reboots",
    body: "The skill must store all state in purely transient volatile in-memory storage without disk access, but also require durable persistent recovery across reboots by saving to disk."
  },
  {
    label: "Non-Skill Bug (Unsupported)",
    title: "Fix CSS React button alignment bug",
    body: "The submit button on the login form is misaligned by 4px on Safari mobile viewports."
  }
];

export default function App() {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [inputUrl, setInputUrl] = useState('');
  const [inputTitle, setInputTitle] = useState(SAMPLE_PRESETS[0].title);
  const [inputBody, setInputBody] = useState(SAMPLE_PRESETS[0].body);
  const [isUrlMode, setIsUrlMode] = useState(false);
  const [loading, setLoading] = useState(false);
  const [activePipeline, setActivePipeline] = useState<PipelineResult | null>(null);
  const [selectedReqId, setSelectedReqId] = useState<string | null>(null);
  const [leftTab, setLeftTab] = useState<'requirements' | 'gates'>('requirements');

  // Modals state
  const [prModalOpen, setPrModalOpen] = useState(false);
  const [prResult, setPrResult] = useState<any | null>(null);

  const [ambiguityModalOpen, setAmbiguityModalOpen] = useState(false);
  const [selectedAmbiguityId, setSelectedAmbiguityId] = useState<string>('auto');
  const [ambiguityResolutionInput, setAmbiguityResolutionInput] = useState('');

  const [conflictModalOpen, setConflictModalOpen] = useState(false);
  const [selectedConflictId, setSelectedConflictId] = useState<string>('auto');
  const [conflictStrategy, setConflictStrategy] = useState<'keep_a' | 'keep_b' | 'merge'>('merge');
  const [conflictResolutionInput, setConflictResolutionInput] = useState('');

  useEffect(() => {
    fetchHealth().then(setHealth).catch(() => {});
  }, []);

  const handleRunPipeline = async () => {
    setLoading(true);
    setPrResult(null);
    try {
      let issueData;
      if (isUrlMode && inputUrl) {
        issueData = await importIssue({ url: inputUrl });
      } else {
        issueData = await importIssue({ title: inputTitle, body: inputBody });
      }

      const res = await startPipeline({
        issue_id: issueData.issue_id,
        title: issueData.title,
        body: issueData.body,
        source_url: issueData.source_url || ""
      });

      setActivePipeline(res);
      if (res.skill_ir?.requirements?.length) {
        setSelectedReqId(res.skill_ir.requirements[0].id);
      }

      // Check for human-in-the-loop blocking gates
      if (res.final_state === 'BLOCKED_AMBIGUITY') {
        const firstAmb = res.skill_ir?.ambiguities?.find(a => a.is_blocking);
        if (firstAmb) {
          setSelectedAmbiguityId(firstAmb.id);
        }
        setAmbiguityModalOpen(true);
        setLeftTab('gates');
      } else if (res.final_state === 'BLOCKED_CONFLICT') {
        const firstConf = res.skill_ir?.conflicts?.find(c => c.is_blocking);
        if (firstConf) {
          setSelectedConflictId(firstConf.id);
        }
        setConflictModalOpen(true);
        setLeftTab('gates');
      } else {
        setLeftTab('requirements');
      }
    } catch (err: any) {
      alert(`Pipeline error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleResolveAmbiguity = async () => {
    if (!activePipeline) return;
    if (!ambiguityResolutionInput.trim()) {
      alert("Please provide a clarification statement to resolve ambiguity.");
      return;
    }
    setLoading(true);
    try {
      const res = await resolvePipelineAmbiguity(
        activePipeline.pipeline_id,
        selectedAmbiguityId,
        ambiguityResolutionInput
      );
      setActivePipeline(res);
      setAmbiguityModalOpen(false);
      setAmbiguityResolutionInput('');
      if (res.final_state === 'VALIDATED') {
        setLeftTab('requirements');
      }
    } catch (err: any) {
      alert(`Failed to resolve ambiguity: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleResolveConflict = async () => {
    if (!activePipeline) return;
    setLoading(true);
    try {
      const res = await resolvePipelineConflict(
        activePipeline.pipeline_id,
        selectedConflictId,
        conflictStrategy,
        conflictResolutionInput || `Resolved using ${conflictStrategy} strategy`
      );
      setActivePipeline(res);
      setConflictModalOpen(false);
      setConflictResolutionInput('');
      if (res.final_state === 'VALIDATED') {
        setLeftTab('requirements');
      }
    } catch (err: any) {
      alert(`Failed to resolve conflict: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleExportPR = async () => {
    if (!activePipeline?.skill_ir?.skill_plan) return;
    try {
      const res = await exportPR(activePipeline.skill_ir.skill_plan.name, {
        repo_url: "https://github.com/nagajahnavibusani3103/Issue2Skill",
        skill_name: activePipeline.skill_ir.skill_plan.name
      });
      setPrResult(res);
      setPrModalOpen(true);
    } catch (err: any) {
      alert(`Export PR failed: ${err.message}`);
    }
  };

  const handleDownloadSkill = () => {
    if (!activePipeline?.skill_md) return;
    const blob = new Blob([activePipeline.skill_md], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'SKILL.md';
    a.click();
    URL.revokeObjectURL(url);
  };

  const skillIr = activePipeline?.skill_ir;
  const currentSkillMd = activePipeline?.skill_md || "# Run pipeline to generate Agent Skill";
  const blockingAmbiguities = skillIr?.ambiguities?.filter(a => a.is_blocking) || [];
  const blockingConflicts = skillIr?.conflicts?.filter(c => c.is_blocking) || [];
  const totalGateItems = (skillIr?.ambiguities?.length || 0) + (skillIr?.conflicts?.length || 0);

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-[#0d1117] text-[#c9d1d9] font-sans">
      {/* 1. TOP STATUS & NAVIGATION BAR */}
      <header className="h-14 border-b border-[#30363d] bg-[#161b22] px-5 flex items-center justify-between select-none">
        <div className="flex items-center gap-3">
          <div className="bg-[#238636] p-1.5 rounded-md text-white">
            <Layers className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-semibold text-white tracking-wide text-sm">ISSUE2SKILL</span>
              <span className="text-[11px] bg-[#30363d] px-2 py-0.5 rounded text-[#8b949e] font-mono">v1.0.0</span>
            </div>
            <div className="text-[11px] text-[#8b949e]">Compiler: GitHub Issue &rarr; Verified Agent Skill</div>
          </div>
        </div>

        {/* System Health Indicators */}
        <div className="flex items-center gap-4 text-xs font-mono">
          <div className="flex items-center gap-1.5 bg-[#0d1117] px-2.5 py-1 rounded border border-[#30363d]">
            <Database className="w-3.5 h-3.5 text-[#3fb950]" />
            <span className="text-[#8b949e]">DB:</span>
            <span className="text-white">{health?.services?.database || "CONNECTING..."}</span>
          </div>
          <div className="flex items-center gap-1.5 bg-[#0d1117] px-2.5 py-1 rounded border border-[#30363d]">
            <Cpu className="w-3.5 h-3.5 text-[#58a6ff]" />
            <span className="text-[#8b949e]">Model:</span>
            <span className="text-white">{health?.services?.model_provider || "Qwen3-8B"}</span>
          </div>
          <div className="flex items-center gap-1.5 bg-[#0d1117] px-2.5 py-1 rounded border border-[#30363d]">
            <ShieldCheck className="w-3.5 h-3.5 text-[#d29922]" />
            <span className="text-[#8b949e]">Sandbox:</span>
            <span className="text-white">{health?.services?.sandbox || "DOCKER_SANDBOX"}</span>
          </div>
        </div>
      </header>

      {/* 2. PIPELINE PROGRESS STEPPER */}
      <div className="border-b border-[#30363d] bg-[#0d1117] px-5 py-2.5 flex items-center justify-between text-xs">
        <div className="flex items-center gap-2 overflow-x-auto">
          {[
            { id: "INGEST", label: "1. Issue Ingestion" },
            { id: "CLASSIFY", label: "2. Eligibility & Extraction" },
            { id: "SKILLIR", label: "3. SkillIR Plan" },
            { id: "SPEC", label: "4. Spec Validation" },
            { id: "EXECUTE", label: "5. Sandbox Behavioral Run" },
            { id: "VALIDATED", label: "6. Validated Skill" }
          ].map((step, idx) => {
            const isCompleted = activePipeline?.final_state === "VALIDATED";
            const isBlocked = activePipeline?.final_state === "BLOCKED_AMBIGUITY" || activePipeline?.final_state === "BLOCKED_CONFLICT";
            const isCurrent = loading || (idx === 1 && isBlocked);
            return (
              <React.Fragment key={step.id}>
                <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded font-medium ${
                  isCompleted ? "bg-[#238636]/10 text-[#3fb950] border border-[#238636]/30" :
                  isBlocked && idx === 1 ? "bg-[#d29922]/15 text-[#d29922] border border-[#d29922]/40" :
                  isCurrent ? "bg-[#58a6ff]/10 text-[#58a6ff] border border-[#58a6ff]/30 animate-pulse" :
                  "text-[#8b949e]"
                }`}>
                  {isCompleted ? <CheckCircle2 className="w-3.5 h-3.5 text-[#3fb950]" /> :
                   isBlocked && idx === 1 ? <AlertTriangle className="w-3.5 h-3.5 text-[#d29922]" /> :
                   <span className="w-2 h-2 rounded-full bg-[#30363d]" />}
                  <span>{step.label}</span>
                </div>
                {idx < 5 && <ArrowRight className="w-3 h-3 text-[#30363d]" />}
              </React.Fragment>
            );
          })}
        </div>

        {activePipeline && (
          <div className="flex items-center gap-3 font-mono text-xs">
            <span className="text-[#8b949e]">State:</span>
            <span className={`px-2 py-0.5 rounded font-bold ${
              activePipeline.final_state === "VALIDATED" ? "bg-[#238636] text-white" :
              activePipeline.final_state === "BLOCKED_AMBIGUITY" ? "bg-[#d29922] text-black" :
              activePipeline.final_state === "BLOCKED_CONFLICT" ? "bg-[#f85149] text-white" :
              activePipeline.final_state === "UNSUPPORTED_ISSUE" ? "bg-[#6e7681] text-white" :
              "bg-[#f85149] text-white"
            }`}>
              {activePipeline.final_state}
            </span>
            <span className="text-[#8b949e]">{activePipeline.duration_ms}ms</span>
          </div>
        )}
      </div>

      {/* HUMAN-IN-THE-LOOP INTERACTIVE BANNERS */}
      {activePipeline?.final_state === 'BLOCKED_AMBIGUITY' && (
        <div className="bg-[#d29922]/15 border-b border-[#d29922]/40 px-5 py-2 flex items-center justify-between text-xs">
          <div className="flex items-center gap-2 text-[#d29922]">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            <span>
              <strong>Pipeline Blocked on Ambiguity:</strong> Human-in-the-loop clarification required to proceed.
            </span>
          </div>
          <button
            onClick={() => setAmbiguityModalOpen(true)}
            className="bg-[#d29922] hover:bg-[#e3b341] text-black font-semibold px-3 py-1 rounded text-xs transition flex items-center gap-1.5"
          >
            <HelpCircle className="w-3.5 h-3.5" />
            Resolve Ambiguity &rarr;
          </button>
        </div>
      )}

      {activePipeline?.final_state === 'BLOCKED_CONFLICT' && (
        <div className="bg-[#f85149]/15 border-b border-[#f85149]/40 px-5 py-2 flex items-center justify-between text-xs">
          <div className="flex items-center gap-2 text-[#f85149]">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            <span>
              <strong>Pipeline Blocked on Conflicting Requirements:</strong> Resolution strategy required to reconcile contradictory specs.
            </span>
          </div>
          <button
            onClick={() => setConflictModalOpen(true)}
            className="bg-[#f85149] hover:bg-[#da3633] text-white font-semibold px-3 py-1 rounded text-xs transition flex items-center gap-1.5"
          >
            <Split className="w-3.5 h-3.5" />
            Resolve Conflict &rarr;
          </button>
        </div>
      )}

      {/* 3. MAIN THREE-PANE STUDIO */}
      <div className="flex-1 flex overflow-hidden">
        {/* LEFT PANE: Issue & Requirements / Gates */}
        <div className="w-[360px] border-r border-[#30363d] flex flex-col bg-[#161b22]">
          <div className="p-3 border-b border-[#30363d] flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-[#8b949e]">Source Issue</span>
            <div className="flex items-center gap-1 overflow-x-auto max-w-[200px]">
              {SAMPLE_PRESETS.map((p, i) => (
                <button
                  key={i}
                  onClick={() => {
                    setInputTitle(p.title);
                    setInputBody(p.body);
                    setIsUrlMode(false);
                  }}
                  className="text-[10px] bg-[#21262d] hover:bg-[#30363d] text-[#c9d1d9] px-2 py-0.5 rounded transition shrink-0"
                  title={p.title}
                >
                  Preset {i+1}
                </button>
              ))}
            </div>
          </div>

          <div className="p-3 border-b border-[#30363d] flex flex-col gap-2">
            <div className="flex gap-2 text-xs">
              <button
                onClick={() => setIsUrlMode(false)}
                className={`flex-1 py-1 rounded text-center ${!isUrlMode ? "bg-[#21262d] text-white font-medium" : "text-[#8b949e]"}`}
              >
                Direct Text
              </button>
              <button
                onClick={() => setIsUrlMode(true)}
                className={`flex-1 py-1 rounded text-center ${isUrlMode ? "bg-[#21262d] text-white font-medium" : "text-[#8b949e]"}`}
              >
                GitHub URL
              </button>
            </div>

            {isUrlMode ? (
              <input
                type="text"
                placeholder="https://github.com/owner/repo/issues/1"
                value={inputUrl}
                onChange={(e) => setInputUrl(e.target.value)}
                className="w-full bg-[#0d1117] border border-[#30363d] rounded px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-[#58a6ff]"
              />
            ) : (
              <>
                <input
                  type="text"
                  placeholder="Issue title..."
                  value={inputTitle}
                  onChange={(e) => setInputTitle(e.target.value)}
                  className="w-full bg-[#0d1117] border border-[#30363d] rounded px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-[#58a6ff]"
                />
                <textarea
                  rows={3}
                  placeholder="Issue description..."
                  value={inputBody}
                  onChange={(e) => setInputBody(e.target.value)}
                  className="w-full bg-[#0d1117] border border-[#30363d] rounded px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-[#58a6ff] resize-none"
                />
              </>
            )}

            <button
              onClick={handleRunPipeline}
              disabled={loading}
              className="w-full bg-[#238636] hover:bg-[#2ea043] disabled:opacity-50 text-white font-semibold py-1.5 rounded text-xs flex items-center justify-center gap-1.5 transition"
            >
              {loading ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
              {loading ? "Processing Pipeline..." : "Compile to Skill"}
            </button>
          </div>

          {/* Subtabs: Extracted Requirements vs Ambiguities/Conflicts */}
          <div className="flex border-b border-[#30363d] bg-[#0d1117] text-xs">
            <button
              onClick={() => setLeftTab('requirements')}
              className={`flex-1 py-1.5 px-3 text-center border-b-2 font-medium transition ${
                leftTab === 'requirements'
                  ? 'border-[#58a6ff] text-white bg-[#161b22]'
                  : 'border-transparent text-[#8b949e] hover:text-[#c9d1d9]'
              }`}
            >
              Requirements ({skillIr?.requirements?.length || 0})
            </button>
            <button
              onClick={() => setLeftTab('gates')}
              className={`flex-1 py-1.5 px-3 text-center border-b-2 font-medium transition flex items-center justify-center gap-1.5 ${
                leftTab === 'gates'
                  ? 'border-[#d29922] text-white bg-[#161b22]'
                  : 'border-transparent text-[#8b949e] hover:text-[#c9d1d9]'
              }`}
            >
              <span>Gates</span>
              {totalGateItems > 0 && (
                <span className={`text-[10px] px-1.5 py-0.2 rounded-full font-bold ${
                  blockingAmbiguities.length + blockingConflicts.length > 0
                    ? 'bg-[#d29922] text-black'
                    : 'bg-[#30363d] text-[#c9d1d9]'
                }`}>
                  {totalGateItems}
                </span>
              )}
            </button>
          </div>

          {/* TAB 1: REQUIREMENTS */}
          {leftTab === 'requirements' && (
            <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-2.5">
              {skillIr?.requirements?.map((req) => {
                const isSelected = selectedReqId === req.id;
                const mapping = skillIr.traceability?.mappings?.[req.id];
                return (
                  <div
                    key={req.id}
                    onClick={() => setSelectedReqId(req.id)}
                    className={`p-2.5 rounded border text-xs cursor-pointer transition ${
                      isSelected ? "bg-[#21262d] border-[#58a6ff]" : "bg-[#0d1117] border-[#30363d] hover:border-[#8b949e]"
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-mono font-bold text-[#58a6ff]">{req.id}</span>
                      <div className="flex gap-1">
                        <span className="text-[10px] px-1.5 py-0.2 rounded bg-[#30363d] text-[#c9d1d9]">{req.type}</span>
                        <span className="text-[10px] px-1.5 py-0.2 rounded bg-[#30363d] text-[#d29922]">{req.priority}</span>
                      </div>
                    </div>
                    <p className="text-[#c9d1d9] leading-relaxed">{req.statement}</p>

                    {/* Traceability badge */}
                    {mapping && (
                      <div className="mt-2 pt-2 border-t border-[#21262d] flex items-center gap-2 text-[10px] font-mono text-[#8b949e]">
                        <span>&rarr; {mapping.instructions?.join(", ") || "No INS"}</span>
                        <span>&rarr; {mapping.tests?.join(", ") || "No TEST"}</span>
                      </div>
                    )}
                  </div>
                );
              })}

              {(!skillIr?.requirements || skillIr.requirements.length === 0) && (
                <div className="text-center py-8 text-[#8b949e] text-xs">
                  No requirements extracted yet. Click "Compile to Skill" above.
                </div>
              )}
            </div>
          )}

          {/* TAB 2: AMBIGUITY & CONFLICT GATES */}
          {leftTab === 'gates' && (
            <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-3">
              <div>
                <span className="text-[11px] font-semibold uppercase tracking-wider text-[#8b949e] block mb-2">
                  Ambiguities ({skillIr?.ambiguities?.length || 0})
                </span>
                {skillIr?.ambiguities?.map((amb) => (
                  <div key={amb.id} className="p-2.5 mb-2 bg-[#0d1117] border border-[#30363d] rounded text-xs flex flex-col gap-1.5">
                    <div className="flex items-center justify-between">
                      <span className="font-mono font-bold text-[#d29922]">{amb.id}</span>
                      <span className={`text-[10px] px-1.5 py-0.2 rounded font-bold ${
                        amb.is_blocking ? "bg-[#d29922] text-black" : "bg-[#238636] text-white"
                      }`}>
                        {amb.is_blocking ? "BLOCKING" : "RESOLVED"}
                      </span>
                    </div>
                    <div className="text-[#8b949e] text-[11px]">Affected: <span className="font-mono text-white">{amb.affected_req}</span></div>
                    <p className="text-[#c9d1d9]">{amb.description}</p>
                    {amb.user_resolution && (
                      <div className="mt-1 p-1.5 bg-[#161b22] border border-[#30363d] rounded text-[11px] text-[#3fb950]">
                        &check; Resolution: {amb.user_resolution}
                      </div>
                    )}
                    {amb.is_blocking && (
                      <button
                        onClick={() => {
                          setSelectedAmbiguityId(amb.id);
                          setAmbiguityModalOpen(true);
                        }}
                        className="mt-1 bg-[#d29922]/20 hover:bg-[#d29922]/30 text-[#d29922] border border-[#d29922]/40 rounded py-1 px-2 text-[11px] font-medium transition text-center"
                      >
                        Clarify & Resume
                      </button>
                    )}
                  </div>
                ))}
                {(!skillIr?.ambiguities || skillIr.ambiguities.length === 0) && (
                  <div className="text-[#8b949e] text-xs italic">No ambiguities detected.</div>
                )}
              </div>

              <div className="border-t border-[#30363d] pt-3">
                <span className="text-[11px] font-semibold uppercase tracking-wider text-[#8b949e] block mb-2">
                  Conflicts ({skillIr?.conflicts?.length || 0})
                </span>
                {skillIr?.conflicts?.map((conf) => (
                  <div key={conf.id} className="p-2.5 mb-2 bg-[#0d1117] border border-[#30363d] rounded text-xs flex flex-col gap-1.5">
                    <div className="flex items-center justify-between">
                      <span className="font-mono font-bold text-[#f85149]">{conf.id}</span>
                      <span className={`text-[10px] px-1.5 py-0.2 rounded font-bold ${
                        conf.is_blocking ? "bg-[#f85149] text-white" : "bg-[#238636] text-white"
                      }`}>
                        {conf.is_blocking ? "BLOCKING" : "RESOLVED"}
                      </span>
                    </div>
                    <div className="text-[#8b949e] text-[11px]">
                      Collision: <span className="font-mono text-white">{conf.req_a}</span> &harr; <span className="font-mono text-white">{conf.req_b}</span>
                    </div>
                    <p className="text-[#c9d1d9]">{conf.description}</p>
                    {conf.user_resolution && (
                      <div className="mt-1 p-1.5 bg-[#161b22] border border-[#30363d] rounded text-[11px] text-[#3fb950]">
                        &check; Resolution: {conf.user_resolution}
                      </div>
                    )}
                    {conf.is_blocking && (
                      <button
                        onClick={() => {
                          setSelectedConflictId(conf.id);
                          setConflictModalOpen(true);
                        }}
                        className="mt-1 bg-[#f85149]/20 hover:bg-[#f85149]/30 text-[#f85149] border border-[#f85149]/40 rounded py-1 px-2 text-[11px] font-medium transition text-center"
                      >
                        Reconcile & Resume
                      </button>
                    )}
                  </div>
                ))}
                {(!skillIr?.conflicts || skillIr.conflicts.length === 0) && (
                  <div className="text-[#8b949e] text-xs italic">No conflicts detected.</div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* CENTER PANE: Skill Studio (Monaco Editor & Frontmatter Inspector) */}
        <div className="flex-1 flex flex-col bg-[#0d1117]">
          <div className="h-10 border-b border-[#30363d] bg-[#161b22] px-4 flex items-center justify-between text-xs">
            <div className="flex items-center gap-2 font-mono">
              <span className="text-[#58a6ff]">SKILL.md</span>
              {activePipeline?.skill_ir?.spec_validation_passed && (
                <span className="flex items-center gap-1 text-[11px] text-[#3fb950] bg-[#238636]/10 px-2 py-0.5 rounded border border-[#238636]/30">
                  <CheckCircle2 className="w-3 h-3" /> Level 1 Spec Validated
                </span>
              )}
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={handleDownloadSkill}
                disabled={!activePipeline?.skill_md}
                className="bg-[#21262d] hover:bg-[#30363d] disabled:opacity-40 text-xs px-2.5 py-1 rounded flex items-center gap-1.5 transition"
              >
                <Download className="w-3.5 h-3.5" />
                Download SKILL.md
              </button>
            </div>
          </div>

          <div className="flex-1 overflow-hidden">
            <Editor
              height="100%"
              theme="vs-dark"
              defaultLanguage="markdown"
              value={currentSkillMd}
              options={{
                readOnly: true,
                minimap: { enabled: false },
                fontSize: 13,
                wordWrap: 'on',
                lineNumbers: 'on',
                fontFamily: '"JetBrains Mono", monospace'
              }}
            />
          </div>
        </div>

        {/* RIGHT PANE: Test Execution & Verification Console */}
        <div className="w-[380px] border-l border-[#30363d] flex flex-col bg-[#161b22]">
          <div className="p-3 border-b border-[#30363d] flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Terminal className="w-4 h-4 text-[#58a6ff]" />
              <span className="text-xs font-semibold uppercase tracking-wider text-[#8b949e]">Behavioral Test Suite</span>
            </div>
            <span className="text-xs font-mono bg-[#21262d] px-2 py-0.5 rounded text-[#8b949e]">
              Level 3 Sandbox
            </span>
          </div>

          <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-2.5">
            {activePipeline?.test_results?.map((res, i) => (
              <div key={i} className="p-3 bg-[#0d1117] border border-[#30363d] rounded text-xs flex flex-col gap-2 font-mono">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-white">{res.test_id}</span>
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                    res.status === 'PASSED' ? 'bg-[#238636] text-white' :
                    res.status === 'TIMEOUT' ? 'bg-[#d29922] text-black' :
                    'bg-[#f85149] text-white'
                  }`}>
                    {res.status}
                  </span>
                </div>

                <div className="text-[11px] text-[#8b949e]">
                  Duration: {res.duration_ms}ms | Exit: {res.exit_code}
                </div>

                {/* Assertions */}
                <div className="flex flex-col gap-1 border-t border-[#21262d] pt-2">
                  {res.assertions?.map((ass, ai) => (
                    <div key={ai} className="flex items-start gap-1.5 text-[11px]">
                      {ass.passed ? (
                        <CheckCircle2 className="w-3.5 h-3.5 text-[#3fb950] shrink-0 mt-0.5" />
                      ) : (
                        <XCircle className="w-3.5 h-3.5 text-[#f85149] shrink-0 mt-0.5" />
                      )}
                      <span className={ass.passed ? "text-[#c9d1d9]" : "text-[#f85149]"}>
                        {ass.message}
                      </span>
                    </div>
                  ))}
                </div>

                {/* Stdout / Stderr logs snippet */}
                {res.stdout && (
                  <div className="mt-1 p-2 bg-[#161b22] border border-[#30363d] rounded text-[10px] text-[#8b949e] overflow-x-auto whitespace-pre">
                    {res.stdout.trim()}
                  </div>
                )}
              </div>
            ))}

            {(!activePipeline?.test_results || activePipeline.test_results.length === 0) && (
              <div className="text-center py-12 text-[#8b949e] text-xs">
                Run compiler to execute behavioral sandbox tests.
              </div>
            )}
          </div>

          {/* Action Bar */}
          <div className="p-3 border-t border-[#30363d] bg-[#161b22] flex gap-2">
            <button
              onClick={handleExportPR}
              disabled={activePipeline?.final_state !== "VALIDATED"}
              className="flex-1 bg-[#1f6feb] hover:bg-[#388bfd] disabled:opacity-40 text-white font-semibold py-1.5 rounded text-xs flex items-center justify-center gap-1.5 transition"
            >
              <GitPullRequest className="w-3.5 h-3.5" />
              Export to GitHub PR
            </button>
          </div>
        </div>
      </div>

      {/* 4. MODAL: AMBIGUITY RESOLUTION */}
      {ambiguityModalOpen && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-[#161b22] border border-[#d29922]/50 rounded-lg w-[560px] max-w-full p-5 shadow-2xl flex flex-col gap-4">
            <div className="flex items-center justify-between border-b border-[#30363d] pb-3">
              <div className="flex items-center gap-2 text-[#d29922]">
                <HelpCircle className="w-5 h-5" />
                <span className="font-semibold text-white text-sm">Human-in-the-Loop Ambiguity Clarification</span>
              </div>
              <button
                onClick={() => setAmbiguityModalOpen(false)}
                className="text-[#8b949e] hover:text-white text-lg font-bold"
              >
                &times;
              </button>
            </div>

            <div className="flex flex-col gap-3 text-xs">
              <p className="text-[#8b949e] leading-relaxed">
                The Issue2Skill compiler identified an underspecified requirement that prevents deterministic test synthesis.
                Provide human clarification below to resume the compilation pipeline.
              </p>

              {skillIr?.ambiguities?.map((amb) => (
                <div key={amb.id} className="p-3 bg-[#0d1117] border border-[#30363d] rounded flex flex-col gap-1.5">
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-[#58a6ff] font-bold">{amb.id}</span>
                    <span className="text-[#8b949e]">Target: {amb.affected_req}</span>
                  </div>
                  <div className="text-[#c9d1d9] font-medium">{amb.description}</div>
                </div>
              ))}

              <div className="flex flex-col gap-1.5 mt-2">
                <label className="text-[#8b949e] font-semibold uppercase tracking-wider text-[11px]">
                  Your Clarification / Concrete Specification:
                </label>
                <textarea
                  rows={3}
                  value={ambiguityResolutionInput}
                  onChange={(e) => setAmbiguityResolutionInput(e.target.value)}
                  placeholder="e.g., Use an in-memory LRU cache with max 1,000 items and TTL of 60 seconds. Evict oldest on overflow."
                  className="w-full bg-[#0d1117] border border-[#30363d] rounded p-2.5 text-xs text-white focus:outline-none focus:border-[#d29922]"
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2 border-t border-[#30363d]">
              <button
                onClick={() => setAmbiguityModalOpen(false)}
                className="px-3 py-1.5 rounded bg-[#21262d] hover:bg-[#30363d] text-xs font-medium text-white transition"
              >
                Cancel
              </button>
              <button
                onClick={handleResolveAmbiguity}
                disabled={loading || !ambiguityResolutionInput.trim()}
                className="px-4 py-1.5 rounded bg-[#d29922] hover:bg-[#e3b341] disabled:opacity-50 text-xs font-semibold text-black flex items-center gap-1.5 transition"
              >
                {loading ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5" />}
                Submit Clarification & Resume
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 5. MODAL: CONFLICT RESOLUTION */}
      {conflictModalOpen && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-[#161b22] border border-[#f85149]/50 rounded-lg w-[580px] max-w-full p-5 shadow-2xl flex flex-col gap-4">
            <div className="flex items-center justify-between border-b border-[#30363d] pb-3">
              <div className="flex items-center gap-2 text-[#f85149]">
                <Split className="w-5 h-5" />
                <span className="font-semibold text-white text-sm">Conflicting Requirements Reconciler</span>
              </div>
              <button
                onClick={() => setConflictModalOpen(false)}
                className="text-[#8b949e] hover:text-white text-lg font-bold"
              >
                &times;
              </button>
            </div>

            <div className="flex flex-col gap-3 text-xs">
              <p className="text-[#8b949e] leading-relaxed">
                The requirements contain mutually contradictory constraints. Select a resolution strategy to reconcile the specification and resume compilation.
              </p>

              {skillIr?.conflicts?.map((conf) => (
                <div key={conf.id} className="p-3 bg-[#0d1117] border border-[#30363d] rounded flex flex-col gap-2">
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-[#f85149] font-bold">{conf.id}</span>
                    <span className="text-[#8b949e]">Between {conf.req_a} &amp; {conf.req_b}</span>
                  </div>
                  <div className="text-[#c9d1d9]">{conf.description}</div>
                </div>
              ))}

              <div className="flex flex-col gap-2 mt-2">
                <span className="text-[#8b949e] font-semibold uppercase tracking-wider text-[11px]">
                  Resolution Strategy:
                </span>
                <div className="flex flex-col gap-1.5">
                  <label className="flex items-center gap-2 p-2 rounded border border-[#30363d] bg-[#0d1117] cursor-pointer hover:border-[#8b949e]">
                    <input
                      type="radio"
                      name="strategy"
                      value="keep_a"
                      checked={conflictStrategy === 'keep_a'}
                      onChange={() => setConflictStrategy('keep_a')}
                      className="text-[#58a6ff]"
                    />
                    <div>
                      <div className="font-medium text-white">Prioritize Requirement A</div>
                      <div className="text-[11px] text-[#8b949e]">Discards the conflicting secondary constraint in Requirement B.</div>
                    </div>
                  </label>

                  <label className="flex items-center gap-2 p-2 rounded border border-[#30363d] bg-[#0d1117] cursor-pointer hover:border-[#8b949e]">
                    <input
                      type="radio"
                      name="strategy"
                      value="keep_b"
                      checked={conflictStrategy === 'keep_b'}
                      onChange={() => setConflictStrategy('keep_b')}
                      className="text-[#58a6ff]"
                    />
                    <div>
                      <div className="font-medium text-white">Prioritize Requirement B</div>
                      <div className="text-[11px] text-[#8b949e]">Discards the conflicting primary constraint in Requirement A.</div>
                    </div>
                  </label>

                  <label className="flex items-center gap-2 p-2 rounded border border-[#30363d] bg-[#0d1117] cursor-pointer hover:border-[#8b949e]">
                    <input
                      type="radio"
                      name="strategy"
                      value="merge"
                      checked={conflictStrategy === 'merge'}
                      onChange={() => setConflictStrategy('merge')}
                      className="text-[#58a6ff]"
                    />
                    <div>
                      <div className="font-medium text-white">Synthesize Unified Requirement (Merge)</div>
                      <div className="text-[11px] text-[#8b949e]">Harmonizes both requirements into a non-contradictory hybrid specification.</div>
                    </div>
                  </label>
                </div>
              </div>

              <div className="flex flex-col gap-1.5 mt-1">
                <label className="text-[#8b949e] font-semibold uppercase tracking-wider text-[11px]">
                  Custom Synthesis Notes (Optional):
                </label>
                <input
                  type="text"
                  value={conflictResolutionInput}
                  onChange={(e) => setConflictResolutionInput(e.target.value)}
                  placeholder="e.g., Provide in-memory speed with optional disk snapshotting on graceful shutdown."
                  className="w-full bg-[#0d1117] border border-[#30363d] rounded p-2 text-xs text-white focus:outline-none focus:border-[#f85149]"
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2 border-t border-[#30363d]">
              <button
                onClick={() => setConflictModalOpen(false)}
                className="px-3 py-1.5 rounded bg-[#21262d] hover:bg-[#30363d] text-xs font-medium text-white transition"
              >
                Cancel
              </button>
              <button
                onClick={handleResolveConflict}
                disabled={loading}
                className="px-4 py-1.5 rounded bg-[#f85149] hover:bg-[#da3633] disabled:opacity-50 text-xs font-semibold text-white flex items-center gap-1.5 transition"
              >
                {loading ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <GitMerge className="w-3.5 h-3.5" />}
                Reconcile &amp; Resume
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 6. MODAL: GITHUB PULL REQUEST EXPORT */}
      {prModalOpen && prResult && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-[#161b22] border border-[#30363d] rounded-lg w-[540px] max-w-full p-5 shadow-2xl flex flex-col gap-4">
            <div className="flex items-center justify-between border-b border-[#30363d] pb-3">
              <div className="flex items-center gap-2">
                <GitPullRequest className="w-5 h-5 text-[#58a6ff]" />
                <span className="font-semibold text-white text-sm">GitHub Pull Request Created</span>
              </div>
              <button
                onClick={() => setPrModalOpen(false)}
                className="text-[#8b949e] hover:text-white"
              >
                &times;
              </button>
            </div>

            <div className="flex flex-col gap-2 text-xs">
              <div>
                <span className="text-[#8b949e]">Target Branch:</span>
                <span className="ml-2 font-mono text-[#58a6ff]">{prResult.branch}</span>
              </div>
              <div>
                <span className="text-[#8b949e]">PR Title:</span>
                <div className="font-medium text-white mt-0.5">{prResult.pr_title}</div>
              </div>
              <div>
                <span className="text-[#8b949e]">Description:</span>
                <pre className="mt-1 p-2 bg-[#0d1117] border border-[#30363d] rounded text-[11px] font-mono whitespace-pre-wrap text-[#c9d1d9]">
                  {prResult.pr_description}
                </pre>
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2 border-t border-[#30363d]">
              <button
                onClick={() => setPrModalOpen(false)}
                className="px-3 py-1.5 rounded bg-[#21262d] hover:bg-[#30363d] text-xs font-medium text-white transition"
              >
                Close
              </button>
              <a
                href={prResult.export_url}
                target="_blank"
                rel="noreferrer"
                className="px-3 py-1.5 rounded bg-[#238636] hover:bg-[#2ea043] text-xs font-semibold text-white flex items-center gap-1.5 transition"
              >
                View on GitHub <ExternalLink className="w-3.5 h-3.5" />
              </a>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
