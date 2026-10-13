from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path
from typing import Any, Callable

from . import __version__
from .client import SiYuanClient, eprint, fail, init_config, json_out, load_config
from .docs import update_docs

BLOCK_ID_RE = re.compile(r"^\d{14}-[0-9a-z]{7}$")
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
SNIPPET_CHARS = 300

# Raw `api` calls to these endpoints get a stderr hint pointing at the dedicated command.
ENDPOINT_TO_COMMAND = {
    "/api/notebook/createNotebook": "create-notebook <name>",
    "/api/notebook/renameNotebook": "rename-notebook <notebook-id> <name>",
    "/api/notebook/removeNotebook": "remove-notebook <notebook-id>",
    "/api/notebook/getNotebookConf": "notebook-conf <notebook-id>",
    "/api/filetree/createDocWithMd": "create-doc --notebook <nb> --path <path> --markdown '...'",
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
    "/api/block/getBlockKramdown": "get-block <block-id>",
    "/api/block/getBlockKramdowns": "get-blocks <block-id>...",
    "/api/block/getBlockInfo": "block-info <block-id>",
    "/api/block/getDocInfo": "doc-info <doc-id>",
    "/api/block/getBlockBreadcrumb": "breadcrumb <block-id>",
    "/api/block/getRecentUpdatedBlocks": "recent",
    "/api/attr/setBlockAttrs": "set-attrs <block-id> --attrs '{...}'",
    "/api/attr/getBlockAttrs": "attrs <block-id>",
    "/api/search/fullTextSearchBlock": "search <query>",
    "/api/query/sql": "sql '<SELECT ...>'",
    "/api/ref/getBacklink2": "backlinks <block-id>",
    "/api/tag/getTag": "tags",
    "/api/bookmark/getBookmark": "bookmarks",
}


# --- argument helpers -------------------------------------------------------


def read_text_arg(value: str | None, file_value: str | None, field: str) -> str:
    if value is not None and file_value is not None:
        fail({"error": f"pass either --{field} or --{field}-file, not both"})
    if file_value is not None:
        return Path(file_value).expanduser().read_text(encoding="utf-8")
    if value is not None:
        return value
    fail({"error": f"missing --{field} or --{field}-file"})


def parse_json_arg(raw: str | None, file_path: str | None, flag: str = "data") -> dict[str, Any]:
    if raw and file_path:
        fail({"error": f"pass either --{flag} or --{flag}-file, not both"})
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


def block_id(value: str) -> str:
    """argparse type for IDs that may be interpolated into SQL."""
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


def markdown_of(args: argparse.Namespace) -> str:
    return read_text_arg(args.markdown, args.markdown_file, "markdown")


# --- command handlers -------------------------------------------------------
# Each handler takes (args, client) and returns the JSON value printed to stdout.

Handler = Callable[[argparse.Namespace, SiYuanClient], Any]


def simple(endpoint: str, build: Callable[[argparse.Namespace, dict[str, Any]], dict[str, Any]] | None = None) -> Handler:
    def handler(args: argparse.Namespace, client: SiYuanClient) -> Any:
        return client.post(endpoint, build(args, client.profile) if build else {})

    return handler


def cmd_api(args, client):
    endpoint = args.endpoint if args.endpoint.startswith("/") else f"/{args.endpoint}"
    if endpoint in ENDPOINT_TO_COMMAND:
        eprint(f"[hint] This endpoint has a dedicated command: siyuan-cli {ENDPOINT_TO_COMMAND[endpoint]}")
    return client.post(endpoint, parse_json_arg(args.data, args.data_file))


def cmd_search(args, client):
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


def cmd_sql(args, client):
    response = client.post("/api/query/sql", {"stmt": args.statement})
    if isinstance(response, dict) and response.get("truncated"):
        eprint(
            f"[warn] Result truncated at the server default limit ({response.get('limit')} rows = Settings > Search > result count). "
            "Add an explicit LIMIT/OFFSET with a stable ORDER BY (e.g. ORDER BY hpath, id); use SELECT COUNT(*) for totals."
        )
    return response


def cmd_search_docs(args, client):
    response = client.post("/api/filetree/searchDocs", {"k": args.keyword})
    docs = [
        {"id": Path(d.get("path", "")).stem or None, "box": d.get("box"), "hPath": d.get("hPath"), "path": d.get("path")}
        for d in response.get("data") or []
    ]
    return with_data(response, docs)


def cmd_backlinks(args, client):
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


def cmd_recent(args, client):
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


def cmd_tags(args, client):
    if args.keyword:
        return client.post("/api/search/searchTag", {"k": args.keyword})
    return client.post("/api/tag/getTag", {"ignoreMaxListHint": True})


def cmd_create_doc(args, client):
    payload = {
        "notebook": notebook_id(client.profile, args.notebook),
        "path": resolve_doc_path(client.profile, args.path),
        "markdown": markdown_of(args),
    }
    return client.post("/api/filetree/createDocWithMd", payload)


def cmd_rename_doc(args, client):
    if args.id:
        return client.post("/api/filetree/renameDocByID", {"id": args.id, "title": args.title})
    if not args.path:
        fail({"error": "rename-doc requires --id or --path"})
    return client.post("/api/filetree/renameDoc", {"notebook": notebook_id(client.profile, args.notebook), "path": args.path, "title": args.title})


def cmd_remove_doc(args, client):
    if args.id:
        return client.post("/api/filetree/removeDocByID", {"id": args.id})
    if not args.path:
        fail({"error": "remove-doc requires --id or --path", "examples": [
            "siyuan-cli remove-doc --id <doc-id>",
            "siyuan-cli remove-doc --notebook <nb-id> --path /path/to/doc.sy",
        ]})
    return client.post("/api/filetree/removeDoc", {"notebook": notebook_id(client.profile, args.notebook), "path": args.path})


def cmd_daily_note(args, client):
    notebook = notebook_id(client.profile, args.notebook)
    if args.markdown is None and args.markdown_file is None:
        if args.prepend:
            fail({"error": "--prepend needs --markdown or --markdown-file"})
        return client.post("/api/filetree/createDailyNote", {"notebook": notebook})
    endpoint = "/api/block/prependDailyNoteBlock" if args.prepend else "/api/block/appendDailyNoteBlock"
    return client.post(endpoint, {"notebook": notebook, "dataType": "markdown", "data": markdown_of(args)})


def cmd_insert_block(args, client):
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


def cmd_update_block(args, client):
    payload = {"id": args.id, "dataType": "markdown", "data": markdown_of(args)}
    if args.lock_type:
        payload["lockType"] = True
    return client.post("/api/block/updateBlock", payload)


def cmd_move_block(args, client):
    if not (args.previous_id or args.parent_id):
        fail({"error": "missing move anchor", "hint": "Pass --previous-id (move after it) or --parent-id (move to first child)."})
    payload: dict[str, Any] = {"id": args.id}
    if args.previous_id:
        payload["previousID"] = args.previous_id
    if args.parent_id:
        payload["parentID"] = args.parent_id
    return client.post("/api/block/moveBlock", payload)


def cmd_upload_asset(args, client):
    return client.upload_assets(args.files, args.assets_dir)


# --- parser -----------------------------------------------------------------


def add_markdown_args(parser: argparse.ArgumentParser, required: bool = True) -> None:
    group = parser.add_mutually_exclusive_group(required=required)
    group.add_argument("--markdown", help="Markdown content.")
    group.add_argument("--markdown-file", help="Read Markdown content from a UTF-8 file (preferred for long content).")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="siyuan-cli", description="Operate SiYuan notes through the local HTTP API.")
    parser.add_argument(
        "-V", "--version", action="version", version=f"siyuan-cli {__version__}",
        help="Show the siyuan-cli version and exit (for the connected server's version, use the `version` command).",
    )
    parser.add_argument("--profile", help="Profile name from config.json.")
    parser.add_argument("--config", help="Explicit config.json path.")
    sub = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    def cmd(name: str, handler: Handler | None, help: str, needs_config: bool = True) -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=help, description=help)
        p.set_defaults(handler=handler, needs_config=needs_config)
        return p

    # maintenance
    p = cmd("init-config", None, "Create the user config file.", needs_config=False)
    p.add_argument("--overwrite", action="store_true")
    p = cmd("update-docs", None, "Refresh vendored official SiYuan API references.", needs_config=False)
    p.add_argument("--references-dir", help="Path to the skill references directory. Defaults to ./skill/references.")
    p.add_argument("--timeout", type=int, default=30)

    # system
    cmd("version", simple("/api/system/version"), "Get the connected SiYuan server's version (for the CLI version use -V/--version).")
    cmd("server-version", simple("/api/system/version"), "Alias of `version`: the connected SiYuan server's version.")
    cmd("current-time", simple("/api/system/currentTime"), "Get SiYuan system time.")

    p = cmd("api", cmd_api, "Call any SiYuan API endpoint (only when no dedicated command exists).")
    p.add_argument("endpoint", help="Endpoint such as /api/notebook/lsNotebooks.")
    p.add_argument("--data", help="JSON object payload.")
    p.add_argument("--data-file", help="Read JSON object payload from file.")

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
        p = cmd(name, simple(endpoint, lambda a, _: {"notebook": a.notebook}), f"{name.replace('-', ' ').capitalize()}.")
        p.add_argument("notebook", help="Notebook ID.")

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

    p = cmd("sql", cmd_sql, "Execute a read-only SQL query (warns on stderr when the server truncated the result).")
    p.add_argument("statement")

    p = cmd("search-docs", cmd_search_docs, "Find documents by title/path keyword.")
    p.add_argument("keyword")

    p = cmd("get-block", simple("/api/block/getBlockKramdown", lambda a, _: {"id": a.id}), "Read a block as Kramdown.")
    p.add_argument("id")
    p = cmd("get-blocks", simple("/api/block/getBlockKramdowns", lambda a, _: {"ids": a.ids}), "Read several blocks as Kramdown in one call.")
    p.add_argument("ids", nargs="+")
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
    p = cmd("tags", cmd_tags, "List the tag tree, or search tags by keyword.")
    p.add_argument("keyword", nargs="?")
    cmd("bookmarks", simple("/api/bookmark/getBookmark"), "List bookmarks.")
    p = cmd("attrs", simple("/api/attr/getBlockAttrs", lambda a, _: {"id": a.id}), "Get block attributes.")
    p.add_argument("id")

    # paths and IDs
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

    # documents
    p = cmd("create-doc", cmd_create_doc, "Create a document with Markdown. Missing parent documents are created.")
    p.add_argument("--notebook", help="Notebook ID. Defaults to profile.default_notebook.")
    p.add_argument("--path", required=True, help="hPath like /Inbox/Title ('/' always separates levels). A bare title goes under default_doc_path.")
    add_markdown_args(p)
    p = cmd("rename-doc", cmd_rename_doc, "Rename a document by ID or notebook/path.")
    p.add_argument("--id")
    p.add_argument("--notebook", help="Required with --path unless default_notebook is configured.")
    p.add_argument("--path", help="Storage path such as /<doc-id>.sy.")
    p.add_argument("--title", required=True)
    p = cmd("remove-doc", cmd_remove_doc, "Remove a document (and its subdocuments) by ID or notebook/path.")
    p.add_argument("--id")
    p.add_argument("--notebook", help="Required with --path unless default_notebook is configured.")
    p.add_argument("--path", help="Storage path such as /<doc-id>.sy.")
    p = cmd("move-doc", simple("/api/filetree/moveDocsByID", lambda a, _: {"fromIDs": a.ids, "toID": a.to}), "Move documents under another document or to a notebook root.")
    p.add_argument("ids", nargs="+", help="Document IDs to move.")
    p.add_argument("--to", required=True, help="Target parent document ID or notebook ID.")
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
        p = cmd(name, simple(endpoint, lambda a, _: {"parentID": a.parent_id, "dataType": "markdown", "data": markdown_of(a)}),
                f"{'Append' if name.startswith('append') else 'Prepend'} Markdown as the {'last' if name.startswith('append') else 'first'} child of a block or document.")
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
    p = cmd("set-attrs", simple("/api/attr/setBlockAttrs", lambda a, _: {"id": a.id, "attrs": parse_json_arg(a.attrs, a.attrs_file, "attrs")}),
            "Set block attributes (custom ones need the custom- prefix; a null value removes the attribute).")
    p.add_argument("id")
    p.add_argument("--attrs", help="JSON object of attributes.")
    p.add_argument("--attrs-file", help="Read attributes JSON object from file.")

    # assets
    p = cmd("upload-asset", cmd_upload_asset, "Upload files to SiYuan assets.")
    p.add_argument("files", nargs="+", help="File paths to upload.")
    p.add_argument("--assets-dir", default="/assets/", help="Target assets directory path (default: /assets/).")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if not args.needs_config:
        eprint("[profile: none]")
        if args.command == "init-config":
            json_out(init_config(args.overwrite))
        else:
            json_out(update_docs(args.references_dir, args.timeout))
        return 0

    _config_path, profile_name, profile = load_config(args.config, args.profile)
    eprint(f"[profile: {profile_name}]")
    json_out(args.handler(args, SiYuanClient(profile)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
