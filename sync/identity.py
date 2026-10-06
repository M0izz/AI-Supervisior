"""
AI Supervisor — Project & Device Identity
Derives stable, path-independent project identifiers across heterogeneous machines
and generates cryptographic device identifiers.
"""

import hashlib
import os
import re
import subprocess
from pathlib import Path
from typing import Optional, Tuple
import uuid


def normalize_git_url(raw_url: str) -> str:
    """
    Normalizes a Git remote URL into a path-independent canonical identifier.
    Examples:
        git@github.com:M0izz/AI-Supervisior.git -> repo:github.com/m0izz/ai-supervisior
        https://github.com/M0izz/AI-Supervisior.git -> repo:github.com/m0izz/ai-supervisior
        ssh://git@gitlab.com/group/repo.git -> repo:gitlab.com/group/repo
    """
    cleaned = raw_url.strip().lower()

    # Strip .git suffix
    if cleaned.endswith(".git"):
        cleaned = cleaned[:-4]

    # Handle SSH git@host:owner/repo
    ssh_match = re.match(r"^(?:ssh://)?git@([^:/]+)[:/](.+)$", cleaned)
    if ssh_match:
        host, repo_path = ssh_match.group(1), ssh_match.group(2).lstrip("/")
        return f"repo:{host}/{repo_path}"

    # Handle HTTP/HTTPS https://host/owner/repo
    http_match = re.match(r"^https?://([^/]+)/(.+)$", cleaned)
    if http_match:
        host, repo_path = http_match.group(1), http_match.group(2).lstrip("/")
        return f"repo:{host}/{repo_path}"

    # Fallback to sanitized string
    sanitized = re.sub(r"[^a-zA-Z0-9_\-\.]+", "/", cleaned).strip("/")
    return f"repo:{sanitized}"


def derive_project_id(repo_path: Optional[Path] = None) -> str:
    """
    Derives a stable, path-independent project identity.
    Priority:
    1. Git remote origin URL (canonical across developer machines)
    2. Explicit .supervisor/project_id file if present
    3. Git root commit hash
    4. Deterministic project fingerprint based on repository root name & marker
    """
    root = Path(repo_path or ".").resolve()

    # 1. Check for explicit cached project ID
    marker_file = root / ".supervisor" / "project_id"
    if marker_file.exists():
        try:
            cached_id = marker_file.read_text(encoding="utf-8").strip()
            if cached_id:
                return cached_id
        except Exception:
            pass

    # 2. Try git remote origin
    try:
        res = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=2,
            shell=False
        )
        if res.returncode == 0 and res.stdout.strip():
            project_id = normalize_git_url(res.stdout.strip())
            _cache_project_id(root, project_id)
            return project_id
    except Exception:
        pass

    # 3. Try git root commit hash
    try:
        res = subprocess.run(
            ["git", "rev-list", "--max-parents=0", "HEAD"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=2,
            shell=False
        )
        if res.returncode == 0 and res.stdout.strip():
            root_commit = res.stdout.strip().split()[-1]
            project_id = f"commit:{root_commit[:16]}"
            _cache_project_id(root, project_id)
            return project_id
    except Exception:
        pass

    # 4. Fallback: Deterministic fingerprint of folder name
    folder_name = root.name.lower()
    fingerprint = hashlib.sha256(folder_name.encode("utf-8")).hexdigest()[:16]
    project_id = f"local-project:{folder_name}-{fingerprint}"
    _cache_project_id(root, project_id)
    return project_id


def _cache_project_id(root: Path, project_id: str) -> None:
    """Persists derived project identity to .supervisor/project_id."""
    try:
        supervisor_dir = root / ".supervisor"
        supervisor_dir.mkdir(parents=True, exist_ok=True)
        marker_file = supervisor_dir / "project_id"
        if not marker_file.exists():
            marker_file.write_text(project_id, encoding="utf-8")
    except Exception:
        pass


def generate_device_credentials() -> Tuple[str, str]:
    """
    Generates a unique (device_id, device_token) pair.
    The device_id is public; the device_token is private and hashed on the server.
    """
    device_id = f"dev_{uuid.uuid4().hex[:12]}"
    device_token = f"tok_{uuid.uuid4().hex}{uuid.uuid4().hex}"
    return device_id, device_token


def hash_device_token(token: str) -> str:
    """Computes a SHA-256 hash of the device token with fixed salt."""
    salt = b"ai_supervisor_sync_salt_v1_"
    return hashlib.sha256(salt + token.encode("utf-8")).hexdigest()
