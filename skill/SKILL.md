---
name: siyuan-cli
description: Operate SiYuan Note / 思源笔记 through the local `siyuan-cli` CLI backed by the official HTTP API and built-in MCP tools. Use when the user wants to search (keyword, regex, SQL, semantic, or attachment content), read, export, import, create, duplicate, append, update, move, rename, or delete SiYuan notebooks, documents, blocks, databases (Attribute Views), tags, bookmarks, templates, history, snapshots, inbox items, or assets, or trigger sync. Also use when they mention 思源笔记, SiYuan, block IDs (like 20240101120000-abc1234), notebook IDs, or a SiYuan API endpoint on port 6806.
metadata:
  version: "0.4.0"
---

# SiYuan CLI

Use `siyuan-cli` instead of ad hoc `curl` calls or mounting SiYuan's raw MCP server into agent context (~20k tokens of schema). `siyuan-cli` wraps both SiYuan's official `/api/*` endpoints and built-in `/mcp` tools behind a zero-dependency CLI with compact JSON output, strict validation, and zero idle context overhead.

Every command prints JSON (`{"code": 0, "msg": "", "data": ...}` for SiYuan operations) to `stdout`. `stderr` carries `[profile: <name>]`, `[warn]` (e.g. truncated SQL), `[hint]`, and optional update notices. Errors go to `stderr` as JSON with a non-zero exit code.

**IDs at a glance**: every block, document, and notebook has an ID like `20240101120000-abc1234`. A document is itself a block, so a doc ID works wherever a block ID is expected. In results, `rootID`/`root_id` is the containing document's ID and `box` is the notebook ID.

## Setup & Diagnostics

Install or upgrade the CLI and companion skill:

```bash
pipx install git+https://github.com/briqt/siyuan-cli.git
# upgrade an existing CLI install:
pipx install --force git+https://github.com/briqt/siyuan-cli.git
# install or sync companion skill:
npx skills add briqt/siyuan-cli -g -y
```

Initialize and inspect configuration (`~/.config/agent-skills/siyuan-cli/config.json`):

```bash
siyuan-cli init-config
siyuan-cli doctor        # verify CLI/Skill versions, config, server version & /mcp availability
siyuan-cli check-update  # check GitHub release & notice feed
```

Set `profiles.default.token` from SiYuan `设置 - 鉴权 - API token` (Settings > Auth > API token), and `base_url` if SiYuan is not at `http://127.0.0.1:6806`. Optionally set `default_notebook` and `default_doc_path`. Use `--profile <name>` for alternate instances; `siyuan-cli -V` prints the CLI version and `siyuan-cli version` queries the connected SiYuan server version.

Troubleshooting:

| `stderr` error | Fix |
|---|---|
| `config not found` / `token is not configured` | Run `siyuan-cli init-config`, ask the user for the API token, and write it to `~/.config/agent-skills/siyuan-cli/config.json` |
| `http error` 401/403 | Token is wrong or regenerated; ask the user for the current token |
| `http error` 404 on `/mcp` | Built-in `/mcp` tools require SiYuan ≥ 3.7.0 (tested on 3.8.11+) |
| `network error` | Check SiYuan is running, `base_url` is reachable, and `no_proxy` covers the host/CIDR |
| `unrecognized arguments` / `invalid choice` | Run `siyuan-cli <command> --help` |

## Quick Commands

Prefer dedicated commands. Run `siyuan-cli <command> --help` for full flags.

**Find & Search:**

```bash
siyuan-cli notebooks
siyuan-cli search "关键词" --page-size 10                      # compact results; --raw for full response
siyuan-cli search "关键词" --types heading paragraph --notebook <nb-id> --order-by updated-desc
siyuan-cli search "a b" --method query                         # also: regex, sql
siyuan-cli semantic-search "概念描述" --notebook <nb-id>        # requires AI embedding configured in SiYuan
siyuan-cli search-assets "合同条款" --ext .pdf                  # search inside PDF/Office/txt attachments
siyuan-cli asset-content assets/spec.pdf                       # full indexed text of an attachment
siyuan-cli search-docs "标题关键词"                              # documents by title/path
siyuan-cli sql-schema                                          # table definitions, block type codes & SQL guide
siyuan-cli sql "SELECT id, content, hpath FROM blocks WHERE content LIKE '%关键词%' ORDER BY hpath, id LIMIT 50"
siyuan-cli recent --limit 20
siyuan-cli backlinks <block-or-doc-id>                         # --blocks for referencing blocks, --mentions for unlinked
```

> **SQL row limit**: without an explicit outer `LIMIT`, `/api/query/sql` silently caps results at `search.limit` (~64 by default). The CLI prints `[warn] Result truncated` on `stderr` when it happens. Always paginate with `ORDER BY hpath, id LIMIT/OFFSET`, and use `SELECT COUNT(*)` for totals.

**Read & Navigate:**

```bash
siyuan-cli export-md <doc-id>                 # whole document as Markdown
siyuan-cli get-block <block-id>               # one block as Kramdown (with IALs/IDs)
siyuan-cli get-blocks <id1> <id2> ...         # multiple blocks in one call
siyuan-cli children <block-id>
siyuan-cli doc-outline <doc-id>
siyuan-cli doc-info <doc-id>                  # title, attrs, ref count, subdoc count
siyuan-cli tree-stat <doc-id>                 # subtree block/word counts
siyuan-cli block-info <block-id>
siyuan-cli breadcrumb <block-id>
siyuan-cli attrs <block-id>                   # batch-attrs <id1> <id2> ... for several blocks
siyuan-cli list-docs --notebook <nb-id> --path /
siyuan-cli resolve-doc-path "Notes" "C/C++" --notebook <nb-id>   # exact segment resolution (literal '/' safe)
siyuan-cli doc-paths <doc-id>... --notebook <nb-id>              # structured ancestor segments & metadata
siyuan-cli hpath-by-id <block-or-doc-id>
siyuan-cli ids-by-hpath /path/to/doc --notebook <nb-id>
```

**Create Documents & Blocks:**

```bash
siyuan-cli create-notebook "Name"
# Preferred structured creation (SiYuan 3.8.11+): preserves literal '/' in title (e.g. "C/C++")
siyuan-cli create-doc --notebook <nb-id> --title "C/C++ Notes" --parent-id <parent-doc-id> --markdown-file note.md
# hPath creation: '/' separates hierarchy levels and auto-creates missing parent docs
siyuan-cli create-doc --notebook <nb-id> --path /Inbox/Title --markdown-file note.md
siyuan-cli duplicate-doc <doc-id>
siyuan-cli daily-note --notebook <nb-id> --markdown "- captured item"   # --prepend to put first; omit markdown to just get/create
siyuan-cli append-block <parent-id> --markdown "New paragraph"
siyuan-cli prepend-block <parent-id> --markdown-file prepend.md
siyuan-cli insert-block --previous-id <block-id> --markdown "Inserted after"
```

**Update, Move & Delete:**

```bash
siyuan-cli update-block <block-id> --markdown-file replacement.md [--lock-type]   # replaces ONE block
siyuan-cli move-block <block-id> --previous-id <sibling-id>    # or --parent-id <parent-id>
siyuan-cli move-doc <doc-id>... --to <parent-doc-or-notebook-id> [--notebook <target-nb-id>]
siyuan-cli rename-doc --id <doc-id> --title "New title"
siyuan-cli rename-notebook <nb-id> "New Name"
siyuan-cli set-attrs <block-id> --attrs '{"custom-status":"done"}'   # custom attrs need custom- prefix; null removes
siyuan-cli fold-block <block-id>                               # unfold-block to expand
siyuan-cli transfer-ref <from-id> <to-id>
siyuan-cli delete-block <block-id>
siyuan-cli remove-doc --id <doc-id>                            # also removes subdocuments; confirm first
siyuan-cli remove-notebook <nb-id>                             # removes whole notebook; confirm first
```

`update-block` replaces **one** block wholesale. Read with `get-block` first to preserve needed content/IALs; to both edit a block and add new blocks, `update-block` then `insert-block --previous-id`. Block references use `((block-id "anchor text"))`, never `[[block-id]]`.

**Databases (Attribute Views), Tags & Bookmarks:**

```bash
siyuan-cli db search --keyword "项目"
siyuan-cli db get --id <av-id>
siyuan-cli db render --id <av-id> --page 1 --page-size 50
siyuan-cli db create --parent-id <doc-id> --name "Tasks" --layout table
siyuan-cli db keys --id <av-id>
siyuan-cli db item-update --id <av-id> --item-id <item-id> --key-id <key-id> --value '{"text":{"content":"Done"}}'
siyuan-cli tags [keyword]                     # rename-tag <old> <new> | remove-tag <label>
siyuan-cli bookmarks                          # bookmark-labels | rename-bookmark <old> <new> | remove-bookmark <label>
```

**Assets, Export, Import, Templates, History & Sync:**

```bash
siyuan-cli upload-asset /local/path/image.png --assets-dir /assets/   # HTTP upload; works with remote base_url too
siyuan-cli unused-assets                      # clean-assets [--path assets/x.png] | asset-stat assets/x.png
siyuan-cli export <doc-id> --format docx --output /dir/on/siyuan/host # formats: md, html, preview, docx, sy, md-zip
siyuan-cli import /path/on/siyuan/host/note.md --type md --notebook <nb-id>
siyuan-cli template search --keyword "日报"   # also: get, render, create, save-as, remove; render-sprig '<expr>'
siyuan-cli history list --notebook <nb-id>    # also: search, get --path <p>, rollback --path <p>
siyuan-cli repo list                          # data snapshots: create --memo "...", tag, diff, search
siyuan-cli sync [status|perform|upload|download]
siyuan-cli inbox list                         # also: get --id <id>, convert --ids <id>... --notebook <nb-id>
```

> **Local vs remote `base_url` paths**: `upload-asset`, `export-md`, and `--markdown-file` read/return data on the **CLI machine** and work identically over remote LAN/Tailscale URLs. File-path arguments in `import` and `export --output` are resolved on the **SiYuan server host**.

**Native Escape Hatches (100% Official Ceiling):**

```bash
siyuan-cli mcp-tools [tool]                   # list all built-in /mcp tools, or inspect one tool's full schema
siyuan-cli mcp <tool> [action] --args '{...}' # call any built-in /mcp tool (e.g. pdf, image, bazaar)
siyuan-cli api /api/... --data '{...}'        # call any /api/* endpoint without a dedicated command
```

## Workflow

1. Prefer dedicated commands; use `mcp-tools` + `mcp` or `api` only when no dedicated command exists.
2. Locate targets with `search`, `search-docs`, `resolve-doc-path`, or `sql`, then read full content via `get-block` / `get-blocks` or `export-md`.
3. For document titles containing `/` (such as `C/C++` or `2026/11`), always use `create-doc --title ... [--parent-id ...]`; reserve `--path` for slash-delimited hierarchy paths.
4. For long Markdown content, write a temporary UTF-8 file and pass `--markdown-file`.
5. Before replacing, moving, or deleting content, read the target first and verify its identity; confirm with the user before destructive document/notebook/tag/history removals.
6. A `code: 0` response means the write was accepted; search/SQL indexes can lag briefly—read by ID when verifying immediate writes.

## References

- [references/api-workflows.md](references/api-workflows.md) — `/api/*` vs `/mcp` architecture, structured document addressing, database mutations, raw endpoint examples, and refreshing vendored official docs (`siyuan-cli update-docs`).
- `references/official/` — vendored official SiYuan docs (`API_zh_CN.md`, `API.md`, `DOCUMENT-ADDRESSING_zh_CN.md`, `DOCUMENT-HPATH.md`, `kernel-api-router.go`).
