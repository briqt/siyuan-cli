from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

try:
    from . import __version__
except ImportError:  # Allows `python src/cli.py --help` during local development.
    __version__ = "0.1.0"


SKILL_NAME = "siyuan-cli"
DEFAULT_BASE_URL = "http://127.0.0.1:6806"
OFFICIAL_API_DOC_URL = "https://github.com/siyuan-note/siyuan/blob/master/API.md"
OFFICIAL_API_RAW_URL = "https://raw.githubusercontent.com/siyuan-note/siyuan/master/API.md"
OFFICIAL_API_DOC_ZH_URL = "https://github.com/siyuan-note/siyuan/blob/master/API_zh_CN.md"
OFFICIAL_API_RAW_ZH_URL = "https://raw.githubusercontent.com/siyuan-note/siyuan/master/API_zh_CN.md"
OFFICIAL_ROUTER_URL = "https://github.com/siyuan-note/siyuan/blob/master/kernel/api/router.go"
OFFICIAL_ROUTER_RAW_URL = "https://raw.githubusercontent.com/siyuan-note/siyuan/master/kernel/api/router.go"
OFFICIAL_DOCS = [
    {
        "name": "api-zh",
        "filename": "API_zh_CN.md",
        "source_url": OFFICIAL_API_DOC_ZH_URL,
        "raw_url": OFFICIAL_API_RAW_ZH_URL,
    },
    {
        "name": "api-en",
        "filename": "API.md",
        "source_url": OFFICIAL_API_DOC_URL,
        "raw_url": OFFICIAL_API_RAW_URL,
    },
    {
        "name": "api-router",
        "filename": "kernel-api-router.go",
        "source_url": OFFICIAL_ROUTER_URL,
        "raw_url": OFFICIAL_ROUTER_RAW_URL,
    },
]
CONFIG_TEMPLATE = {
    "active": "default",
    "profiles": {
        "default": {
            "base_url": DEFAULT_BASE_URL,
            "token": "",
            "timeout_seconds": 30,
            "default_notebook": "",
            "default_doc_path": "/Inbox",
        }
    },
}


def eprint(message: str) -> None:
    print(message, file=sys.stderr)


def json_out(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def user_config_path() -> Path:
    return Path.home() / ".config" / "agent-skills" / SKILL_NAME / "config.json"


def searched_config_paths(explicit: str | None = None) -> list[Path]:
    paths: list[Path] = []
    if explicit:
        paths.append(Path(explicit).expanduser())
    paths.extend(
        [
            Path.cwd() / ".config.json",
            Path.cwd() / "skill" / ".config.json",
            user_config_path(),
        ]
    )
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in paths:
        resolved = path.expanduser()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(resolved)
    return unique


def init_config(overwrite: bool = False) -> dict[str, Any]:
    target = user_config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not overwrite:
        return {
            "ok": True,
            "message": "config already exists",
            "path": str(target),
            "next": f"open {target}",
        }
    target.write_text(json.dumps(CONFIG_TEMPLATE, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "ok": True,
        "message": "created config from template",
        "path": str(target),
        "next": f"open {target}",
    }


def fail(payload: dict[str, Any], code: int = 1) -> None:
    eprint(json.dumps(payload, ensure_ascii=False, indent=2))
    raise SystemExit(code)


def load_config(args: argparse.Namespace) -> tuple[Path, str, dict[str, Any]]:
    searched = searched_config_paths(getattr(args, "config", None))
    for path in searched:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            fail(
                {
                    "error": "invalid config json",
                    "path": str(path),
                    "detail": str(exc),
                    "searched": [str(p) for p in searched],
                    "repair": f"siyuan-cli init-config && open {user_config_path()}",
                }
            )
        profiles = data.get("profiles")
        if not isinstance(profiles, dict):
            fail(
                {
                    "error": "config missing profiles object",
                    "path": str(path),
                    "searched": [str(p) for p in searched],
                    "repair": f"siyuan-cli init-config && open {user_config_path()}",
                }
            )
        profile_name = args.profile or data.get("active") or "default"
        profile = profiles.get(profile_name)
        if not isinstance(profile, dict):
            fail(
                {
                    "error": "profile not found",
                    "profile": profile_name,
                    "path": str(path),
                    "available_profiles": sorted(profiles.keys()),
                }
            )
        base_url = profile.get("base_url") or DEFAULT_BASE_URL
        token = profile.get("token", "")
        if not isinstance(base_url, str) or not base_url.startswith(("http://", "https://")):
            fail({"error": "invalid base_url", "profile": profile_name, "path": str(path)})
        if not isinstance(token, str) or not token.strip():
            fail(
                {
                    "error": "SiYuan API token is not configured",
                    "profile": profile_name,
                    "path": str(path),
                    "searched": [str(p) for p in searched],
                    "repair": f"open {path}",
                    "repair_note": f"Set profiles.{profile_name}.token from SiYuan Settings > About.",
                }
            )
        return path, profile_name, profile
    fail(
        {
            "error": "config not found",
            "searched": [str(p) for p in searched],
            "repair": f"siyuan-cli init-config && open {user_config_path()}",
        }
    )


def read_text_arg(value: str | None, file_value: str | None, field: str) -> str:
    if value is not None and file_value is not None:
        fail({"error": f"pass either --{field} or --{field}-file, not both"})
    if file_value is not None:
        return Path(file_value).expanduser().read_text(encoding="utf-8")
    if value is not None:
        return value
    fail({"error": f"missing --{field} or --{field}-file"})


def parse_json_arg(raw: str | None, file_path: str | None) -> dict[str, Any]:
    if raw and file_path:
        fail({"error": "pass either --data or --data-file, not both"})
    if file_path:
        raw = Path(file_path).expanduser().read_text(encoding="utf-8")
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        fail({"error": "invalid json", "detail": str(exc)})
    if not isinstance(data, dict):
        fail({"error": "json payload must be an object"})
    return data


def fetch_text_url(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": f"{SKILL_NAME}/{__version__}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        fail({"error": "http error", "status": exc.code, "url": url})
    except urllib.error.URLError as exc:
        fail({"error": "network error", "url": url, "detail": str(exc)})


def detect_references_dir(explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit).expanduser()
    candidates = [
        Path.cwd() / "skill" / "references",
        Path.cwd() / "references",
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate
    fail(
        {
            "error": "references directory not found",
            "searched": [str(p) for p in candidates],
            "repair": "Run from the repository root or pass --references-dir /path/to/skill/references.",
        }
    )


def update_docs_payload(args: argparse.Namespace) -> dict[str, Any]:
    references_dir = detect_references_dir(args.references_dir)
    official_dir = references_dir / "official"
    official_dir.mkdir(parents=True, exist_ok=True)
    files = []
    for item in OFFICIAL_DOCS:
        text = fetch_text_url(item["raw_url"], timeout=args.timeout)
        target = official_dir / item["filename"]
        target.write_text(text, encoding="utf-8")
        files.append(
            {
                "name": item["name"],
                "path": str(target),
                "source_url": item["source_url"],
                "raw_url": item["raw_url"],
                "bytes": len(text.encode("utf-8")),
            }
        )
    manifest = {
        "official_repository": "https://github.com/siyuan-note/siyuan",
        "files": files,
    }
    manifest_path = official_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "ok": True,
        "references_dir": str(references_dir),
        "official_dir": str(official_dir),
        "manifest": str(manifest_path),
        "files": files,
    }


def api_post(profile: dict[str, Any], endpoint: str, payload: dict[str, Any] | None = None) -> Any:
    base_url = (profile.get("base_url") or DEFAULT_BASE_URL).rstrip("/")
    endpoint = endpoint if endpoint.startswith("/") else f"/{endpoint}"
    url = f"{base_url}{endpoint}"
    body = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
    timeout = int(profile.get("timeout_seconds") or 30)
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Token {profile['token']}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": f"{SKILL_NAME}/{__version__}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            response_body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="replace")
        fail({"error": "http error", "status": exc.code, "endpoint": endpoint, "body": response_body})
    except urllib.error.URLError as exc:
        fail({"error": "network error", "endpoint": endpoint, "detail": str(exc)})

    try:
        data = json.loads(response_body)
    except json.JSONDecodeError:
        return {"raw": response_body}

    if isinstance(data, dict) and data.get("code", 0) != 0:
        fail({"error": "SiYuan API error", "endpoint": endpoint, "response": data})
    return data


def api_upload_asset(profile: dict[str, Any], files: list[str], assets_dir: str = "/assets/") -> Any:
    import mimetypes
    import uuid

    base_url = (profile.get("base_url") or DEFAULT_BASE_URL).rstrip("/")
    url = f"{base_url}/api/asset/upload"
    timeout = int(profile.get("timeout_seconds") or 30)
    boundary = uuid.uuid4().hex

    parts: list[bytes] = []
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"assetsDirPath\"\r\n\r\n{assets_dir}\r\n".encode())
    for filepath in files:
        p = Path(filepath).expanduser()
        if not p.exists():
            fail({"error": "file not found", "path": str(p)})
        mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"file[]\"; filename=\"{p.name}\"\r\nContent-Type: {mime}\r\n\r\n".encode() + p.read_bytes() + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(parts)

    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={
            "Authorization": f"Token {profile['token']}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": f"{SKILL_NAME}/{__version__}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            response_body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="replace")
        fail({"error": "http error", "status": exc.code, "endpoint": "/api/asset/upload", "body": response_body})
    except urllib.error.URLError as exc:
        fail({"error": "network error", "endpoint": "/api/asset/upload", "detail": str(exc)})

    try:
        data = json.loads(response_body)
    except json.JSONDecodeError:
        return {"raw": response_body}
    if isinstance(data, dict) and data.get("code", 0) != 0:
        fail({"error": "SiYuan API error", "endpoint": "/api/asset/upload", "response": data})
    return data


def default_notebook(profile: dict[str, Any], explicit: str | None = None) -> str:
    notebook = explicit or profile.get("default_notebook")
    if not notebook:
        fail({"error": "missing notebook", "hint": "Pass --notebook or set default_notebook in config.json."})
    return notebook


def required_value(value: str | None, name: str) -> str:
    if not value:
        fail({"error": f"missing {name}"})
    return value


def command_payload(args: argparse.Namespace, profile: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    command = args.command
    if command == "api":
        return args.endpoint, parse_json_arg(args.data, args.data_file)
    if command == "version":
        return "/api/system/version", {}
    if command == "current-time":
        return "/api/system/currentTime", {}
    if command == "notebooks":
        return "/api/notebook/lsNotebooks", {}
    if command == "create-notebook":
        return "/api/notebook/createNotebook", {"name": args.name}
    if command == "rename-notebook":
        return "/api/notebook/renameNotebook", {"notebook": args.notebook, "name": args.name}
    if command == "open-notebook":
        return "/api/notebook/openNotebook", {"notebook": args.notebook}
    if command == "close-notebook":
        return "/api/notebook/closeNotebook", {"notebook": args.notebook}
    if command == "search":
        payload = {
            "query": args.query,
            "page": args.page,
            "pageSize": args.page_size,
        }
        if args.method:
            payload["method"] = args.method
        if args.types:
            payload["types"] = args.types
        if args.paths:
            payload["paths"] = args.paths
        return "/api/search/fullTextSearchBlock", payload
    if command == "sql":
        return "/api/query/sql", {"stmt": args.statement}
    if command == "get-block":
        return "/api/block/getBlockKramdown", {"id": args.id}
    if command == "children":
        return "/api/block/getChildBlocks", {"id": args.id}
    if command == "list-docs":
        return "/api/filetree/listDocsByPath", {"notebook": default_notebook(profile, args.notebook), "path": args.path}
    if command == "create-doc":
        markdown = read_text_arg(args.markdown, args.markdown_file, "markdown")
        return "/api/filetree/createDocWithMd", {"notebook": default_notebook(profile, args.notebook), "path": args.path, "markdown": markdown}
    if command == "rename-doc":
        if args.id:
            return "/api/filetree/renameDocByID", {"id": args.id, "title": args.title}
        return "/api/filetree/renameDoc", {"notebook": default_notebook(profile, args.notebook), "path": required_value(args.path, "--path"), "title": args.title}
    if command == "remove-doc":
        if args.id:
            return "/api/filetree/removeDocByID", {"id": args.id}
        return "/api/filetree/removeDoc", {"notebook": default_notebook(profile, args.notebook), "path": required_value(args.path, "--path")}
    if command == "hpath-by-id":
        return "/api/filetree/getHPathByID", {"id": args.id}
    if command == "path-by-id":
        return "/api/filetree/getPathByID", {"id": args.id}
    if command == "ids-by-hpath":
        return "/api/filetree/getIDsByHPath", {"path": args.path, "notebook": default_notebook(profile, args.notebook)}
    if command == "export-md":
        return "/api/export/exportMdContent", {"id": args.id}
    if command == "insert-block":
        data = read_text_arg(args.markdown, args.markdown_file, "markdown")
        payload = {
            "dataType": "markdown",
            "data": data,
            "nextID": args.next_id or "",
            "previousID": args.previous_id or "",
            "parentID": args.parent_id or "",
        }
        if not (payload["nextID"] or payload["previousID"] or payload["parentID"]):
            fail({"error": "missing insertion anchor", "hint": "Pass --next-id, --previous-id, or --parent-id."})
        return "/api/block/insertBlock", payload
    if command == "append-block":
        data = read_text_arg(args.markdown, args.markdown_file, "markdown")
        return "/api/block/appendBlock", {"parentID": args.parent_id, "dataType": "markdown", "data": data}
    if command == "prepend-block":
        data = read_text_arg(args.markdown, args.markdown_file, "markdown")
        return "/api/block/prependBlock", {"parentID": args.parent_id, "dataType": "markdown", "data": data}
    if command == "update-block":
        data = read_text_arg(args.markdown, args.markdown_file, "markdown")
        return "/api/block/updateBlock", {"id": args.id, "dataType": "markdown", "data": data}
    if command == "delete-block":
        return "/api/block/deleteBlock", {"id": args.id}
    if command == "fold-block":
        return "/api/block/foldBlock", {"id": args.id}
    if command == "unfold-block":
        return "/api/block/unfoldBlock", {"id": args.id}
    if command == "attrs":
        return "/api/attr/getBlockAttrs", {"id": args.id}
    if command == "set-attrs":
        return "/api/attr/setBlockAttrs", {"id": args.id, "attrs": parse_json_arg(args.attrs, args.attrs_file)}
    if command == "doc-outline":
        return "/api/outline/getDocOutline", {"id": args.id}
    fail({"error": "unknown command", "command": command})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Operate SiYuan notes through the local HTTP API.")
    parser.add_argument("--profile", help="Profile name from config.json.")
    parser.add_argument("--config", help="Explicit config.json path.")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init-config", help="Create the user config file.")
    init.add_argument("--overwrite", action="store_true")

    sub.add_parser("version", help="Get SiYuan system version.")
    sub.add_parser("current-time", help="Get SiYuan system time.")
    sub.add_parser("notebooks", help="List notebooks.")

    update_docs = sub.add_parser("update-docs", help="Overwrite bundled references with the latest official SiYuan docs.")
    update_docs.add_argument("--references-dir", help="Path to the skill references directory. Defaults to ./skill/references.")
    update_docs.add_argument("--timeout", type=int, default=30)

    api = sub.add_parser("api", help="Call any SiYuan API endpoint.")
    api.add_argument("endpoint", help="Endpoint such as /api/notebook/lsNotebooks.")
    api.add_argument("--data", help="JSON object payload.")
    api.add_argument("--data-file", help="Read JSON object payload from file.")

    search = sub.add_parser("search", help="Full-text search blocks.")
    search.add_argument("query")
    search.add_argument("--page", type=int, default=1)
    search.add_argument("--page-size", type=int, default=20)
    search.add_argument("--method", help="Optional SiYuan search method.")
    search.add_argument("--types", nargs="+", help="Optional block type filters.")
    search.add_argument("--paths", nargs="+", help="Optional path filters.")

    sql = sub.add_parser("sql", help="Execute a SiYuan SQL query.")
    sql.add_argument("statement")

    create_notebook = sub.add_parser("create-notebook", help="Create a notebook.")
    create_notebook.add_argument("name")

    rename_notebook = sub.add_parser("rename-notebook", help="Rename a notebook.")
    rename_notebook.add_argument("notebook")
    rename_notebook.add_argument("name")

    for name in ("open-notebook", "close-notebook"):
        notebook = sub.add_parser(name, help=f"{name.replace('-', ' ').title()}.")
        notebook.add_argument("notebook")

    get_block = sub.add_parser("get-block", help="Read a block as Kramdown.")
    get_block.add_argument("id")

    children = sub.add_parser("children", help="List child blocks.")
    children.add_argument("id")

    list_docs = sub.add_parser("list-docs", help="List documents under a notebook path.")
    list_docs.add_argument("--notebook", help="Notebook ID. Defaults to profile.default_notebook.")
    list_docs.add_argument("--path", default="/")

    create_doc = sub.add_parser("create-doc", help="Create a document with Markdown.")
    create_doc.add_argument("--notebook", help="Notebook ID. Defaults to profile.default_notebook.")
    create_doc.add_argument("--path", required=True, help="Document path, for example /Inbox/New note.")
    create_doc.add_argument("--markdown")
    create_doc.add_argument("--markdown-file")

    rename_doc = sub.add_parser("rename-doc", help="Rename a document by ID or notebook/path.")
    rename_doc.add_argument("--id")
    rename_doc.add_argument("--notebook", help="Required with --path unless default_notebook is configured.")
    rename_doc.add_argument("--path")
    rename_doc.add_argument("--title", required=True)

    remove_doc = sub.add_parser("remove-doc", help="Remove a document by ID or notebook/path.")
    remove_doc.add_argument("--id")
    remove_doc.add_argument("--notebook", help="Required with --path unless default_notebook is configured.")
    remove_doc.add_argument("--path")

    hpath = sub.add_parser("hpath-by-id", help="Get human-readable document path by block/doc ID.")
    hpath.add_argument("id")

    path = sub.add_parser("path-by-id", help="Get storage path by block/doc ID.")
    path.add_argument("id")

    ids_by_hpath = sub.add_parser("ids-by-hpath", help="Get document IDs by human-readable path.")
    ids_by_hpath.add_argument("path")
    ids_by_hpath.add_argument("--notebook", help="Notebook ID. Defaults to profile.default_notebook.")

    export_md = sub.add_parser("export-md", help="Export a document as Markdown content.")
    export_md.add_argument("id")

    insert = sub.add_parser("insert-block", help="Insert Markdown before, after, or inside an anchor block.")
    insert.add_argument("--next-id")
    insert.add_argument("--previous-id")
    insert.add_argument("--parent-id")
    insert.add_argument("--markdown")
    insert.add_argument("--markdown-file")

    for name in ("append-block", "prepend-block"):
        block = sub.add_parser(name, help=f"{name.replace('-', ' ').title()} with Markdown.")
        block.add_argument("parent_id")
        block.add_argument("--markdown")
        block.add_argument("--markdown-file")

    update = sub.add_parser("update-block", help="Replace a block with Markdown.")
    update.add_argument("id")
    update.add_argument("--markdown")
    update.add_argument("--markdown-file")

    delete = sub.add_parser("delete-block", help="Delete a block.")
    delete.add_argument("id")

    fold = sub.add_parser("fold-block", help="Fold a block.")
    fold.add_argument("id")

    unfold = sub.add_parser("unfold-block", help="Unfold a block.")
    unfold.add_argument("id")

    attrs = sub.add_parser("attrs", help="Get block attributes.")
    attrs.add_argument("id")

    set_attrs = sub.add_parser("set-attrs", help="Set custom block attributes.")
    set_attrs.add_argument("id")
    set_attrs.add_argument("--attrs", help="JSON object of attributes.")
    set_attrs.add_argument("--attrs-file", help="Read attributes JSON object from file.")

    upload_asset = sub.add_parser("upload-asset", help="Upload files to SiYuan assets.")
    upload_asset.add_argument("files", nargs="+", help="File paths to upload.")
    upload_asset.add_argument("--assets-dir", default="/assets/", help="Target assets directory path (default: /assets/).")

    doc_outline = sub.add_parser("doc-outline", help="Get document outline (heading tree).")
    doc_outline.add_argument("id", help="Document ID.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init-config":
        eprint("[profile: default]")
        json_out(init_config(args.overwrite))
        return 0
    if args.command == "update-docs":
        eprint("[profile: none]")
        json_out(update_docs_payload(args))
        return 0

    _config_path, profile_name, profile = load_config(args)
    eprint(f"[profile: {profile_name}]")

    if args.command == "upload-asset":
        result = api_upload_asset(profile, args.files, args.assets_dir)
        json_out(result)
        return 0

    endpoint, payload = command_payload(args, profile)
    result = api_post(profile, endpoint, payload)
    json_out(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
