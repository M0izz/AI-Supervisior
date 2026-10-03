import logging
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any, Dict, List, Optional

logger = logging.getLogger("supervisor.execution.worktree")


class GitWorktreeError(Exception):
    """Raised when a Git worktree operation fails or prerequisites are not met."""

    def __init__(
        self,
        message: str,
        returncode: Optional[int] = None,
        stdout: Optional[str] = None,
        stderr: Optional[str] = None,
    ):
        super().__init__(message)
        self.message = message
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

    def __str__(self) -> str:
        parts = [self.message]
        if self.returncode is not None:
            parts.append(f"(exit code {self.returncode})")
        if self.stderr:
            parts.append(f"stderr: {self.stderr.strip()}")
        return " ".join(parts)


def sanitize_identifier(raw: str) -> str:
    """Sanitizes mission or task IDs for safe use in branch names and directory paths."""
    if not raw:
        return "unknown"
    clean = re.sub(r"[^a-zA-Z0-9_\-]", "_", str(raw).strip())
    return clean[:64]


class WorktreeStatus:
    """Status snapshot of an isolated worktree."""

    def __init__(
        self,
        is_active: bool,
        worktree_path: Path,
        branch_name: str,
        commit_hash: Optional[str] = None,
        has_uncommitted_changes: bool = False,
    ):
        self.is_active = is_active
        self.worktree_path = worktree_path
        self.branch_name = branch_name
        self.commit_hash = commit_hash
        self.has_uncommitted_changes = has_uncommitted_changes

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_active": self.is_active,
            "worktree_path": str(self.worktree_path),
            "branch_name": self.branch_name,
            "commit_hash": self.commit_hash,
            "has_uncommitted_changes": self.has_uncommitted_changes,
        }


class GitWorktreeManager:
    """
    Manages isolated Git worktrees and task branches.
    Provides strict filesystem boundary isolation for autonomous agents
    without risking mutations to the primary repository working tree.
    """

    def __init__(
        self,
        repo_root: str | Path,
        worktrees_base_dir: Optional[str | Path] = None,
    ):
        self.repo_root = Path(repo_root).resolve()
        if worktrees_base_dir:
            self.worktrees_base_dir = Path(worktrees_base_dir).resolve()
        else:
            self.worktrees_base_dir = (self.repo_root / ".supervisor" / "worktrees").resolve()

    def _run_git(
        self,
        args: List[str],
        cwd: Optional[Path] = None,
        check: bool = False,
    ) -> subprocess.CompletedProcess:
        """Executes a Git command without a shell to prevent command injection."""
        working_dir = cwd or self.repo_root
        cmd = ["git"] + args
        try:
            res = subprocess.run(
                cmd,
                cwd=str(working_dir),
                capture_output=True,
                text=True,
                shell=False,
            )
            if check and res.returncode != 0:
                raise GitWorktreeError(
                    f"Git command failed: {' '.join(cmd)}",
                    returncode=res.returncode,
                    stdout=res.stdout,
                    stderr=res.stderr,
                )
            return res
        except FileNotFoundError:
            raise GitWorktreeError(
                "Git executable not found on system PATH. "
                "Autonomous multi-agent execution requires Git worktree isolation."
            )

    def verify_git_repo(self) -> None:
        """
        Validates that repo_root is an initialized Git repository.
        HARD REQUIREMENT: If Git is uninitialized or unavailable, do NOT silently
        fall back to an unisolated sandbox. Raise a clear, actionable error.
        """
        if not self.repo_root.exists() or not self.repo_root.is_dir():
            raise GitWorktreeError(
                f"Repository path '{self.repo_root}' does not exist or is not a directory. "
                "Autonomous multi-agent execution requires an initialized Git repository."
            )

        res = self._run_git(["rev-parse", "--is-inside-work-tree"])
        if res.returncode != 0 or res.stdout.strip().lower() != "true":
            raise GitWorktreeError(
                f"Directory '{self.repo_root}' is not an initialized Git repository. "
                "Autonomous multi-agent execution requires Git worktree isolation. "
                "Please run 'git init' and make an initial commit before dispatching tasks."
            )

    def branch_name(self, mission_id: str, task_id: str) -> str:
        """Generates a deterministic, isolated Git branch name for the task."""
        clean_m = sanitize_identifier(mission_id)
        clean_t = sanitize_identifier(task_id)
        return f"supervisor/{clean_m}/{clean_t}"

    def path(self, mission_id: str, task_id: str) -> Path:
        """
        Calculates and validates the target worktree path.
        Enforces path containment within worktrees_base_dir to prevent directory traversal.
        """
        clean_m = sanitize_identifier(mission_id)
        clean_t = sanitize_identifier(task_id)
        folder_name = f"{clean_m}_{clean_t}"
        target = (self.worktrees_base_dir / folder_name).resolve()

        # Security check: containment
        try:
            target.relative_to(self.worktrees_base_dir)
        except ValueError:
            raise GitWorktreeError(f"Security error: Worktree path '{target}' escapes '{self.worktrees_base_dir}'.")

        return target

    def exists(self, mission_id: str, task_id: str) -> bool:
        """Checks if a worktree already exists on disk and is recognized by Git."""
        target_path = self.path(mission_id, task_id)
        if not target_path.exists():
            return False

        res = self._run_git(["worktree", "list", "--porcelain"])
        if res.returncode == 0:
            norm_target = str(target_path).lower().replace("\\", "/")
            norm_output = res.stdout.lower().replace("\\", "/")
            return norm_target in norm_output
        return False

    def create(
        self,
        mission_id: str,
        task_id: str,
        base_ref: Optional[str] = None,
    ) -> Path:
        """
        Creates an isolated Git worktree on a dedicated branch.
        Protects the main repository working tree from changes.
        """
        self.verify_git_repo()

        target_path = self.path(mission_id, task_id)
        branch = self.branch_name(mission_id, task_id)

        # Check for duplicate / existing worktree
        if self.exists(mission_id, task_id):
            logger.info(f"Worktree for {mission_id}/{task_id} already exists at {target_path}")
            return target_path

        # If directory exists but git does not recognize it (stale), clean directory
        if target_path.exists():
            self._safe_directory_cleanup(target_path)

        self.worktrees_base_dir.mkdir(parents=True, exist_ok=True)

        # Determine if branch already exists
        check_branch = self._run_git(["rev-parse", "--verify", f"refs/heads/{branch}"])
        branch_exists = (check_branch.returncode == 0)

        # Determine base reference
        if not base_ref:
            # Detect default commit/branch
            head_check = self._run_git(["rev-parse", "--verify", "HEAD"])
            if head_check.returncode != 0:
                raise GitWorktreeError(
                    f"Repository at '{self.repo_root}' has no commits. "
                    "Cannot create worktree from an empty repository without initial commit."
                )
            base_ref = "HEAD"

        if branch_exists:
            # Reattach existing branch to the new worktree path
            cmd = ["worktree", "add", str(target_path), branch]
        else:
            # Create new branch rooted at base_ref
            cmd = ["worktree", "add", "-b", branch, str(target_path), base_ref]

        res = self._run_git(cmd)
        if res.returncode != 0:
            # Cleanup on failure
            if target_path.exists():
                self._safe_directory_cleanup(target_path)
            raise GitWorktreeError(
                f"Failed to create git worktree at '{target_path}'",
                returncode=res.returncode,
                stdout=res.stdout,
                stderr=res.stderr,
            )

        logger.info(f"Created isolated worktree at {target_path} on branch {branch}")
        return target_path

    def status(self, mission_id: str, task_id: str) -> WorktreeStatus:
        """Inspects worktree state, current commit, and working tree cleanliness."""
        target_path = self.path(mission_id, task_id)
        branch = self.branch_name(mission_id, task_id)

        if not target_path.exists():
            return WorktreeStatus(
                is_active=False,
                worktree_path=target_path,
                branch_name=branch,
            )

        # Check commit hash
        commit_res = self._run_git(["rev-parse", "HEAD"], cwd=target_path)
        commit_hash = commit_res.stdout.strip() if commit_res.returncode == 0 else None

        # Check uncommitted changes
        diff_res = self._run_git(["status", "--porcelain"], cwd=target_path)
        has_changes = bool(diff_res.stdout.strip()) if diff_res.returncode == 0 else False

        return WorktreeStatus(
            is_active=True,
            worktree_path=target_path,
            branch_name=branch,
            commit_hash=commit_hash,
            has_uncommitted_changes=has_changes,
        )

    def _safe_directory_cleanup(self, target: Path) -> None:
        """Safely removes an isolated worktree folder, strictly guarding against root deletion."""
        resolved = target.resolve()
        # Security sanity check: Never delete the main repository root!
        if resolved == self.repo_root:
            raise GitWorktreeError(f"Security fault: Attempted cleanup of root repository: {resolved}")

        try:
            resolved.relative_to(self.worktrees_base_dir)
        except ValueError:
            raise GitWorktreeError(f"Security fault: Directory '{resolved}' is not inside '{self.worktrees_base_dir}'")

        if resolved.exists():
            shutil.rmtree(resolved, ignore_errors=True)

    def remove(
        self,
        mission_id: str,
        task_id: str,
        force: bool = False,
        delete_branch: bool = True,
    ) -> None:
        """
        Removes the isolated worktree and prunes git metadata.
        Guarantees that the main working tree cannot be mutated or deleted.
        """
        target_path = self.path(mission_id, task_id)
        branch = self.branch_name(mission_id, task_id)

        # Check safety guard
        if target_path.resolve() == self.repo_root:
            raise GitWorktreeError("Safety guard: Cannot remove main repository as worktree.")

        # Attempt git worktree remove
        cmd = ["worktree", "remove", str(target_path)]
        if force:
            cmd.insert(2, "--force")

        res = self._run_git(cmd)
        if res.returncode != 0:
            logger.warning(f"git worktree remove reported: {res.stderr.strip()}")

        # Ensure directory is purged
        if target_path.exists():
            self._safe_directory_cleanup(target_path)

        # Prune worktrees metadata
        self._run_git(["worktree", "prune"])

        # Delete isolated task branch if requested
        if delete_branch:
            del_flag = "-D" if force else "-d"
            self._run_git(["branch", del_flag, branch])

        logger.info(f"Removed worktree for {mission_id}/{task_id} at {target_path}")

    def cleanup(self, mission_id: str, task_id: str, force: bool = False) -> None:
        """Alias for remove() to safely clean up task worktree resources."""
        self.remove(mission_id, task_id, force=force)

    def merge(
        self,
        mission_id: str,
        task_id: str,
        target_branch: str = "main",
    ) -> bool:
        """
        Safely attempts to merge task branch into target_branch.
        DO NOT perform automatic merge conflict resolution in Phase 1.
        Triggers an explicit failure if conflicts occur.
        """
        self.verify_git_repo()
        branch = self.branch_name(mission_id, task_id)

        # Verify branch exists
        res = self._run_git(["rev-parse", "--verify", f"refs/heads/{branch}"])
        if res.returncode != 0:
            raise GitWorktreeError(f"Branch '{branch}' does not exist for merge.")

        # Test mergeability without modifying working tree using git merge-tree
        # If git supports merge-tree (git >= 2.38)
        merge_test = self._run_git(["merge-tree", target_branch, branch])
        if merge_test.returncode != 0 or "+<<<<<<<" in merge_test.stdout:
            raise GitWorktreeError(
                f"Merge conflict detected between branch '{branch}' and target '{target_branch}'. "
                "Automated merge aborted. Manual or supervisor resolution required."
            )

        return True
