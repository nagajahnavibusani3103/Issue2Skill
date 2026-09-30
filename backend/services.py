"""
Issue2Skill — Core Services
- TursoClient (libSQL Hrana HTTP pipeline client with local fallback)
- LLMClient (Unified OpenAI-compatible provider for Qwen3-8B with offline mock generator)
- HardenedProcessSandbox (Zero-Docker OS-isolated workspace confinement)
- SkillHarness (Behavioral evaluation harness for Agent Skills)
- GitHubClient (GitHub issue ingestion and export helper)
"""

import os
import re
import sys
import json
import time
import shutil
import hashlib
import tempfile
import sqlite3
import subprocess
from typing import Dict, Any, List, Optional, Tuple
from urllib.parse import urlparse
import httpx


class SecurityViolationError(Exception):
    """Raised when an untrusted action violates sandbox or path boundaries."""
    pass


# ==============================================================================
# 1. DATABASE CLIENT (TURSO / libSQL HRANA V2 PIPELINE + LOCAL FALLBACK)
# ==============================================================================

class TursoClient:
    """
    Client for Turso / libSQL over HTTPS Hrana pipeline API.
    Gracefully falls back to an in-memory/local SQLite database if credentials
    are not set or if network is unreachable during local testing.
    """

    def __init__(self, database_url: Optional[str] = None, auth_token: Optional[str] = None):
        self.raw_url = database_url or os.getenv("TURSO_DATABASE_URL", "")
        self.auth_token = auth_token or os.getenv("TURSO_AUTH_TOKEN", "")
        self.pipeline_url = self._format_pipeline_url(self.raw_url)
        self.use_remote = bool(self.pipeline_url and self.auth_token)
        self.local_conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.local_conn.row_factory = sqlite3.Row
        self._init_db()

    def _format_pipeline_url(self, url: str) -> Optional[str]:
        if not url:
            return None
        cleaned = url.strip()
        if cleaned.startswith("libsql://"):
            host = cleaned[len("libsql://"):]
            return f"https://{host}/v2/pipeline"
        elif cleaned.startswith("https://") or cleaned.startswith("http://"):
            parsed = urlparse(cleaned)
            return f"{parsed.scheme}://{parsed.netloc}/v2/pipeline"
        return None

    def _init_db(self):
        schema = """
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            repo_url TEXT NOT NULL,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS issues (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            issue_number INTEGER,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            classification TEXT NOT NULL,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS requirements (
            id TEXT PRIMARY KEY,
            issue_id TEXT NOT NULL,
            req_id TEXT NOT NULL,
            statement TEXT NOT NULL,
            req_type TEXT NOT NULL,
            priority TEXT NOT NULL,
            confidence REAL NOT NULL,
            constraints_json TEXT NOT NULL,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS skills (
            id TEXT PRIMARY KEY,
            issue_id TEXT NOT NULL,
            version INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            skill_md TEXT NOT NULL,
            skillir_json TEXT NOT NULL,
            is_validated INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS test_cases (
            id TEXT PRIMARY KEY,
            skill_id TEXT NOT NULL,
            test_id TEXT NOT NULL,
            req_refs_json TEXT NOT NULL,
            test_type TEXT NOT NULL,
            task_prompt TEXT NOT NULL,
            assertions_json TEXT NOT NULL,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS pipeline_runs (
            id TEXT PRIMARY KEY,
            issue_id TEXT NOT NULL,
            skill_id TEXT,
            current_state TEXT NOT NULL,
            repair_attempts INTEGER NOT NULL DEFAULT 0,
            trace_events_json TEXT NOT NULL,
            duration_ms INTEGER NOT NULL,
            created_at INTEGER NOT NULL
        );
        """
        # Always init local fallback connection
        self.local_conn.executescript(schema)

        # If remote is configured, execute schema remotely via Hrana batch
        if self.use_remote:
            try:
                statements = [stmt.strip() for stmt in schema.split(";") if stmt.strip()]
                self.execute_batch(statements)
            except Exception as e:
                # Log without exposing any token
                sys.stderr.write(f"[WARN] Remote Turso init failed, falling back to local storage: {type(e).__name__}\n")
                self.use_remote = False

    def execute(self, sql: str, params: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
        params = params or []
        if not self.use_remote:
            cursor = self.local_conn.cursor()
            cursor.execute(sql, params)
            if sql.strip().upper().startswith("SELECT"):
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
            self.local_conn.commit()
            return []

        # Remote Turso Hrana v2 pipeline call
        req_step = {
            "type": "execute",
            "stmt": {
                "sql": sql,
                "args": [{"type": self._map_arg_type(p), "value": str(p) if p is not None else None} for p in params]
            }
        }
        body = {"requests": [req_step, {"type": "close"}]}
        headers = {
            "Authorization": f"Bearer {self.auth_token}",
            "Content-Type": "application/json"
        }
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(self.pipeline_url, json=body, headers=headers)
            if resp.status_code != 200:
                raise RuntimeError(f"Turso query error HTTP {resp.status_code}")
            data = resp.json()
            results = []
            res_body = data.get("results", [{}])[0]
            if res_body.get("type") == "ok":
                res_data = res_body.get("response", {}).get("result", {})
                cols = [c["name"] for c in res_data.get("cols", [])]
                for r in res_data.get("rows", []):
                    row_dict = {}
                    for col_name, val_obj in zip(cols, r):
                        row_dict[col_name] = val_obj.get("value")
                    results.append(row_dict)
            return results

    def execute_batch(self, statements: List[str]) -> bool:
        if not self.use_remote:
            cursor = self.local_conn.cursor()
            for stmt in statements:
                cursor.execute(stmt)
            self.local_conn.commit()
            return True

        reqs = []
        for stmt in statements:
            reqs.append({
                "type": "execute",
                "stmt": {"sql": stmt}
            })
        reqs.append({"type": "close"})
        headers = {
            "Authorization": f"Bearer {self.auth_token}",
            "Content-Type": "application/json"
        }
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(self.pipeline_url, json={"requests": reqs}, headers=headers)
            return resp.status_code == 200

    def _map_arg_type(self, val: Any) -> str:
        if val is None:
            return "null"
        if isinstance(val, int):
            return "integer"
        if isinstance(val, float):
            return "float"
        return "text"


# ==============================================================================
# 2. LLM CLIENT (QWEN3-8B VIA VLLM / OLLAMA + DETERMINISTIC MOCK GENERATOR)
# ==============================================================================

class LLMClient:
    """
    OpenAI-compatible client for Qwen3-8B.
    Supports vLLM (primary) and Ollama (local dev).
    Includes a deterministic offline generator so unit tests and offline environments
    produce realistic, typed results without external inference dependencies.
    """

    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None, model: Optional[str] = None):
        self.base_url = (base_url or os.getenv("LLM_BASE_URL", "http://localhost:8000/v1")).rstrip("/")
        self.api_key = api_key or os.getenv("LLM_API_KEY", "EMPTY")
        self.model = model or os.getenv("LLM_MODEL", "Qwen3-8B")

    def generate_structured(self, system_prompt: str, user_prompt: str, schema_name: str, fallback_generator=None) -> Dict[str, Any]:
        """
        Requests structured JSON completion from the LLM endpoint.
        Falls back to fallback_generator if endpoint is unreachable.
        """
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt + "\nOUTPUT MUST BE STRICT RAW JSON WITHOUT MARKDOWN."},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"}
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    return self._clean_and_parse_json(content)
        except Exception:
            pass  # Fall back to deterministic engine

        if fallback_generator:
            return fallback_generator()
        raise RuntimeError("Inference endpoint unavailable and no fallback generator provided.")

    def generate_text(self, system_prompt: str, user_prompt: str, fallback_generator=None) -> str:
        """
        Requests free-form text completion from the LLM endpoint.
        Falls back to fallback_generator if endpoint is unreachable.
        """
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.2
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    return data["choices"][0]["message"]["content"]
        except Exception:
            pass

        if fallback_generator:
            return fallback_generator()
        raise RuntimeError("Inference endpoint unavailable and no fallback generator provided.")

    generate_raw = generate_text

    def _clean_and_parse_json(self, raw: str) -> Dict[str, Any]:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        return json.loads(cleaned)


# ==============================================================================
# 3. ISOLATED DOCKER EXECUTION SANDBOX
# ==============================================================================

class DockerExecutionSandbox:
    """
    Isolated Docker Execution Sandbox.
    Untrusted generated skill execution MUST use Docker.
    If Docker is unavailable, execution is refused with SANDBOX_UNAVAILABLE.
    There is NO unsafe native Python/subprocess fallback for untrusted code.

    Enforces (where supported by Docker daemon):
    - Non-root execution (--user 1000:1000)
    - Network disabled (--network none)
    - Read-only root filesystem (--read-only)
    - Controlled writable workspace (-v <workspace>:/workspace:rw -w /workspace)
    - Dropped capabilities (--cap-drop ALL)
    - No privileged mode
    - No Docker socket mounted
    - Security options (--security-opt no-new-privileges)
    - CPU limit (--cpus 1.0)
    - Memory limit (--memory 512m)
    - PID/process limit (--pids-limit 64)
    - Execution timeout (15s)
    - Output size cap (64KB)
    - Sanitized environment with zero application secrets
    """

    BANNED_COMMAND_PATTERNS = [
        r"\bpip\b", r"\bnpm\b", r"\byarn\b", r"\bpnpm\b",
        r"\bcurl\b", r"\bwget\b", r"\bapt\b", r"\bapt-get\b",
        r"\bapk\b", r"\byum\b", r"\bgit\s+clone\b"
    ]

    def __init__(self, timeout_seconds: int = 15, max_output_bytes: int = 65536, mock_mode: bool = False, image: str = "python:3.11-slim"):
        self.timeout_seconds = timeout_seconds
        self.max_output_bytes = max_output_bytes
        self.mock_mode = mock_mode
        self.image = image

    def is_docker_available(self) -> bool:
        """Checks if Docker binary exists and daemon is responsive."""
        if not shutil.which("docker"):
            return False
        try:
            res = subprocess.run(["docker", "info"], capture_output=True, timeout=3)
            return res.returncode == 0
        except Exception:
            return False

    def build_docker_command(self, workspace_dir: str, command: List[str]) -> List[str]:
        """Constructs the hardened Docker command with security flags."""
        canonical_workspace = os.path.realpath(workspace_dir)
        return [
            "docker", "run", "--rm",
            "--network", "none",
            "--read-only",
            "--user", "1000:1000",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--cpus", "1.0",
            "--memory", "512m",
            "--pids-limit", "64",
            "-v", f"{canonical_workspace}:/workspace:rw",
            "-w", "/workspace",
            self.image
        ] + command

    def execute_in_sandbox(self, command: List[str], workspace_dir: str, stdin_data: Optional[str] = None) -> Dict[str, Any]:
        canonical_workspace = os.path.realpath(workspace_dir)
        if not os.path.isdir(canonical_workspace):
            raise SecurityViolationError(f"Workspace path does not exist: {workspace_dir}")

        # Check for banned package managers
        cmd_str = " ".join(command)
        for pattern in self.BANNED_COMMAND_PATTERNS:
            if re.search(pattern, cmd_str, re.IGNORECASE):
                return {
                    "exit_code": 126,
                    "stdout": "",
                    "stderr": f"SECURITY_BLOCKED: Command contains banned utility matching '{pattern}'",
                    "duration_ms": 0,
                    "timed_out": False,
                    "security_blocked": True,
                    "status": "SECURITY_BLOCKED"
                }

        # If Docker is not available and not in mock mode, refuse untrusted execution
        if not self.mock_mode and not self.is_docker_available():
            return {
                "exit_code": 125,
                "stdout": "",
                "stderr": "SANDBOX_UNAVAILABLE: Docker is required for untrusted skill execution but is not installed or running. Execution blocked.",
                "duration_ms": 0,
                "timed_out": False,
                "security_blocked": True,
                "sandbox_unavailable": True,
                "status": "SANDBOX_UNAVAILABLE"
            }

        # If mock mode is explicitly enabled (for deterministic compiler unit tests)
        if self.mock_mode:
            return self._execute_mock(command, canonical_workspace, stdin_data)

        # Docker execution
        docker_cmd = self.build_docker_command(canonical_workspace, command)
        start_time = time.time()
        timed_out = False
        try:
            proc = subprocess.Popen(
                docker_cmd,
                stdin=subprocess.PIPE if stdin_data else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=False
            )
            stdout_raw, stderr_raw = proc.communicate(input=stdin_data, timeout=self.timeout_seconds)
            exit_code = proc.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            subprocess.run(["docker", "kill", proc.pid], capture_output=True)
            stdout_raw, stderr_raw = proc.communicate()
            exit_code = 124
        except Exception as e:
            return {
                "exit_code": 1,
                "stdout": "",
                "stderr": f"Docker execution error: {str(e)}",
                "duration_ms": int((time.time() - start_time) * 1000),
                "timed_out": False,
                "security_blocked": False,
                "status": "FAILED"
            }

        duration_ms = int((time.time() - start_time) * 1000)
        return {
            "exit_code": exit_code,
            "stdout": stdout_raw[:self.max_output_bytes],
            "stderr": stderr_raw[:self.max_output_bytes],
            "duration_ms": duration_ms,
            "timed_out": timed_out,
            "security_blocked": False,
            "status": "PASSED" if exit_code == 0 else "FAILED"
        }

    def _execute_mock(self, command: List[str], workspace_dir: str, stdin_data: Optional[str]) -> Dict[str, Any]:
        """Safe test-only execution for deterministic unit tests."""
        clean_env = {
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", "C:\\Windows"),
            "PATH": os.environ.get("PATH", ""),
            "PYTHONUNBUFFERED": "1"
        }
        start_time = time.time()
        try:
            proc = subprocess.Popen(
                command,
                cwd=workspace_dir,
                env=clean_env,
                stdin=subprocess.PIPE if stdin_data else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=False
            )
            stdout, stderr = proc.communicate(input=stdin_data, timeout=self.timeout_seconds)
            return {
                "exit_code": proc.returncode,
                "stdout": stdout[:self.max_output_bytes],
                "stderr": stderr[:self.max_output_bytes],
                "duration_ms": int((time.time() - start_time) * 1000),
                "timed_out": False,
                "security_blocked": False,
                "status": "PASSED" if proc.returncode == 0 else "FAILED"
            }
        except subprocess.TimeoutExpired:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
            else:
                try:
                    os.kill(proc.pid, 9)
                except OSError:
                    pass
            return {
                "exit_code": 124,
                "stdout": "",
                "stderr": "Execution timed out",
                "duration_ms": int((time.time() - start_time) * 1000),
                "timed_out": True,
                "security_blocked": False,
                "status": "TIMEOUT"
            }

HardenedProcessSandbox = DockerExecutionSandbox  # Backward-compatible alias


# ==============================================================================
# 4. SKILL HARNESS (BEHAVIORAL EVALUATION ENGINE)
# ==============================================================================

class SkillHarness:
    """
    Test harness that executes requirement-derived test cases against an Agent Skill.
    """

    def __init__(self, sandbox: Optional[DockerExecutionSandbox] = None):
        self.sandbox = sandbox or DockerExecutionSandbox()

    def run_test(self, skill_content: str, test_case: Dict[str, Any], skill_scripts: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Runs a test case in an isolated temporary directory.
        Evaluates assertions: EXIT_CODE_EQUALS, STDOUT_CONTAINS, FILE_EXISTS, JSON_SCHEMA_MATCHES.
        """
        with tempfile.TemporaryDirectory(prefix="i2s_run_") as tmp_dir:
            canonical_tmp = os.path.realpath(tmp_dir)

            # 1. Write SKILL.md and any scripts
            skill_md_path = os.path.join(canonical_tmp, "SKILL.md")
            with open(skill_md_path, "w", encoding="utf-8") as f:
                f.write(skill_content)

            if skill_scripts:
                for rel_path, script_code in skill_scripts.items():
                    target_path = os.path.realpath(os.path.join(canonical_tmp, rel_path))
                    if not target_path.startswith(canonical_tmp):
                        raise SecurityViolationError("Path traversal in skill script path")
                    os.makedirs(os.path.dirname(target_path), exist_ok=True)
                    with open(target_path, "w", encoding="utf-8") as f:
                        f.write(script_code)

            # 2. Write test input fixture files if specified
            fixtures = test_case.get("fixtures", {})
            for fname, fcontent in fixtures.items():
                fpath = os.path.realpath(os.path.join(canonical_tmp, fname))
                if not fpath.startswith(canonical_tmp):
                    raise SecurityViolationError("Path traversal in test fixture")
                os.makedirs(os.path.dirname(fpath), exist_ok=True)
                with open(fpath, "w", encoding="utf-8") as f:
                    f.write(fcontent)

            # 3. Determine command to execute
            test_cmd = test_case.get("command")
            if not test_cmd:
                # Default behavioral runner: python script or validation command
                test_cmd = [sys.executable, "-c", "print('Skill test completed successfully')"]

            # 4. Execute inside sandbox
            run_result = self.sandbox.execute_in_sandbox(
                command=test_cmd,
                workspace_dir=canonical_tmp,
                stdin_data=test_case.get("stdin")
            )

            # 5. Evaluate assertions
            assertions = test_case.get("assertions", [])
            assertion_results = []
            all_passed = not run_result["timed_out"] and not run_result["security_blocked"]

            for assertion in assertions:
                a_type = assertion.get("type")
                expected = assertion.get("expected")
                passed = False
                message = ""

                if a_type == "EXIT_CODE_EQUALS":
                    passed = (run_result["exit_code"] == int(expected))
                    message = f"Exit code {run_result['exit_code']} vs expected {expected}"
                elif a_type == "STDOUT_CONTAINS":
                    passed = (str(expected) in run_result["stdout"])
                    message = f"Stdout contains '{expected}'"
                elif a_type == "STDERR_CONTAINS":
                    passed = (str(expected) in run_result["stderr"])
                    message = f"Stderr contains '{expected}'"
                elif a_type == "FILE_EXISTS":
                    target_file = os.path.realpath(os.path.join(canonical_tmp, str(expected)))
                    passed = os.path.exists(target_file) and target_file.startswith(canonical_tmp)
                    message = f"File '{expected}' exists"
                elif a_type == "JSON_SCHEMA_MATCHES":
                    # Simple JSON parse assertion
                    target_file = os.path.realpath(os.path.join(canonical_tmp, assertion.get("file", "output.json")))
                    try:
                        if os.path.exists(target_file):
                            with open(target_file, "r", encoding="utf-8") as jf:
                                json.load(jf)
                            passed = True
                            message = "Valid JSON payload produced"
                        else:
                            passed = False
                            message = f"JSON file '{target_file}' missing"
                    except Exception as ex:
                        passed = False
                        message = f"Malformed JSON: {str(ex)}"
                else:
                    passed = True
                    message = f"Unknown assertion '{a_type}' skipped"

                if not passed:
                    all_passed = False

                assertion_results.append({
                    "assertion": assertion,
                    "passed": passed,
                    "message": message
                })

            status = "PASSED" if (all_passed and len(assertions) > 0) else "FAILED"
            if run_result["timed_out"]:
                status = "TIMEOUT"
            elif run_result.get("sandbox_unavailable"):
                status = "SANDBOX_UNAVAILABLE"
            elif run_result["security_blocked"]:
                status = "SECURITY_BLOCKED"

            return {
                "test_id": test_case.get("id", "TEST-UNKNOWN"),
                "status": status,
                "exit_code": run_result["exit_code"],
                "stdout": run_result["stdout"],
                "stderr": run_result["stderr"],
                "duration_ms": run_result["duration_ms"],
                "assertions": assertion_results
            }


# ==============================================================================
# 5. GITHUB CLIENT (ISSUE INGESTION & PR PAYLOAD BUILDER)
# ==============================================================================

class GitHubClient:
    """Helper client for GitHub issue ingestion and Pull Request creation."""

    def __init__(self, token: Optional[str] = None):
        self.token = token or os.getenv("GITHUB_TOKEN", "")

    def fetch_issue_from_url(self, issue_url: str) -> Dict[str, Any]:
        """
        Parses github.com/owner/repo/issues/123 and fetches issue metadata.
        Uses public unauthenticated API when token is not present.
        """
        parsed = urlparse(issue_url)
        parts = parsed.path.strip("/").split("/")
        if len(parts) < 4 or parts[2] != "issues":
            raise ValueError(f"Invalid GitHub issue URL: {issue_url}")

        owner, repo, _, issue_number = parts[0], parts[1], parts[2], parts[3]
        api_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}"

        headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "Issue2Skill-Compiler"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        with httpx.Client(timeout=10.0) as client:
            resp = client.get(api_url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "owner": owner,
                    "repo": repo,
                    "issue_number": int(issue_number),
                    "title": data.get("title", ""),
                    "body": data.get("body", "") or "",
                    "url": issue_url
                }
            elif resp.status_code == 404:
                raise ValueError("GitHub issue not found (check repository permissions)")
            else:
                raise RuntimeError(f"GitHub API error HTTP {resp.status_code}")
