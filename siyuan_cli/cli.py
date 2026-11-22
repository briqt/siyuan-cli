from __future__ import annotations

import argparse
from datetime import datetime
import html
import json
import re
import secrets
from pathlib import Path
from typing import Any, Callable

from . import __version__
from .client import (
    FetchError,
    SiYuanClient,
    eprint,
    fail,
    init_config,
    inspect_config,
    json_out,
    load_config,
    read_disable_update_check,
    user_data_dir,
)
from .docs import update_docs
from .update_check import check_update, is_update_disabled

BLOCK_ID_RE = re.compile(r"^\d{14}-[0-9a-z]{7}$")
NODE_ID_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"
SEARCH_TYPES = [
    "document", "heading", "list", "listItem", "codeBlock", "mathBlock", "table", "blockquote",
    "superBlock", "paragraph", "htmlBlock", "embedBlock", "databaseBlock", "audioBlock", "videoBlock",
    "iframeBlock", "widgetBlock", "callout", "tabs", "tabItem",
]
SEARCH_METHODS = {"keyword": 0, "query": 1, "sql": 2, "regex": 3}
SEARCH_ORDERS = {
    "type": 0, "created-asc": 1, "created-desc": 2, "updated-asc": 3, "updated-desc": 4,
    "content": 5, "relevance-asc": 6, "relevance-desc": 7,
}
EXPORT_FORMATS = ["md", "html", "preview", "docx", "sy", "md-zip"]
IMPORT_TYPES = ["md", "sy", "data"]
DB_ACTIONS = [
    "create", "search", "get", "render", "keys", "key_add", "key_update", "key_set_template", "key_remove",
    "item_add", "item_remove", "item_update", "items_add", "items_update",
    "view_get", "view_add", "view_duplicate", "view_remove", "view_update", "view_move",
    "view_field_move", "view_visibility_set", "view_filters_set", "view_sorts_set",
    "view_group_set", "view_layout_set", "unused", "clean",
]
SNIPPET_CHARS = 300

# Raw `api` calls to these endpoints get a stderr hint pointing at the dedicated command.
ENDPOINT_TO_COMMAND = {
    "/api/system/version": "version",
    "/api/system/currentTime": "current-time",
    "/api/notebook/lsNotebooks": "notebooks",
    "/api/notebook/openNotebook": "open-notebook <notebook-id>",
    "/api/notebook/closeNotebook": "close-notebook <notebook-id>",
    "/api/notebook/createNotebook": "create-notebook <name>",
    "/api/notebook/renameNotebook": "rename-notebook <notebook-id> <name>",
    "/api/notebook/removeNotebook": "remove-notebook <notebook-id>",
    "/api/notebook/getNotebookConf": "notebook-conf <notebook-id>",
    "/api/notebook/setNotebookConf": "set-notebook-conf <notebook-id> --conf '{...}'",
    "/api/filetree/listDocsByPath": "list-docs --notebook <nb> --path /",
    "/api/filetree/getHPathByID": "hpath-by-id <block-id>",
    "/api/filetree/getPathByID": "path-by-id <block-id>",
    "/api/filetree/getIDsByHPath": "ids-by-hpath <hpath> --notebook <nb>",
    "/api/filetree/createDocWithMd": "create-doc --notebook <nb> --path <path> --markdown '...'",
    "/api/filetree/createDocByParent": "create-doc --notebook <nb> --title <title> [--parent-id <id>] --markdown '...'",
    "/api/filetree/resolveDocPath": "resolve-doc-path <segment>... --notebook <nb>",
    "/api/filetree/getDocPaths": "doc-paths <doc-id>... --notebook <nb>",
    "/api/filetree/renameDoc": "rename-doc --notebook <nb> --path <path> --title <title>",
    "/api/filetree/renameDocByID": "rename-doc --id <doc-id> --title <title>",
    "/api/filetree/removeDoc": "remove-doc --notebook <nb> --path <path>",
    "/api/filetree/removeDocByID": "remove-doc --id <doc-id>",
    "/api/filetree/moveDocsByID": "move-doc <doc-id>... --to <parent-doc-or-notebook-id>",
    "/api/filetree/searchDocs": "search-docs <keyword>",
    "/api/filetree/createDailyNote": "daily-note --notebook <nb>",
    "/api/block/appendDailyNoteBlock": "daily-note --notebook <nb> --markdown '...'",
    "/api/block/prependDailyNoteBlock": "daily-note --notebook <nb> --prepend --markdown '...'",
    "/api/block/appendBlock": "append-block <parent-id> --markdown '...'",
    "/api/block/prependBlock": "prepend-block <parent-id> --markdown '...'",
    "/api/block/insertBlock": "insert-block --previous-id <id> --markdown '...'",
    "/api/block/updateBlock": "update-block <block-id> --markdown '...'",
    "/api/block/deleteBlock": "delete-block <block-id>",
    "/api/block/moveBlock": "move-block <block-id> --previous-id <id> | --parent-id <id>",
    "/api/block/foldBlock": "fold-block <block-id>",
    "/api/block/unfoldBlock": "unfold-block <block-id>",
    "/api/block/getBlockKramdown": "get-block <block-id>",
    "/api/block/getBlockKramdowns": "get-blocks <block-id>...",
    "/api/block/getChildBlocks": "children <block-id>",
    "/api/block/getBlockInfo": "block-info <block-id>",
    "/api/block/getDocInfo": "doc-info <doc-id>",
    "/api/block/getBlockBreadcrumb": "breadcrumb <block-id>",
    "/api/block/getRecentUpdatedBlocks": "recent",
    "/api/block/transferBlockRef": "transfer-ref <from-id> <to-id>",
    "/api/outline/getDocOutline": "doc-outline <doc-id>",
    "/api/export/exportMdContent": "export-md <doc-id>",
    "/api/attr/setBlockAttrs": "set-attrs <block-id> --attrs '{...}'",
    "/api/attr/getBlockAttrs": "attrs <block-id>",
    "/api/search/fullTextSearchBlock": "search <query>",
    "/api/search/searchTag": "tags <keyword>",
    "/api/query/sql": "sql '<SELECT ...>'",
    "/api/ref/getBacklink2": "backlinks <block-id>",
    "/api/tag/getTag": "tags",
    "/api/bookmark/getBookmark": "bookmarks",
    "/api/template/renderSprig": "render-sprig '<template>'",
    "/api/asset/upload": "upload-asset <file>...",
}


# --- argument helpers -------------------------------------------------------


def generate_node_id() -> str:
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    suffix = "".join(secrets.choice(NODE_ID_ALPHABET) for _ in range(7))
    return f"{stamp}-{suffix}"


def _read_utf8_file(file_value: str) -> str:
    p = Path(file_value).expanduser()
    try:
        return p.read_text(encoding="utf-8")
    except OSError as exc:
        fail({"error": "file read error", "path": str(p), "detail": str(exc)})


def read_text_arg(value: str | None, file_value: str | None, field: str, *, default: str | None = None) -> str:
    if value is not None and file_value is not None:
        fail({"error": f"pass either --{field} or --{field}-file, not both"})
    if file_value is not None:
        return _read_utf8_file(file_value)
    if value is not None:
        return value
    if default is not None:
        return default
    fail({"error": f"missing --{field} or --{field}-file"})


def parse_json_arg(raw: str | None, file_path: str | None, flag: str = "data") -> dict[str, Any]:
    if raw and file_path:
        fail({"error": f"pass either --{flag} or --{flag}-file, not both"})
    if file_path:
        raw = _read_utf8_file(file_path)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        fail({"error": "invalid json", "flag": f"--{flag}", "detail": str(exc)})
    if not isinstance(data, dict):
        fail({"error": "json payload must be an object", "flag": f"--{flag}"})
    return data


def block_id(value: str) -> str:
    """argparse type for IDs that may be interpolated into SQL or node creation."""
    if not BLOCK_ID_RE.match(value):
        raise argparse.ArgumentTypeError(f"invalid block ID {value!r} (expected like 20240101120000-abc1234)")
    return value


def notebook_id(profile: dict[str, Any], explicit: str | None) -> str:
    notebook = explicit or profile.get("default_notebook")
    if not notebook:
        fail({"error": "missing notebook", "hint": "Pass --notebook or set default_notebook in config.json."})
    return notebook


def resolve_doc_path(profile: dict[str, Any], path: str) -> str:
    """Absolute hPaths pass through; a bare title lands under default_doc_path."""
    if path.startswith("/"):
        return path
    base = (profile.get("default_doc_path") or "/").rstrip("/")
    return f"{base}/{path}"


def snippet(text: str | None, limit: int = SNIPPET_CHARS) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", "", text or "")).strip()
    return text if len(text) <= limit else text[:limit] + "…"


def with_data(response: Any, data: Any) -> Any:
    if isinstance(response, dict) and "data" in response:
        return {**response, "data": data}
    return response


def markdown_of(args: argparse.Namespace, *, default: str | None = None) -> str:
    return read_text_arg(args.markdown, args.markdown_file, "markdown", default=default)


def find_installed_skill_info() -> dict[str, str | None] | None:
    home = Path.home()
    candidates = [
        home / ".agents" / "skills" / "siyuan-cli" / "SKILL.md",
        home / ".claude" / "skills" / "siyuan-cli" / "SKILL.md",
        home / ".gemini" / "config" / "skills" / "siyuan-cli" / "SKILL.md",
        Path(__file__).resolve().parent.parent / "skills" / "siyuan-cli" / "SKILL.md",
    ]
    for path in candidates:
        if path.is_file():
            try:
                text = path.read_text(encoding="utf-8")
                m = re.search(r'^\s*version:\s*"?([0-9]+\.[0-9]+\.[0-9]+)"?\s*$', text, re.MULTILINE)
                return {"path": str(path), "version": m.group(1) if m else None}
            except OSError:
                continue
    return None


# --- command handlers -------------------------------------------------------

Handler = Callable[[argparse.Namespace, SiYuanClient], Any]


def simple(endpoint: str, build: Callable[[argparse.Namespace, dict[str, Any]], dict[str, Any]] | None = None) -> Handler:
    def handler(args: argparse.Namespace, client: SiYuanClient) -> Any:
        return client.post(endpoint, build(args, client.profile) if build else {})

    return handler


def cmd_doctor(args: argparse.Namespace) -> dict[str, Any]:
    skill_info = find_installed_skill_info()
    cfg_info = inspect_config(args.config, args.profile)
    report: dict[str, Any] = {
        "ok": True,
        "cli_version": __version__,
        "skill_version": skill_info["version"] if skill_info else None,
        "skill_path": skill_info["path"] if skill_info else None,
        "skill_matches_cli": (skill_info["version"] == __version__) if (skill_info and skill_info.get("version")) else None,
        "config_ok": cfg_info["ok"],
        "config_path": str(cfg_info["path"]) if "path" in cfg_info else None,
        "profile": cfg_info.get("profile_name"),
    }
    if not cfg_info["ok"]:
        report["ok"] = False
        report["config_error"] = cfg_info["error"]
        return report

    client = SiYuanClient(cfg_info["profile"])
    report["base_url"] = client.base_url
    try:
        ver_resp = client.post("/api/system/version", {}, raise_on_error=True)
        report["server_reachable"] = True
        report["server_version"] = ver_resp.get("data") if isinstance(ver_resp, dict) else None
    except FetchError as exc:
        report["ok"] = False
        report["server_reachable"] = False
        report["server_error"] = exc.info
        return report

    try:
        tools = client.mcp_list_tools(raise_on_error=True)
        report["mcp_available"] = True
        report["mcp_tool_count"] = len(tools)
    except FetchError as exc:
        report["mcp_available"] = False
        report["mcp_error"] = exc.info

    default_nb = cfg_info["profile"].get("default_notebook") or ""
    report["default_notebook"] = default_nb or None
    if default_nb:
        try:
            nbs = ((client.post("/api/notebook/lsNotebooks", {}, raise_on_error=True).get("data") or {}).get("notebooks")) or []
            report["default_notebook_exists"] = any(n.get("id") == default_nb for n in nbs if isinstance(n, dict))
            if not report["default_notebook_exists"]:
                report["ok"] = False
        except FetchError:
            report["default_notebook_exists"] = None
    return report


def cmd_api(args, client: SiYuanClient):
    endpoint = args.endpoint if args.endpoint.startswith("/") else f"/{args.endpoint}"
    payload = parse_json_arg(args.data, args.data_file)
    if endpoint in ENDPOINT_TO_COMMAND:
        eprint(f"[hint] This endpoint has a dedicated command: siyuan-cli {ENDPOINT_TO_COMMAND[endpoint]}")
    return client.post(endpoint, payload)


def cmd_mcp_tools(args, client: SiYuanClient):
    tools = client.mcp_list_tools()
    if args.tool:
        for t in tools:
            if t.get("name") == args.tool:
                return {"code": 0, "msg": "", "data": t}
        fail({"error": "MCP tool not found", "tool": args.tool, "available_tools": sorted(t.get("name", "") for t in tools)})
    summary = []
    for t in tools:
        props = (t.get("inputSchema") or {}).get("properties") or {}
        actions = (props.get("action") or {}).get("enum") or []
        first_line = ((t.get("description") or "").splitlines() or [""])[0]
        summary.append({"name": t.get("name"), "actions": actions, "summary": first_line})
    return {"code": 0, "msg": "", "data": {"count": len(summary), "tools": summary}}


def cmd_mcp(args, client: SiYuanClient):
    payload = parse_json_arg(args.args, args.args_file, "args")
    if args.action and "action" not in payload:
        payload["action"] = args.action
    return client.mcp_call(args.tool, payload)


def cmd_notebook_icon(args, client: SiYuanClient):
    if args.random:
        return client.mcp_call("notebook", {"action": "random_icon", "id": args.notebook})
    if not args.icon:
        fail({"error": "notebook-icon requires <icon> code (e.g. 1f4d4) or --random"})
    return client.mcp_call("notebook", {"action": "set_icon", "id": args.notebook, "icon": args.icon})


def cmd_search(args, client: SiYuanClient):
    payload: dict[str, Any] = {"query": args.query, "page": args.page, "pageSize": args.page_size}
    payload["method"] = SEARCH_METHODS[args.method]
    payload["orderBy"] = SEARCH_ORDERS[args.order_by]
    payload["groupBy"] = 1 if args.group_by_doc else 0
    if args.types:
        payload["types"] = {t: True for t in args.types}
    paths = list(args.notebook or []) + list(args.paths or [])
    if paths:
        payload["paths"] = paths
    response = client.post("/api/search/fullTextSearchBlock", payload)
    if args.raw or args.method == "sql":
        return response
    data = response.get("data") or {}
    blocks = [
        {
            "id": b.get("id"),
            "rootID": b.get("rootID"),
            "box": b.get("box"),
            "hPath": b.get("hPath"),
            "type": b.get("type"),
            "subType": b.get("subType") or None,
            "content": snippet(b.get("content")),
        }
        for b in data.get("blocks") or []
    ]
    return with_data(
        response,
        {
            "matchedBlockCount": data.get("matchedBlockCount"),
            "matchedRootCount": data.get("matchedRootCount"),
            "pageCount": data.get("pageCount"),
            "blocks": blocks,
        },
    )


def cmd_semantic_search(args, client: SiYuanClient):
    return client.mcp_call(
        "search",
        {
            "action": "semantic",
            "query": args.query,
            "page": args.page,
            "pageSize": args.page_size,
            "notebook": ",".join(args.notebook) if args.notebook else None,
            "path": ",".join(args.paths) if args.paths else None,
            "type": args.type,
        },
    )


def cmd_search_assets(args, client: SiYuanClient):
    return client.mcp_call(
        "search",
        {
            "action": "asset",
            "query": args.query,
            "ext": args.ext,
            "page": args.page,
            "pageSize": args.page_size,
        },
    )


def cmd_sql(args, client: SiYuanClient):
    response = client.post("/api/query/sql", {"stmt": args.statement})
    if isinstance(response, dict) and response.get("truncated"):
        eprint(
            f"[warn] Result truncated at the server default limit ({response.get('limit')} rows = Settings > Search > result count). "
            "Add an explicit LIMIT/OFFSET with a stable ORDER BY (e.g. ORDER BY hpath, id); use SELECT COUNT(*) for totals."
        )
    return response


def cmd_search_docs(args, client: SiYuanClient):
    response = client.post("/api/filetree/searchDocs", {"k": args.keyword})
    docs = [
        {"id": Path(d.get("path", "")).stem or None, "box": d.get("box"), "hPath": d.get("hPath"), "path": d.get("path")}
        for d in response.get("data") or []
    ]
    return with_data(response, docs)


def cmd_backlinks(args, client: SiYuanClient):
    if args.blocks:
        stmt = (
            "SELECT b.id, b.root_id, b.box, b.hpath, b.type, b.content, r.def_block_id "
            "FROM refs r JOIN blocks b ON b.id = r.block_id "
            f"WHERE r.def_block_id = '{args.id}' OR r.def_block_root_id = '{args.id}' "
            "ORDER BY b.hpath, b.id LIMIT 9999"
        )
        return cmd_sql(argparse.Namespace(statement=stmt), client)
    response = client.post("/api/ref/getBacklink2", {"id": args.id, "k": args.keyword or "", "mk": args.keyword or ""})
    data = response.get("data") or {}

    def compact(items):
        return [
            {"id": x.get("id"), "box": x.get("box"), "hPath": x.get("hPath"), "nodeType": x.get("nodeType"), "count": x.get("count")}
            for x in items or []
        ]

    result = {"backlinkCount": data.get("linkRefsCount"), "backlinks": compact(data.get("backlinks"))}
    if args.mentions:
        result.update({"mentionCount": data.get("mentionsCount"), "mentions": compact(data.get("backmentions"))})
    return with_data(response, result)


def cmd_recent(args, client: SiYuanClient):
    response = client.post("/api/block/getRecentUpdatedBlocks", {})
    blocks = [
        {
            "id": b.get("id"),
            "rootID": b.get("rootID"),
            "hPath": b.get("hPath"),
            "type": b.get("type"),
            "updated": (b.get("ial") or {}).get("updated"),
            "content": snippet(b.get("content"), 120),
        }
        for b in (response.get("data") or [])[: args.limit]
    ]
    return with_data(response, blocks)


def cmd_tags(args, client: SiYuanClient):
    if args.keyword:
        return client.post("/api/search/searchTag", {"k": args.keyword})
    return client.post("/api/tag/getTag", {"ignoreMaxListHint": True})


def cmd_resolve_doc_path(args, client: SiYuanClient):
    start: dict[str, Any] = {"kind": "document", "id": args.start_id} if args.start_id else {"kind": "root"}
    payload = {
        "notebook": notebook_id(client.profile, args.notebook),
        "start": start,
        "segments": args.segments,
    }
    return client.post("/api/filetree/resolveDocPath", payload)


def cmd_doc_paths(args, client: SiYuanClient):
    payload: dict[str, Any] = {
        "notebook": notebook_id(client.profile, args.notebook),
        "ids": args.ids,
    }
    if args.include_icons:
        payload["includeIcons"] = True
    return client.post("/api/filetree/getDocPaths", payload)


def cmd_create_doc(args, client: SiYuanClient):
    nb = notebook_id(client.profile, args.notebook)
    if args.title is not None and args.path is not None:
        fail({"error": "pass either --title (structured parent-ID mode) or --path (hPath mode), not both"})
    if args.title is not None:
        payload: dict[str, Any] = {
            "notebook": nb,
            "parentID": args.parent_id if args.parent_id else None,
            "id": args.id or generate_node_id(),
            "title": {"format": "plain", "text": args.title},
            "markdown": markdown_of(args, default=""),
        }
        if args.tags:
            payload["tags"] = args.tags
        if args.with_math:
            payload["withMath"] = True
        if args.template_path:
            payload["docCreateTemplatePath"] = args.template_path
        if args.expected_parent_revision:
            payload["expectedParentRevision"] = args.expected_parent_revision
        return client.post("/api/filetree/createDocByParent", payload)

    if not args.path:
        fail({"error": "create-doc requires --title <title> (preferred for literal '/' titles) or --path <hpath>"})
    if args.parent_id or args.id or args.tags or args.with_math or args.template_path or args.expected_parent_revision:
        fail({"error": "--parent-id/--id/--tags/--with-math/--template-path require --title mode"})
    return client.post(
        "/api/filetree/createDocWithMd",
        {
            "notebook": nb,
            "path": resolve_doc_path(client.profile, args.path),
            "markdown": markdown_of(args),
        },
    )


def cmd_rename_doc(args, client: SiYuanClient):
    if args.id:
        return client.post("/api/filetree/renameDocByID", {"id": args.id, "title": args.title})
    if not args.path:
        fail({"error": "rename-doc requires --id or --path"})
    return client.post("/api/filetree/renameDoc", {"notebook": notebook_id(client.profile, args.notebook), "path": args.path, "title": args.title})


def cmd_remove_doc(args, client: SiYuanClient):
    if args.id:
        return client.post("/api/filetree/removeDocByID", {"id": args.id})
    if not args.path:
        fail(
            {
                "error": "remove-doc requires --id or --path",
                "examples": [
                    "siyuan-cli remove-doc --id <doc-id>",
                    "siyuan-cli remove-doc --notebook <nb-id> --path /path/to/doc.sy",
                ],
            }
        )
    return client.post("/api/filetree/removeDoc", {"notebook": notebook_id(client.profile, args.notebook), "path": args.path})


def cmd_move_doc(args, client: SiYuanClient):
    if args.notebook:
        if len(args.ids) != 1:
            fail({"error": "cross-notebook move (--notebook) accepts one document ID at a time"})
        parent_id = "" if args.to == args.notebook else args.to
        return client.mcp_call("document", {"action": "move", "id": args.ids[0], "notebook": args.notebook, "parentID": parent_id})
    return client.post("/api/filetree/moveDocsByID", {"fromIDs": args.ids, "toID": args.to})


def cmd_daily_note(args, client: SiYuanClient):
    notebook = notebook_id(client.profile, args.notebook)
    if args.markdown is None and args.markdown_file is None:
        if args.prepend:
            fail({"error": "--prepend needs --markdown or --markdown-file"})
        return client.post("/api/filetree/createDailyNote", {"notebook": notebook})
    endpoint = "/api/block/prependDailyNoteBlock" if args.prepend else "/api/block/appendDailyNoteBlock"
    return client.post(endpoint, {"notebook": notebook, "dataType": "markdown", "data": markdown_of(args)})


def cmd_insert_block(args, client: SiYuanClient):
    payload = {
        "dataType": "markdown",
        "data": markdown_of(args),
        "nextID": args.next_id or "",
        "previousID": args.previous_id or "",
        "parentID": args.parent_id or "",
    }
    if not (payload["nextID"] or payload["previousID"] or payload["parentID"]):
        fail({"error": "missing insertion anchor", "hint": "Pass --next-id, --previous-id, or --parent-id."})
    return client.post("/api/block/insertBlock", payload)


def cmd_update_block(args, client: SiYuanClient):
    payload: dict[str, Any] = {"id": args.id, "dataType": "markdown", "data": markdown_of(args)}
    if args.lock_type:
        payload["lockType"] = True
    return client.post("/api/block/updateBlock", payload)


def cmd_move_block(args, client: SiYuanClient):
    if not (args.previous_id or args.parent_id):
        fail({"error": "missing move anchor", "hint": "Pass --previous-id (move after it) or --parent-id (move to first child)."})
    payload: dict[str, Any] = {"id": args.id}
    if args.previous_id:
        payload["previousID"] = args.previous_id
    if args.parent_id:
        payload["parentID"] = args.parent_id
    return client.post("/api/block/moveBlock", payload)


def cmd_transfer_ref(args, client: SiYuanClient):
    payload: dict[str, Any] = {"fromID": args.from_id, "toID": args.to_id}
    if args.ref_ids:
        payload["refIDs"] = args.ref_ids
    return client.post("/api/block/transferBlockRef", payload)


def cmd_upload_asset(args, client: SiYuanClient):
    return client.upload_assets(args.files, args.assets_dir)


def cmd_export(args, client: SiYuanClient):
    if args.format == "md" and not args.output:
        return client.post("/api/export/exportMdContent", {"id": args.id})
    output_dir = str(Path(args.output).expanduser().resolve()) if args.output else None
    return client.mcp_call("export", {"action": args.format, "id": args.id, "output": output_dir})


def cmd_export_data(args, client: SiYuanClient):
    output_dir = str(Path(args.output).expanduser().resolve()) if args.output else None
    return client.mcp_call("export", {"action": "data", "output": output_dir})


def cmd_import(args, client: SiYuanClient):
    abs_path = str(Path(args.path).expanduser().resolve())
    nb = None if args.type == "data" else notebook_id(client.profile, args.notebook)
    return client.mcp_call(
        "import",
        {
            "action": args.type,
            "path": abs_path,
            "notebook": nb,
            "targetPath": args.target_path,
        },
    )


def cmd_db(args, client: SiYuanClient):
    action = args.action.replace("-", "_")
    if action not in DB_ACTIONS:
        fail({"error": "invalid database action", "action": args.action, "allowed_actions": DB_ACTIONS})
    payload = parse_json_arg(args.args, args.args_file, "args")
    payload["action"] = action
    mapping = {
        "id": args.id,
        "blockID": args.block_id,
        "viewID": args.view_id,
        "keyword": args.keyword,
        "query": args.query,
        "parentID": args.parent_id,
        "previousID": args.previous_id,
        "nextID": args.next_id,
        "name": args.name,
        "primaryKeyName": args.primary_key_name,
        "layout": args.layout,
        "keyID": args.key_id,
        "type": args.type,
        "itemID": args.item_id,
        "notebook": args.notebook,
        "page": args.page,
        "pageSize": args.page_size,
        "revision": args.revision,
    }
    for k, v in mapping.items():
        if v is not None and k not in payload:
            payload[k] = v
    if args.value is not None and "value" not in payload:
        payload["value"] = parse_json_arg(args.value, None, "value")
    return client.mcp_call("database", payload)


def cmd_template(args, client: SiYuanClient):
    action = args.action.replace("-", "_")
    content = read_text_arg(args.content, args.content_file, "content", default="") if (args.content is not None or args.content_file is not None) else None
    return client.mcp_call(
        "template",
        {
            "action": action,
            "keyword": args.keyword,
            "path": args.path,
            "id": args.id,
            "name": args.name,
            "content": content,
            "overwrite": True if args.overwrite else None,
        },
    )


def cmd_history(args, client: SiYuanClient):
    return client.mcp_call(
        "history",
        {
            "action": args.action,
            "query": args.query,
            "notebook": args.notebook,
            "op": args.op,
            "type": args.type,
            "page": args.page,
            "path": args.path,
        },
    )


def cmd_repo(args, client: SiYuanClient):
    action = args.action.replace("-", "_")
    return client.mcp_call(
        "repo",
        {
            "action": action,
            "id": args.id,
            "name": args.name,
            "memo": args.memo,
            "left": args.left,
            "right": args.right,
            "keyword": args.keyword,
            "page": args.page,
            "tag": True if args.only_tagged else None,
        },
    )


def cmd_inbox(args, client: SiYuanClient):
    nb = notebook_id(client.profile, args.notebook) if args.action == "convert" else args.notebook
    return client.mcp_call(
        "inbox",
        {
            "action": args.action,
            "id": args.id,
            "ids": ",".join(args.ids) if args.ids else None,
            "notebook": nb,
            "parentID": args.parent_id,
            "page": args.page,
            "remove_after": False if args.keep else None,
        },
    )


# --- parser -----------------------------------------------------------------


def add_markdown_args(parser: argparse.ArgumentParser, required: bool = True) -> None:
    group = parser.add_mutually_exclusive_group(required=required)
    group.add_argument("--markdown", help="Markdown content.")
    group.add_argument("--markdown-file", help="Read Markdown content from a UTF-8 file (preferred for long content).")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="siyuan-cli", description="Operate SiYuan notes through the official HTTP API and built-in MCP.")
    parser.add_argument(
        "-V", "--version", action="version", version=f"siyuan-cli {__version__}",
        help="Show the siyuan-cli version and exit (for the connected server's version, use the `version` command).",
    )
    parser.add_argument("--profile", help="Profile name from config.json.")
    parser.add_argument("--config", help="Explicit config.json path.")
    parser.add_argument("--no-update-check", action="store_true", help="Disable update checks and cached stderr notices.")
    sub = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    def cmd(name: str, handler: Handler | None, help: str, needs_config: bool = True) -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=help, description=help)
        p.set_defaults(handler=handler, needs_config=needs_config)
        return p

    # maintenance & diagnostics
    p = cmd("init-config", None, "Create ~/.config/agent-skills/siyuan-cli/config.json.", needs_config=False)
    p.add_argument("--overwrite", action="store_true")
    p = cmd("update-docs", None, "Refresh vendored official SiYuan API references.", needs_config=False)
    p.add_argument("--references-dir", help="Path to the skill references directory. Defaults to ./skills/siyuan-cli/references.")
    p.add_argument("--timeout", type=int, default=30)
    cmd("check-update", None, "Check GitHub release & notice feed without requiring SiYuan.", needs_config=False)
    cmd("doctor", None, "Diagnose CLI/Skill versions, config, server connectivity, and /mcp availability.", needs_config=False)

    # system & workspace
    cmd("version", simple("/api/system/version"), "Get the connected SiYuan server's version (for the CLI version use -V/--version).")
    cmd("server-version", simple("/api/system/version"), "Alias of `version`: the connected SiYuan server's version.")
    cmd("current-time", simple("/api/system/currentTime"), "Get SiYuan system time.")
    cmd("workspaces", lambda _a, c: c.mcp_call("workspace", {"action": "info"}), "Get current SiYuan workspace info and validity.")
    cmd("workspace-list", lambda _a, c: c.mcp_call("workspace", {"action": "list"}), "List registered SiYuan workspace paths.")

    # raw passthrough escape hatches
    p = cmd("api", cmd_api, "Call any SiYuan /api/* endpoint (only when no dedicated command exists).")
    p.add_argument("endpoint", help="Endpoint such as /api/notebook/lsNotebooks.")
    p.add_argument("--data", help="JSON object payload.")
    p.add_argument("--data-file", help="Read JSON object payload from file.")

    p = cmd("mcp-tools", cmd_mcp_tools, "List built-in SiYuan /mcp tools or inspect one tool's full schema.")
    p.add_argument("tool", nargs="?", help="Optional MCP tool name (e.g. database, document, pdf) for full schema.")

    p = cmd("mcp", cmd_mcp, "Call any built-in SiYuan /mcp tool directly.")
    p.add_argument("tool", help="Built-in MCP tool name (e.g. database, pdf, image, bazaar).")
    p.add_argument("action", nargs="?", help="Optional action parameter for macro tools.")
    p.add_argument("--args", help="JSON object arguments.")
    p.add_argument("--args-file", help="Read JSON object arguments from file.")

    # notebooks
    cmd("notebooks", simple("/api/notebook/lsNotebooks"), "List notebooks.")
    p = cmd("create-notebook", simple("/api/notebook/createNotebook", lambda a, _: {"name": a.name}), "Create a notebook.")
    p.add_argument("name")
    p = cmd("rename-notebook", simple("/api/notebook/renameNotebook", lambda a, _: {"notebook": a.notebook, "name": a.name}), "Rename a notebook.")
    p.add_argument("notebook")
    p.add_argument("name")
    for name, endpoint in (
        ("open-notebook", "/api/notebook/openNotebook"),
        ("close-notebook", "/api/notebook/closeNotebook"),
        ("remove-notebook", "/api/notebook/removeNotebook"),
        ("notebook-conf", "/api/notebook/getNotebookConf"),
    ):
        p = cmd(name, simple(endpoint, lambda a, _, ep=endpoint: {"notebook": a.notebook}), f"{name.replace('-', ' ').capitalize()}.")
        p.add_argument("notebook", help="Notebook ID.")
    p = cmd(
        "set-notebook-conf",
        simple("/api/notebook/setNotebookConf", lambda a, _: {"notebook": a.notebook, "conf": parse_json_arg(a.conf, a.conf_file, "conf")}),
        "Update notebook configuration object.",
    )
    p.add_argument("notebook", help="Notebook ID.")
    p.add_argument("--conf", help="Notebook conf JSON object.")
    p.add_argument("--conf-file", help="Read notebook conf JSON object from file.")
    p = cmd("notebook-icon", cmd_notebook_icon, "Set or randomize a notebook icon.")
    p.add_argument("notebook", help="Notebook ID.")
    p.add_argument("icon", nargs="?", help="Unicode hex icon code (e.g. 1f4d4).")
    p.add_argument("--random", action="store_true", help="Assign a random icon.")

    # read / search
    p = cmd("search", cmd_search, "Full-text search blocks (compact output; --raw for the full API response).")
    p.add_argument("query")
    p.add_argument("--page", type=int, default=1)
    p.add_argument("--page-size", type=int, default=20)
    p.add_argument("--method", choices=list(SEARCH_METHODS), default="keyword", help="keyword (default), query (query syntax), sql, regex.")
    p.add_argument("--types", nargs="+", choices=SEARCH_TYPES, metavar="TYPE", help=f"Only these block types: {', '.join(SEARCH_TYPES)}.")
    p.add_argument("--notebook", nargs="+", help="Limit to notebook IDs.")
    p.add_argument("--paths", nargs="+", help="Limit to storage paths like <notebook-id>/<doc-id>.sy.")
    p.add_argument("--order-by", choices=list(SEARCH_ORDERS), default="type")
    p.add_argument("--group-by-doc", action="store_true", help="Group matches by document.")
    p.add_argument("--raw", action="store_true", help="Print the full API response.")

    p = cmd("semantic-search", cmd_semantic_search, "Semantic search over blocks (requires SiYuan AI embedding configured).")
    p.add_argument("query")
    p.add_argument("--page", type=int, default=1)
    p.add_argument("--page-size", type=int, default=20)
    p.add_argument("--notebook", nargs="+", help="Limit to notebook IDs.")
    p.add_argument("--paths", nargs="+", help="Limit to storage paths.")
    p.add_argument("--type", choices=SEARCH_TYPES, help="Filter by block type.")

    p = cmd("search-assets", cmd_search_assets, "Full-text search inside indexed attachments (PDF/Office/txt).")
    p.add_argument("query")
    p.add_argument("--ext", help="Optional extension filter (e.g. .pdf).")
    p.add_argument("--page", type=int, default=1)
    p.add_argument("--page-size", type=int, default=20)

    p = cmd("asset-content", lambda a, c: c.mcp_call("search", {"action": "getasset", "path": a.path}), "Read full indexed text of an attachment.")
    p.add_argument("path", help="Asset path such as assets/foo.pdf.")

    p = cmd("sql", cmd_sql, "Execute a read-only SQL query (warns on stderr when the server truncated the result).")
    p.add_argument("statement")
    cmd("sql-schema", lambda _a, c: c.mcp_call("sql", {"action": "schema"}), "Get official SQL table definitions, block type codes, and query guide.")

    p = cmd("search-docs", cmd_search_docs, "Find documents by title/path keyword.")
    p.add_argument("keyword")

    p = cmd("get-block", simple("/api/block/getBlockKramdown", lambda a, _: {"id": a.id}), "Read a block as Kramdown.")
    p.add_argument("id")
    p = cmd("get-blocks", simple("/api/block/getBlockKramdowns", lambda a, _: {"ids": a.ids}), "Read several blocks as Kramdown in one call.")
    p.add_argument("ids", nargs="+")
    p = cmd("block-dom", lambda a, c: c.mcp_call("block", {"action": "dom", "id": a.id}), "Read a block's rendered SiYuan DOM.")
    p.add_argument("id")
    p = cmd("tree-stat", lambda a, c: c.mcp_call("block", {"action": "tree_stat", "id": a.id}), "Get document/subtree statistics.")
    p.add_argument("id")
    p = cmd("children", simple("/api/block/getChildBlocks", lambda a, _: {"id": a.id}), "List child blocks.")
    p.add_argument("id")
    p = cmd("block-info", simple("/api/block/getBlockInfo", lambda a, _: {"id": a.id}), "Get a block's document, notebook, and path.")
    p.add_argument("id")
    p = cmd("doc-info", simple("/api/block/getDocInfo", lambda a, _: {"id": a.id}), "Get document info (title, attrs, ref and subdoc counts).")
    p.add_argument("id")
    p = cmd("breadcrumb", simple("/api/block/getBlockBreadcrumb", lambda a, _: {"id": a.id}), "Get the heading/list ancestry of a block.")
    p.add_argument("id")
    p = cmd("doc-outline", simple("/api/outline/getDocOutline", lambda a, _: {"id": a.id}), "Get document outline (heading tree).")
    p.add_argument("id", help="Document ID.")
    p = cmd("export-md", simple("/api/export/exportMdContent", lambda a, _: {"id": a.id}), "Export a document as Markdown content.")
    p.add_argument("id")
    p = cmd("recent", cmd_recent, "List recently updated blocks.")
    p.add_argument("--limit", type=int, default=20)
    p = cmd("backlinks", cmd_backlinks, "List documents referencing a block/document.")
    p.add_argument("id", type=block_id)
    p.add_argument("--keyword", help="Filter backlinks by keyword.")
    p.add_argument("--mentions", action="store_true", help="Also list unlinked mentions.")
    p.add_argument("--blocks", action="store_true", help="List the referencing blocks with content (via SQL) instead of documents.")
    p = cmd("refresh-backlinks", lambda a, c: c.mcp_call("ref", {"action": "refresh", "id": a.id}), "Refresh backlink index for a document/block.")
    p.add_argument("id")

    # tags & bookmarks
    p = cmd("tags", cmd_tags, "List the tag tree, or search tags by keyword.")
    p.add_argument("keyword", nargs="?")
    p = cmd("rename-tag", lambda a, c: c.mcp_call("tag", {"action": "rename", "old": a.old, "new": a.new}), "Rename a tag across the workspace.")
    p.add_argument("old")
    p.add_argument("new")
    p = cmd("remove-tag", lambda a, c: c.mcp_call("tag", {"action": "remove", "label": a.label}), "Remove a tag across the workspace.")
    p.add_argument("label")

    cmd("bookmarks", simple("/api/bookmark/getBookmark"), "List bookmarks.")
    cmd("bookmark-labels", lambda _a, c: c.mcp_call("bookmark", {"action": "labels"}), "List bookmark group labels.")
    p = cmd("rename-bookmark", lambda a, c: c.mcp_call("bookmark", {"action": "rename", "old": a.old, "new": a.new}), "Rename a bookmark group label.")
    p.add_argument("old")
    p.add_argument("new")
    p = cmd("remove-bookmark", lambda a, c: c.mcp_call("bookmark", {"action": "remove", "label": a.label}), "Remove a bookmark group label.")
    p.add_argument("label")

    # attributes
    p = cmd("attrs", simple("/api/attr/getBlockAttrs", lambda a, _: {"id": a.id}), "Get block attributes.")
    p.add_argument("id")
    p = cmd("batch-attrs", lambda a, c: c.mcp_call("attr", {"action": "batch-get", "ids": ",".join(a.ids)}), "Get attributes of multiple blocks in one call.")
    p.add_argument("ids", nargs="+")

    # paths and structured document addressing (SiYuan 3.8.11+)
    p = cmd("list-docs", simple("/api/filetree/listDocsByPath", lambda a, prof: {"notebook": notebook_id(prof, a.notebook), "path": a.path}), "List documents under a notebook storage path.")
    p.add_argument("--notebook", help="Notebook ID. Defaults to profile.default_notebook.")
    p.add_argument("--path", default="/", help="Storage path such as / or /<doc-id>.sy.")
    p = cmd("hpath-by-id", simple("/api/filetree/getHPathByID", lambda a, _: {"id": a.id}), "Get human-readable document path by block/doc ID.")
    p.add_argument("id")
    p = cmd("path-by-id", simple("/api/filetree/getPathByID", lambda a, _: {"id": a.id}), "Get storage path by block/doc ID.")
    p.add_argument("id")
    p = cmd("ids-by-hpath", simple("/api/filetree/getIDsByHPath", lambda a, prof: {"path": a.path, "notebook": notebook_id(prof, a.notebook)}), "Get document IDs by human-readable path.")
    p.add_argument("path")
    p.add_argument("--notebook", help="Notebook ID. Defaults to profile.default_notebook.")
    p = cmd("resolve-doc-path", cmd_resolve_doc_path, "Resolve exact document title segments without '/' ambiguity (SiYuan 3.8.11+).")
    p.add_argument("segments", nargs="*", help="Ordered title segments (literal '/' preserved in each segment).")
    p.add_argument("--notebook", help="Notebook ID. Defaults to profile.default_notebook.")
    p.add_argument("--start-id", help="Optional starting parent document ID (defaults to notebook root).")
    p = cmd("doc-paths", cmd_doc_paths, "Get structured document metadata & segment chains by IDs (SiYuan 3.8.11+).")
    p.add_argument("ids", nargs="+", help="1..128 document IDs.")
    p.add_argument("--notebook", help="Notebook ID. Defaults to profile.default_notebook.")
    p.add_argument("--include-icons", action="store_true", help="Include document and ancestor icons.")

    # documents
    p = cmd("create-doc", cmd_create_doc, "Create a document via structured --title [--parent-id] (literal '/' safe) or hPath --path.")
    p.add_argument("--notebook", help="Notebook ID. Defaults to profile.default_notebook.")
    p.add_argument("--title", help="Plain document title (uses createDocByParent; literal '/' is preserved).")
    p.add_argument("--parent-id", help="Existing parent document ID for --title mode (omit for notebook root).")
    p.add_argument("--id", type=block_id, help="Explicit new document ID for --title mode (auto-generated if omitted).")
    p.add_argument("--tags", help="Comma-separated document tags for --title mode.")
    p.add_argument("--with-math", action="store_true", help="Parse inline math in --title mode.")
    p.add_argument("--template-path", help="Template path when markdown is empty in --title mode.")
    p.add_argument("--expected-parent-revision", help="Optional parent revision guard for --title mode.")
    p.add_argument("--path", help="hPath like /Inbox/Title ('/' separates levels; missing parents are created). Bare title goes under default_doc_path.")
    add_markdown_args(p, required=False)

    p = cmd("duplicate-doc", lambda a, c: c.mcp_call("document", {"action": "duplicate", "id": a.id}), "Duplicate a document.")
    p.add_argument("id", help="Document ID to duplicate.")

    p = cmd("rename-doc", cmd_rename_doc, "Rename a document by ID or notebook/path.")
    p.add_argument("--id")
    p.add_argument("--notebook", help="Required with --path unless default_notebook is configured.")
    p.add_argument("--path", help="Storage path such as /<doc-id>.sy.")
    p.add_argument("--title", required=True)
    p = cmd("remove-doc", cmd_remove_doc, "Remove a document (and its subdocuments) by ID or notebook/path.")
    p.add_argument("--id")
    p.add_argument("--notebook", help="Required with --path unless default_notebook is configured.")
    p.add_argument("--path", help="Storage path such as /<doc-id>.sy.")
    p = cmd("move-doc", cmd_move_doc, "Move documents under another document or notebook root.")
    p.add_argument("ids", nargs="+", help="Document IDs to move.")
    p.add_argument("--to", required=True, help="Target parent document ID or notebook ID.")
    p.add_argument("--notebook", help="Target notebook ID when moving across notebooks.")
    p = cmd("daily-note", cmd_daily_note, "Create/get today's daily note, or append/prepend Markdown to it.")
    p.add_argument("--notebook", help="Notebook ID. Defaults to profile.default_notebook.")
    p.add_argument("--prepend", action="store_true", help="Prepend instead of append.")
    add_markdown_args(p, required=False)

    # blocks
    p = cmd("insert-block", cmd_insert_block, "Insert Markdown before, after, or inside an anchor block.")
    p.add_argument("--next-id", help="Insert before this block.")
    p.add_argument("--previous-id", help="Insert after this block.")
    p.add_argument("--parent-id", help="Insert as a child of this block.")
    add_markdown_args(p)
    for name, endpoint in (("append-block", "/api/block/appendBlock"), ("prepend-block", "/api/block/prependBlock")):
        p = cmd(
            name,
            simple(endpoint, lambda a, _, ep=endpoint: {"parentID": a.parent_id, "dataType": "markdown", "data": markdown_of(a)}),
            f"{'Append' if name.startswith('append') else 'Prepend'} Markdown as the {'last' if name.startswith('append') else 'first'} child of a block or document.",
        )
        p.add_argument("parent_id")
        add_markdown_args(p)
    p = cmd("update-block", cmd_update_block, "Replace ONE block with Markdown.")
    p.add_argument("id")
    p.add_argument("--lock-type", action="store_true", help="Reject the update if the new content changes the block type.")
    add_markdown_args(p)
    p = cmd("move-block", cmd_move_block, "Move a block after a sibling (--previous-id) or into a parent (--parent-id).")
    p.add_argument("id")
    p.add_argument("--previous-id")
    p.add_argument("--parent-id")
    p = cmd("delete-block", simple("/api/block/deleteBlock", lambda a, _: {"id": a.id}), "Delete a block.")
    p.add_argument("id")
    p = cmd("fold-block", simple("/api/block/foldBlock", lambda a, _: {"id": a.id}), "Fold a block.")
    p.add_argument("id")
    p = cmd("unfold-block", simple("/api/block/unfoldBlock", lambda a, _: {"id": a.id}), "Unfold a block.")
    p.add_argument("id")
    p = cmd("transfer-ref", cmd_transfer_ref, "Transfer block references from one block to another.")
    p.add_argument("from_id")
    p.add_argument("to_id")
    p.add_argument("--ref-ids", nargs="+", help="Optional subset of referencing block IDs to transfer.")
    p = cmd(
        "set-attrs",
        simple("/api/attr/setBlockAttrs", lambda a, _: {"id": a.id, "attrs": parse_json_arg(a.attrs, a.attrs_file, "attrs")}),
        "Set block attributes (custom ones need the custom- prefix; a null value removes the attribute).",
    )
    p.add_argument("id")
    p.add_argument("--attrs", help="JSON object of attributes.")
    p.add_argument("--attrs-file", help="Read attributes JSON object from file.")

    # assets, export & import
    p = cmd("upload-asset", cmd_upload_asset, "Upload local files to SiYuan assets over HTTP.")
    p.add_argument("files", nargs="+", help="Local file paths to upload.")
    p.add_argument("--assets-dir", default="/assets/", help="Target assets directory path (default: /assets/).")
    cmd("unused-assets", lambda _a, c: c.mcp_call("asset", {"action": "unused"}), "List unreferenced workspace assets.")
    p = cmd("clean-assets", lambda a, c: c.mcp_call("asset", {"action": "clean", "path": a.path}), "Remove unused workspace asset(s).")
    p.add_argument("--path", help="Optional single unused asset path; omit to clean all unused assets.")
    p = cmd("asset-stat", lambda a, c: c.mcp_call("asset", {"action": "stat", "path": a.path}), "Get metadata of a workspace asset.")
    p.add_argument("path", help="Asset path such as assets/image.png.")

    p = cmd("export", cmd_export, "Export a document to md, html, preview, docx, sy (.sy.zip), or md-zip.")
    p.add_argument("id", help="Document ID.")
    p.add_argument("--format", choices=EXPORT_FORMATS, default="md", help="Export format (default: md).")
    p.add_argument("--output", help="Output directory on the SiYuan host (required for docx).")
    p = cmd("export-data", cmd_export_data, "Export full SiYuan workspace data archive.")
    p.add_argument("--output", help="Optional output directory on the SiYuan host.")

    p = cmd("import", cmd_import, "Import Markdown, .sy.zip, or data archive from a path accessible to the SiYuan host.")
    p.add_argument("path", help="Source file/directory path on the SiYuan host.")
    p.add_argument("--type", choices=IMPORT_TYPES, default="md", help="Import type: md (default), sy (.sy.zip), or data.")
    p.add_argument("--notebook", help="Target notebook ID (required for md/sy unless default_notebook is set).")
    p.add_argument("--target-path", help="Optional target parent path inside the notebook.")

    # database (Attribute View)
    p = cmd("db", cmd_db, "Operate SiYuan Attribute Views (databases) via official MCP actions.")
    p.add_argument("action", help="Action such as search, get, render, create, keys, key-add, item-add, item-update, view-get (run `mcp-tools database` for full schema).")
    p.add_argument("--id", help="Attribute view ID (avID).")
    p.add_argument("--block-id", help="Database block ID or bound block ID.")
    p.add_argument("--view-id", help="Database view ID.")
    p.add_argument("--keyword", help="Keyword for search.")
    p.add_argument("--query", help="Query filter for render.")
    p.add_argument("--parent-id", help="Parent block/document ID for create.")
    p.add_argument("--previous-id", help="Previous sibling block ID for create.")
    p.add_argument("--next-id", help="Next sibling block ID for create.")
    p.add_argument("--name", help="Database, column, or view name.")
    p.add_argument("--primary-key-name", help="Primary key column name for create.")
    p.add_argument("--layout", help="View layout (table, board, gallery, calendar).")
    p.add_argument("--key-id", help="Column key ID.")
    p.add_argument("--type", help="Column type (text, number, date, select, mSelect, url, checkbox, relation, rollup, ...).")
    p.add_argument("--item-id", help="Row item ID.")
    p.add_argument("--value", help="Cell value JSON object for item-update.")
    p.add_argument("--notebook", help="Notebook ID when required for encrypted notebooks.")
    p.add_argument("--page", type=int, help="Page number for render.")
    p.add_argument("--page-size", type=int, help="Page size for render.")
    p.add_argument("--revision", help="View revision for view mutations.")
    p.add_argument("--args", help="Additional JSON object merged into database arguments.")
    p.add_argument("--args-file", help="Read additional JSON arguments from file.")

    # templates, history, repo, sync, inbox
    p = cmd("template", cmd_template, "Manage or render document templates.")
    p.add_argument("action", choices=["search", "get", "remove", "render", "save-as", "save_as", "create"])
    p.add_argument("--keyword", help="Keyword for search.")
    p.add_argument("--path", help="Template path for get/remove/render.")
    p.add_argument("--id", help="Target document/block ID for render or save-as.")
    p.add_argument("--name", help="Template name for create or save-as.")
    p.add_argument("--content", help="Template Markdown content for create.")
    p.add_argument("--content-file", help="Read template Markdown content from file.")
    p.add_argument("--overwrite", action="store_true", help="Overwrite existing template on create/save-as.")

    p = cmd("render-sprig", simple("/api/template/renderSprig", lambda a, _: {"template": a.template}), "Render a Go Sprig template expression.")
    p.add_argument("template", help="Sprig template string, e.g. '{{now | date \"2006-01-02\"}}'.")

    p = cmd("history", cmd_history, "Search, inspect, or roll back automatic document history.")
    p.add_argument("action", choices=["list", "search", "get", "rollback", "clear"])
    p.add_argument("--query", help="Search query.")
    p.add_argument("--notebook", help="Notebook ID filter.")
    p.add_argument("--op", help="History operation filter (e.g. update, delete, format).")
    p.add_argument("--type", type=int, help="History type code.")
    p.add_argument("--page", type=int, help="Page number.")
    p.add_argument("--path", help="History entry path for get/rollback.")

    p = cmd("repo", cmd_repo, "Manage SiYuan data repository snapshots.")
    p.add_argument("action", choices=["list", "create", "tag", "untag", "checkout", "diff", "search", "purge", "file-get", "file-rollback", "file-open", "file-export"])
    p.add_argument("--id", help="Snapshot ID.")
    p.add_argument("--name", help="Tag name.")
    p.add_argument("--memo", help="Snapshot memo for create.")
    p.add_argument("--left", help="Left snapshot ID for diff.")
    p.add_argument("--right", help="Right snapshot ID for diff.")
    p.add_argument("--keyword", help="Keyword for search.")
    p.add_argument("--page", type=int, help="Page number.")
    p.add_argument("--only-tagged", action="store_true", help="Only list tagged snapshots.")

    p = cmd("sync", lambda a, c: c.mcp_call("sync", {"action": a.action}), "Check sync status or perform cloud/S3/WebDAV/local sync.")
    p.add_argument("action", nargs="?", choices=["status", "perform", "upload", "download"], default="status")

    p = cmd("inbox", cmd_inbox, "List, read, or convert SiYuan cloud inbox entries.")
    p.add_argument("action", choices=["list", "get", "convert"])
    p.add_argument("--id", help="Inbox item ID for get.")
    p.add_argument("--ids", nargs="+", help="Inbox item IDs for convert.")
    p.add_argument("--notebook", help="Target notebook ID for convert.")
    p.add_argument("--parent-id", help="Optional target parent document ID for convert.")
    p.add_argument("--page", type=int, help="Page number for list.")
    p.add_argument("--keep", action="store_true", help="Keep inbox item after convert (default removes after convert).")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    data_dir = user_data_dir()

    if not args.needs_config:
        if args.command == "init-config":
            eprint("[profile: none]")
            json_out(init_config(args.overwrite))
            return 0
        if args.command == "update-docs":
            eprint("[profile: none]")
            json_out(update_docs(args.references_dir, args.timeout))
            return 0
        if args.command == "check-update":
            eprint("[profile: none]")
            disabled = is_update_disabled(
                no_update_check=args.no_update_check,
                config_disabled=read_disable_update_check(args.config),
            )
            res = check_update(data_dir, disabled=disabled, force=True)
            json_out(res)
            return 0
        if args.command == "doctor":
            eprint("[profile: none]")
            report = cmd_doctor(args)
            json_out(report)
            disabled = is_update_disabled(
                no_update_check=args.no_update_check,
                config_disabled=read_disable_update_check(args.config),
            )
            check_update(data_dir, disabled=disabled)
            return 0 if report.get("ok") else 1

    _config_path, profile_name, profile = load_config(args.config, args.profile)
    eprint(f"[profile: {profile_name}]")
    disabled = is_update_disabled(
        no_update_check=args.no_update_check,
        config_disabled=bool(profile.get("_disable_update_check")),
    )
    try:
        out = args.handler(args, SiYuanClient(profile))
    except SystemExit as exc:
        check_update(data_dir, disabled=disabled)
        raise exc
    json_out(out)
    check_update(data_dir, disabled=disabled)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
