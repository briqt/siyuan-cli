---
name: siyuan-cli
description: Operate SiYuan Note / 思源笔记 through the local `siyuan-cli` CLI backed by the official HTTP API. Use when the user wants to search, read, export, create, append, update, move, rename, or delete SiYuan notebooks, documents, or blocks; capture notes or quick thoughts into SiYuan or today's daily note (日记); find backlinks/references (反链、双链、引用), tags, bookmarks, or recently edited content; read or set block attributes; upload assets; or run SQL over the SiYuan database. Also use when they mention 思源笔记, SiYuan, block IDs (like 20240101120000-abc1234), notebook IDs, or the local SiYuan API on port 6806.
---

# SiYuan CLI

Use `siyuan-cli` instead of ad hoc curl calls. It handles config discovery, profile selection, token auth, strict API payload shapes, compact JSON output, and error reporting.

Every command prints JSON `{"code": 0, "msg": "", "data": ...}` to stdout. stderr carries `[profile: <name>]`, plus `[warn]` (e.g. truncated SQL) and `[hint]` lines worth reading. Errors go to stderr as JSON with a non-zero exit code.

**IDs at a glance**: every block, document, and notebook has an ID like `20240101120000-abc1234`. A document is itself a block, so a doc ID works wherever a block ID is expected. In results, `rootID`/`root_id` is the containing document's ID and `box` is the notebook ID.

## Setup

Install the CLI if it is unavailable:

```bash
pipx install git+https://github.com/briqt/siyuan-cli.git
# upgrade an existing install:
pipx install --force git+https://github.com/briqt/siyuan-cli.git
```

Initialize config:

```bash
siyuan-cli init-config
open ~/.config/agent-skills/siyuan-cli/config.json
```

Set `profiles.default.token` from SiYuan `设置 - 鉴权 - API token` (Settings > Auth > API token). Set `base_url` to the current SiYuan API URL if it is not `http://127.0.0.1:6806`. Optionally set `default_notebook` and `default_doc_path`.

Use `--profile <name>` for alternate SiYuan instances. `siyuan-cli version` checks connectivity (server version); `siyuan-cli -V` shows the CLI version.

Troubleshooting:

| stderr error | Fix |
|---|---|
| `config not found` / `token is not configured` | Run `siyuan-cli init-config`, then ask the user for the token and put it in the config file |
| `http error` 401/403 | Token is wrong or was regenerated; ask the user for the current one |
| `network error` | SiYuan is not running or `base_url` is unreachable; check `base_url`, and that `no_proxy` covers the host if a proxy is set |
| `Field [...] has an invalid type` | Payload shape is wrong (usually in `siyuan-cli api`); check the official docs for that endpoint |
| `unrecognized arguments` / `invalid choice` | Run `siyuan-cli <command> --help` |

## Quick Commands

Always prefer dedicated commands over `siyuan-cli api`. Use `siyuan-cli api` only for endpoints that have no dedicated command (it prints a `[hint]` when one exists).

**Find:**

```bash
siyuan-cli notebooks
siyuan-cli search "关键词" --page-size 10                      # compact results; --raw for the full response
siyuan-cli search "关键词" --types heading paragraph --notebook <notebook-id> --order-by updated-desc
siyuan-cli search "a b" --method query                         # also: regex, sql
siyuan-cli search-docs "标题关键词"                              # documents by title/path
siyuan-cli sql "SELECT id, content, hpath FROM blocks WHERE content LIKE '%关键词%' ORDER BY hpath, id LIMIT 50"
siyuan-cli recent --limit 20                                   # recently updated blocks
siyuan-cli backlinks <block-or-doc-id>                  # docs that reference it; --blocks for referencing blocks with content, --mentions for unlinked mentions
siyuan-cli tags [keyword]                              # tag tree, or matching tags
siyuan-cli bookmarks
```

> **SQL row limit**: without an explicit outer `LIMIT`, `/api/query/sql` returns at most `search.limit` rows (Settings > Search result count, ~64 by default) and silently drops the rest — this once made a 100+ subdoc tree look like 63. The CLI prints `[warn] Result truncated` on stderr when it happens. Always paginate with `LIMIT/OFFSET` plus a stable `ORDER BY hpath, id`; use `SELECT COUNT(*)` for totals.

**Read:**

```bash
siyuan-cli export-md <doc-id>                 # whole document as Markdown
siyuan-cli get-block <block-id>               # one block as Kramdown (with IALs/IDs)
siyuan-cli get-blocks <id1> <id2> ...         # several blocks in one call
siyuan-cli children <block-id>
siyuan-cli doc-outline <doc-id>
siyuan-cli doc-info <doc-id>                  # title, attrs, ref count, subdoc count
siyuan-cli block-info <block-id>              # owning document and notebook
siyuan-cli breadcrumb <block-id>              # heading/list ancestry
siyuan-cli attrs <block-id>
siyuan-cli hpath-by-id <block-or-doc-id>
siyuan-cli ids-by-hpath /path/to/doc --notebook <notebook-id>
siyuan-cli list-docs --notebook <notebook-id> --path /
```

**Create:**

```bash
siyuan-cli create-notebook "Name"
siyuan-cli create-doc --notebook <notebook-id> --path /Inbox/Title --markdown-file note.md
siyuan-cli create-doc --path "Title" --markdown "..."     # bare title -> default_doc_path in default_notebook
siyuan-cli daily-note --notebook <notebook-id>           # create/get today's note
siyuan-cli daily-note --notebook <notebook-id> --markdown "- captured item"   # append (--prepend to put first)
siyuan-cli append-block <parent-id> --markdown "New paragraph"
siyuan-cli prepend-block <parent-id> --markdown-file prepend.md
siyuan-cli insert-block --previous-id <block-id> --markdown "Inserted after"
```

`create-doc --path` is an hPath: `/` always separates levels and missing parents are created. A literal slash in a title must be the full-width `／`.

**Update / Move:**

```bash
siyuan-cli update-block <block-id> --markdown-file replacement.md [--lock-type]   # replaces ONE block
siyuan-cli move-block <block-id> --previous-id <sibling-id>    # or --parent-id <parent-id> to become first child
siyuan-cli move-doc <doc-id>... --to <parent-doc-id-or-notebook-id>
siyuan-cli rename-doc --id <doc-id> --title "New title"
siyuan-cli rename-notebook <notebook-id> "New Name"
siyuan-cli set-attrs <block-id> --attrs '{"custom-status":"done"}'   # custom attrs need the custom- prefix; null removes
siyuan-cli fold-block <block-id>                     # unfold-block to expand
```

`update-block` replaces exactly one block; to edit and also add content, update the block then `insert-block --previous-id` it. `--lock-type` rejects edits that would change the block type (e.g. paragraph → heading).

**Delete:**

```bash
siyuan-cli delete-block <block-id>
siyuan-cli remove-doc --id <doc-id>            # also removes subdocuments
siyuan-cli remove-notebook <notebook-id>       # whole notebook; confirm with the user first
```

**Assets:**

```bash
siyuan-cli upload-asset /path/to/image.png --assets-dir /assets/
```

Block references in Markdown use `((block-id "anchor text"))`, never `[[block-id]]`.

## Workflow

1. Prefer dedicated commands for all operations; `siyuan-cli api` is only for endpoints without one.
2. For lookup, start with `search`, `search-docs`, or `sql`, then read the selected block with `get-block` (or several with `get-blocks`).
3. For whole-document reading, prefer `export-md <doc-id>`; for block-level reading, use `get-block`, `children`, and `doc-outline`.
4. For writes, resolve the destination notebook/document/block first. If a default notebook is configured, it may be used for document commands; otherwise pass `--notebook`.
5. For long Markdown content, write a temporary file in the current workspace and pass `--markdown-file`.
6. Before replacing, moving, or deleting content, read the target block or export the target document and make sure it is unique.
7. A `code: 0` response means the request was accepted; it does not guarantee indexes are refreshed. If a follow-up search misses fresh content, read by ID instead.
8. In the final answer, describe the note title/path or action result in human terms; include IDs only when useful for later edits.

## Official Docs

Before using an unfamiliar endpoint, read the vendored official docs under `references/official/`:

```bash
rg -n "/api/block/appendBlock|插入后置子块" references/official/API_zh_CN.md
rg -n "/api/block/appendBlock" references/official/API.md
rg -n "appendBlock" references/official/kernel-api-router.go
```

Only endpoints with their own section in `API*.md` are public and stable; other routes in `kernel-api-router.go` are internal and may change. `DOCUMENT-HPATH.md` explains how document titles map to hPaths.

If the official docs are missing or stale, update them from the SiYuan official GitHub repo:

```bash
siyuan-cli update-docs --references-dir <skill-root>/references
```

When working from this repository root, `siyuan-cli update-docs` is enough.

## Note Organization

写入笔记时遵循以下组织原则：

**核心方向**：笔记应自包含、信息密度优先、最小约束让结构有机生长。触发组织行为的时机：文档过长需要拆分、找不到该往哪写、或用户要求整理结构时。

在思源中的具体应用：
- **自包含**：每篇文档独立可理解，标题即摘要，首段即上下文
- **最小约束**：不强制固定目录结构，按内容自然归类
- **信息密度优先**：写的人花 2 分钟，读的人省 20 分钟
- **单一权威源**：同一信息只在一处维护，其他地方用链接引用

实践：
- 新笔记优先追加到已有的主题文档，而非每条都创建新文档
- 文档过长（>200 块）时拆分为子文档
- 用思源的标签和属性替代 frontmatter 的 `type`/`tags` 角色
- 需要跨文档导航时，用引用块或嵌入块，而非维护独立索引

**完整方法论**：加载 `knowledge-project` skill 查看组织原则、生命周期管理和蒸馏流程的完整定义。若该 skill 不可用，参阅 https://raw.githubusercontent.com/briqt/knowledge-project/master/SKILL.md 。

## References

- `references/api-workflows.md` — API semantics, lookup strategy, safe write sequencing, raw endpoints without a dedicated command
- `references/official/` — vendored official API docs (see Official Docs above)
