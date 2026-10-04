import asyncio
import logging
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from core.verification.models import (
    VerificationCheck,
    VerificationCheckStatus,
    VerificationCheckType,
    VerificationContext,
)

logger = logging.getLogger("supervisor.verification.checks")

MAX_OUTPUT_BYTES = 50_000
PROTECTED_PATHS = {".env", ".git", "schema.sql", ".secrets"}


def _safe_excerpt(text: str, max_bytes: int = MAX_OUTPUT_BYTES) -> str:
    """Truncates text safely to bounded length."""
    if not text:
        return ""
    if len(text) > max_bytes:
        return text[:max_bytes] + f"\n... [TRUNCATED at {max_bytes} characters]"
    return text


def _path_matches(file_path: str, patterns: List[str]) -> bool:
    """Matches a normalized relative path against a list of glob patterns or exact paths."""
    clean_target = file_path.replace("\\", "/")
    if clean_target.startswith("./"):
        clean_target = clean_target[2:]
    for pat in patterns:
        clean_pat = pat.replace("\\", "/")
        if clean_pat.startswith("./"):
            clean_pat = clean_pat[2:]
        if clean_pat == "*":
            return True
        if clean_target == clean_pat:
            return True
        if clean_pat.endswith("/*"):
            prefix = clean_pat[:-2]
            if clean_target.startswith(prefix + "/") or clean_target == prefix:
                return True
        elif clean_pat.endswith("/**"):
            prefix = clean_pat[:-3]
            if clean_target.startswith(prefix + "/") or clean_target == prefix:
                return True
        elif clean_pat.startswith("*."):
            ext = clean_pat[1:]
            if clean_target.endswith(ext):
                return True
        elif clean_target.startswith(clean_pat.rstrip("*")):
            return True
    return False



def run_git_check(context: VerificationContext) -> VerificationCheck:
    """
    Inspects worktree existence, directory integrity, and Git repository state.
    """
    ws = Path(context.workspace)
    if not ws.exists() or not ws.is_dir():
        return VerificationCheck(
            check_id="check_git_workspace",
            check_type=VerificationCheckType.GIT,
            description="Verify that task workspace exists and is accessible",
            status=VerificationCheckStatus.FAIL,
            message=f"Workspace directory does not exist or is not a directory: '{context.workspace}'",
            evidence={"workspace": context.workspace, "exists": False},
        )

    # Inspect Git state
    evidence: Dict[str, Any] = {"workspace": str(ws), "exists": True}
    try:
        git_check = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(ws),
            capture_output=True,
            text=True,
            shell=False,
            timeout=5,
        )
        is_git = git_check.returncode == 0 and git_check.stdout.strip().lower() == "true"
        evidence["is_git_worktree"] = is_git

        if is_git:
            # Check commit hash
            commit_res = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(ws),
                capture_output=True,
                text=True,
                shell=False,
                timeout=5,
            )
            evidence["head_commit"] = commit_res.stdout.strip() if commit_res.returncode == 0 else "unknown"

            # Check status porcelain
            status_res = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(ws),
                capture_output=True,
                text=True,
                shell=False,
                timeout=5,
            )
            raw_status = status_res.stdout.strip() if status_res.returncode == 0 else ""
            evidence["uncommitted_changes_count"] = len([line for line in raw_status.splitlines() if line.strip()])
            evidence["has_uncommitted_changes"] = bool(raw_status)
    except Exception as e:
        evidence["git_error"] = str(e)

    return VerificationCheck(
        check_id="check_git_workspace",
        check_type=VerificationCheckType.GIT,
        description="Verify isolated worktree integrity and access",
        status=VerificationCheckStatus.PASS,
        message="Workspace exists and is accessible.",
        evidence=evidence,
    )


def run_scope_check(context: VerificationContext) -> VerificationCheck:
    """
    Independently inspects modified files and compares against the authorized task scope whitelist.
    Flags path traversal attempts, protected file modifications, and unauthorized edits.
    """
    ws = Path(context.workspace)
    if not ws.exists():
        return VerificationCheck(
            check_id="check_scope",
            check_type=VerificationCheckType.SCOPE,
            description="Verify modifications respect declared task scope boundaries",
            status=VerificationCheckStatus.FAIL,
            message=f"Workspace does not exist: '{context.workspace}'",
            evidence={"workspace": context.workspace},
        )

    # Collect list of changed files from Git if available, or completion claim
    changed_files: List[str] = []
    try:
        # Check uncommitted files via git status
        st = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(ws),
            capture_output=True,
            text=True,
            shell=False,
            timeout=5,
        )
        if st.returncode == 0:
            for line in st.stdout.splitlines():
                if len(line) > 2:
                    path_part = line[2:].strip().strip('"')
                    if " -> " in path_part:
                        path_part = path_part.split(" -> ")[1].strip()
                    if path_part and path_part not in changed_files:
                        changed_files.append(path_part)

        # Check committed files on this branch against base branch (master / main)
        for base_ref in ("master", "main"):
            diff_res = subprocess.run(
                ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
                cwd=str(ws),
                capture_output=True,
                text=True,
                shell=False,
                timeout=5,
            )
            if diff_res.returncode == 0:
                if diff_res.stdout.strip():
                    for f in diff_res.stdout.strip().splitlines():
                        if f.strip() and f.strip() not in changed_files:
                            changed_files.append(f.strip())
                break
    except Exception as e:
        logger.debug(f"Git inspection in scope check had non-fatal error: {e}")

    # Also augment with completion claim reported files if available
    claimed_files = context.completion_claim.get("changed_files") or []
    for cf in claimed_files:
        if isinstance(cf, str) and cf not in changed_files:
            changed_files.append(cf)

    # Normalization: normalize slashes and strip optional leading './' without destroying '.' or '..'
    norm_changed: List[str] = []
    for f in changed_files:
        if not f or not isinstance(f, str):
            continue
        cleaned = f.strip().replace("\\", "/")
        if cleaned.startswith("./"):
            cleaned = cleaned[2:]
        if "__pycache__" in cleaned or cleaned.endswith(".pyc") or ".pytest_cache" in cleaned:
            continue
        if cleaned:
            norm_changed.append(cleaned)


    # 1. Path Traversal & Escape Check
    for f in norm_changed:
        if ".." in f or f.startswith("/") or re.match(r"^[a-zA-Z]:", f):
            return VerificationCheck(
                check_id="check_scope",
                check_type=VerificationCheckType.SCOPE,
                description="Verify modifications respect declared task scope boundaries",
                status=VerificationCheckStatus.FAIL,
                message=f"Path traversal or directory escape detected in modified file: '{f}'",
                evidence={"changed_files": norm_changed, "violation": f, "violation_type": "path_traversal"},
            )


    # 2. Protected Files Check
    for f in norm_changed:
        base_name = Path(f).name.lower()
        if base_name in PROTECTED_PATHS or any(p in f.split("/") for p in PROTECTED_PATHS):
            return VerificationCheck(
                check_id="check_scope",
                check_type=VerificationCheckType.SCOPE,
                description="Verify modifications respect declared task scope boundaries",
                status=VerificationCheckStatus.FAIL,
                message=f"Modification of protected system or configuration file forbidden: '{f}'",
                evidence={"changed_files": norm_changed, "protected_file": f},
            )

    # 3. Task Allowed Files Whitelist Check
    allowed = context.allowed_files
    unauthorized: List[str] = []
    if allowed:
        for f in norm_changed:
            if not _path_matches(f, allowed):
                unauthorized.append(f)

    if unauthorized:
        return VerificationCheck(
            check_id="check_scope",
            check_type=VerificationCheckType.SCOPE,
            description="Verify modifications respect declared task scope boundaries",
            status=VerificationCheckStatus.FAIL,
            message=f"Out-of-scope modifications detected: {unauthorized}. Allowed scope: {allowed}",
            evidence={
                "changed_files": norm_changed,
                "allowed_files": allowed,
                "unauthorized_files": unauthorized,
            },
        )

    # 4. Expected Files Existence Check
    missing_expected: List[str] = []
    for ef in context.expected_files:
        expected_path = ws / ef.replace("\\", "/").strip("./")
        if not expected_path.exists():
            missing_expected.append(ef)

    if missing_expected:
        return VerificationCheck(
            check_id="check_scope",
            check_type=VerificationCheckType.SCOPE,
            description="Verify modifications respect declared task scope boundaries",
            status=VerificationCheckStatus.FAIL,
            message=f"Expected task output files missing: {missing_expected}",
            evidence={"expected_files": context.expected_files, "missing": missing_expected},
        )

    return VerificationCheck(
        check_id="check_scope",
        check_type=VerificationCheckType.SCOPE,
        description="Verify modifications respect declared task scope boundaries",
        status=VerificationCheckStatus.PASS,
        message="All observed modifications satisfy declared task scope rules.",
        evidence={"changed_files": norm_changed, "allowed_files": allowed},
    )


def run_test_check(context: VerificationContext) -> VerificationCheck:
    """
    Independently executes declared test verification requirements in the isolated workspace.
    Enforces shell=False, bounded output, and timeout ceilings.
    """
    reqs = context.verification_requirements
    if not reqs:
        return VerificationCheck(
            check_id="check_tests",
            check_type=VerificationCheckType.TESTS,
            description="Run independent test verification commands",
            status=VerificationCheckStatus.SKIPPED,
            message="No test verification requirements declared for this task.",
            evidence={"verification_requirements": []},
        )

    ws = Path(context.workspace)
    results: List[Dict[str, Any]] = []

    for cmd_str in reqs:
        cmd_str = cmd_str.strip()
        if not cmd_str:
            continue

        # Safe command tokenization (shell=False invariant)
        parts = shlex.split(cmd_str, posix=(os.name != "nt"))
        parts = [p.strip('"\'') for p in parts]

        # Windows python/pytest executable normalization
        if parts:
            if parts[0] in ("python", "python3"):
                parts[0] = sys.executable
            elif parts[0] == "pytest":
                parts = [sys.executable, "-m", "pytest"] + parts[1:]

        start_t = time.monotonic()
        try:
            proc = subprocess.run(
                parts,
                cwd=str(ws),
                capture_output=True,
                text=True,
                shell=False,
                timeout=context.timeout,
            )
            duration = time.monotonic() - start_t
            stdout_excerpt = _safe_excerpt(proc.stdout)
            stderr_excerpt = _safe_excerpt(proc.stderr)

            cmd_evidence = {
                "command": cmd_str,
                "exit_code": proc.returncode,
                "duration_seconds": round(duration, 3),
                "stdout_excerpt": stdout_excerpt,
                "stderr_excerpt": stderr_excerpt,
            }
            results.append(cmd_evidence)

            if proc.returncode != 0:
                return VerificationCheck(
                    check_id="check_tests",
                    check_type=VerificationCheckType.TESTS,
                    description="Run independent test verification commands",
                    status=VerificationCheckStatus.FAIL,
                    message=f"Independent verification test command failed with exit code {proc.returncode}: '{cmd_str}'",
                    evidence={
                        "failed_command": cmd_str,
                        "exit_code": proc.returncode,
                        "stdout_excerpt": stdout_excerpt,
                        "stderr_excerpt": stderr_excerpt,
                        "all_results": results,
                    },
                )
        except subprocess.TimeoutExpired as te:
            duration = time.monotonic() - start_t
            return VerificationCheck(
                check_id="check_tests",
                check_type=VerificationCheckType.TESTS,
                description="Run independent test verification commands",
                status=VerificationCheckStatus.FAIL,
                message=f"Verification command timed out after {context.timeout:.1f}s: '{cmd_str}'",
                evidence={
                    "command": cmd_str,
                    "timeout_seconds": context.timeout,
                    "duration_seconds": round(duration, 3),
                    "exit_code": "TIMEOUT",
                    "error": "timed out",
                },

            )
        except Exception as e:
            return VerificationCheck(
                check_id="check_tests",
                check_type=VerificationCheckType.TESTS,
                description="Run independent test verification commands",
                status=VerificationCheckStatus.FAIL,
                message=f"Error executing verification command '{cmd_str}': {e}",
                evidence={"command": cmd_str, "error": str(e)},
            )

    return VerificationCheck(
        check_id="check_tests",
        check_type=VerificationCheckType.TESTS,
        description="Run independent test verification commands",
        status=VerificationCheckStatus.PASS,
        message=f"All {len(results)} independent test verification command(s) passed successfully.",
        evidence={"commands_executed": len(results), "results": results},
    )


def run_regression_check(
    context: VerificationContext,
    current_test_evidence: Optional[Dict[str, Any]] = None,
) -> VerificationCheck:
    """
    Compares current test outcomes against the baseline to detect introduced regressions.
    """
    baseline = context.baseline_test_results
    if not baseline:
        return VerificationCheck(
            check_id="check_regression",
            check_type=VerificationCheckType.REGRESSION,
            description="Verify no regressions against baseline test suite results",
            status=VerificationCheckStatus.SKIPPED,
            message="No baseline test results available to verify regressions against.",
            evidence={"baseline_available": False},
        )

    # Baseline comparison logic
    baseline_passed = set(baseline.get("passed_tests", []))
    baseline_failed = set(baseline.get("failed_tests", []))

    current_evidence = current_test_evidence or {}
    # Extract current failures from test stdout / metadata if provided
    current_failed = set(current_evidence.get("failed_tests", []))

    # Regressions: tests that were passing in baseline but are now failing
    new_regressions = [t for t in current_failed if t in baseline_passed]

    if new_regressions:
        return VerificationCheck(
            check_id="check_regression",
            check_type=VerificationCheckType.REGRESSION,
            description="Verify no regressions against baseline test suite results",
            status=VerificationCheckStatus.FAIL,
            message=f"Regressions detected: {len(new_regressions)} previously passing tests now fail: {new_regressions}",
            evidence={
                "baseline_passed_count": len(baseline_passed),
                "new_regressions": new_regressions,
            },
        )

    return VerificationCheck(
        check_id="check_regression",
        check_type=VerificationCheckType.REGRESSION,
        description="Verify no regressions against baseline test suite results",
        status=VerificationCheckStatus.PASS,
        message="No test regressions detected relative to baseline.",
        evidence={"baseline_passed_count": len(baseline_passed), "new_regressions_count": 0},
    )


def run_completion_claim_check(context: VerificationContext) -> VerificationCheck:
    """
    Evaluates whether the task has verifiable completion criteria.
    If the task has no verification requirements, no expected files, and no allowed files,
    it cannot be mechanically verified and requires operator review.
    """
    has_test_reqs = bool(context.verification_requirements)
    has_expected_files = bool(context.expected_files)
    has_allowed_files = bool(context.allowed_files)

    if not has_test_reqs and not has_expected_files and not has_allowed_files:
        return VerificationCheck(
            check_id="check_completion_claim",
            check_type=VerificationCheckType.COMPLETION_CLAIM,
            description="Verify task has structured, verifiable acceptance criteria",
            status=VerificationCheckStatus.WARN,
            message=(
                "Task lacks structured verifiable criteria (no test commands, expected files, or allowed files). "
                "Manual operator review is required."
            ),
            evidence={
                "has_test_reqs": False,
                "has_expected_files": False,
                "has_allowed_files": False,
            },
        )

    return VerificationCheck(
        check_id="check_completion_claim",
        check_type=VerificationCheckType.COMPLETION_CLAIM,
        description="Verify task has structured, verifiable acceptance criteria",
        status=VerificationCheckStatus.PASS,
        message="Task acceptance criteria are structured and verifiable.",
        evidence={
            "has_test_reqs": has_test_reqs,
            "has_expected_files": has_expected_files,
            "has_allowed_files": has_allowed_files,
            "claimed_summary": context.completion_claim.get("summary", ""),
        },
    )
