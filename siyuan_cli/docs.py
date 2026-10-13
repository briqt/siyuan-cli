"""Vendor the official SiYuan API references into the skill directory."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .client import FetchError, fail, fetch_text_url

OFFICIAL_REPOSITORY = "https://github.com/siyuan-note/siyuan"
OFFICIAL_COMMIT_API = "https://api.github.com/repos/siyuan-note/siyuan/commits/master"
OFFICIAL_DOCS = [
    {"name": "api-zh", "filename": "API_zh_CN.md", "repo_path": "docs/API.zh-CN.md"},
    {"name": "api-en", "filename": "API.md", "repo_path": "docs/API.md"},
    {"name": "api-router", "filename": "kernel-api-router.go", "repo_path": "kernel/api/router.go"},
    {"name": "document-hpath", "filename": "DOCUMENT-HPATH.md", "repo_path": "docs/DOCUMENT-HPATH.md"},
]


def detect_references_dir(explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit).expanduser()
    candidates = [Path.cwd() / "skill" / "references", Path.cwd() / "references"]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    fail(
        {
            "error": "references directory not found",
            "searched": [str(p) for p in candidates],
            "repair": "Run from the repository root or pass --references-dir /path/to/skill/references.",
        }
    )


def latest_commit(timeout: float) -> str | None:
    """Best effort: pin all files to one upstream commit so they stay consistent."""
    try:
        return json.loads(fetch_text_url(OFFICIAL_COMMIT_API, timeout=timeout, attempts=2))["sha"]
    except (FetchError, KeyError, TypeError, json.JSONDecodeError):
        return None


def update_docs(references_dir: str | None, timeout: float) -> dict[str, Any]:
    official_dir = detect_references_dir(references_dir) / "official"
    commit = latest_commit(timeout)
    ref = commit or "master"

    # Fetch everything before writing so a network failure never leaves a half-updated set.
    fetched = []
    for item in OFFICIAL_DOCS:
        raw_url = f"https://raw.githubusercontent.com/siyuan-note/siyuan/{ref}/{item['repo_path']}"
        try:
            fetched.append((item, raw_url, fetch_text_url(raw_url, timeout=timeout)))
        except FetchError as exc:
            fail({**exc.info, "note": "no files were written"})

    official_dir.mkdir(parents=True, exist_ok=True)
    files = []
    changed = []
    for item, raw_url, text in fetched:
        target = official_dir / item["filename"]
        old = target.read_text(encoding="utf-8") if target.exists() else None
        if old != text:
            target.write_text(text, encoding="utf-8")
            changed.append(item["filename"])
        encoded = text.encode("utf-8")
        files.append(
            {
                "name": item["name"],
                "path": item["filename"],
                "source_url": f"{OFFICIAL_REPOSITORY}/blob/{ref}/{item['repo_path']}",
                "bytes": len(encoded),
                "sha256": hashlib.sha256(encoded).hexdigest(),
            }
        )
    manifest = {"official_repository": OFFICIAL_REPOSITORY, "commit": commit, "files": files}
    manifest_path = official_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "official_dir": str(official_dir), "commit": commit, "changed": changed, "files": files}
