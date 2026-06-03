---
name: siyuan-cli
description: Operate SiYuan Note / 思源笔记 through a local CLI backed by the official HTTP API. Use when the user asks to search, read, create, append, update, delete, organize, export, or inspect SiYuan notebooks, documents, blocks, attributes, or SQL query results; when they mention 思源笔记, SiYuan, block IDs, notebook IDs, or the local SiYuan API; or when an agent needs durable note capture into SiYuan.
---

# SiYuan CLI

Use `siyuan-cli` instead of ad hoc curl calls. It handles config discovery, profile selection, token auth, JSON output, common API error reporting, and local maintenance of official SiYuan API references.

## Setup

Install the CLI if it is unavailable:

```bash
pipx install git+https://github.com/briqt/siyuan-cli.git
```

Initialize config:

```bash
siyuan-cli init-config
open ~/.config/agent-skills/siyuan-cli/config.json
```

Set `profiles.default.token` from SiYuan `Settings > About`. Set `base_url` to the current SiYuan API URL if it is not `http://127.0.0.1:6806`.

The CLI prints `[profile: <name>]` to stderr on every run and JSON to stdout. Use `--profile <name>` for alternate SiYuan instances.

## Official Docs

Before using an unfamiliar endpoint, read the vendored official docs under `references/official/`:

```bash
rg -n "/api/block/appendBlock|插入后置子块" references/official/API_zh_CN.md
rg -n "/api/block/appendBlock" references/official/API.md
rg -n "appendBlock" references/official/kernel-api-router.go
```

If the official docs are missing or stale, update them from the SiYuan official GitHub repo:

```bash
siyuan-cli update-docs --references-dir <skill-root>/references
```

When working from this repository root, `siyuan-cli update-docs` is enough.

## Quick Commands

```bash
siyuan-cli notebooks
siyuan-cli list-docs --notebook <notebook-id> --path /
siyuan-cli search "关键词" --page-size 10
siyuan-cli sql "SELECT id, content, hpath FROM blocks WHERE content LIKE '%关键词%' LIMIT 20"
siyuan-cli get-block <block-id>
siyuan-cli export-md <doc-id>
siyuan-cli children <block-id>
siyuan-cli create-doc --notebook <notebook-id> --path /Inbox/Title --markdown-file note.md
siyuan-cli insert-block --parent-id <parent-id> --markdown-file note.md
siyuan-cli append-block <parent-id> --markdown "New paragraph"
siyuan-cli update-block <block-id> --markdown-file replacement.md
siyuan-cli delete-block <block-id>
```

Use `siyuan-cli api <endpoint> --data '{...}'` for official endpoints not yet wrapped by a dedicated command. Check the local official docs first so the request payload matches the current API.

## Workflow

1. For lookup, start with `search` or `sql`, then read the selected block with `get-block`.
2. For whole-document reading, prefer `export-md <doc-id>`; for block-level reading, use `get-block` and `children`.
3. For writes, resolve the destination notebook/document/block first. If a default notebook is configured, it may be used for document commands; otherwise pass `--notebook`.
4. For long Markdown content, write a temporary file in the current workspace and pass `--markdown-file`.
5. Before replacing or deleting content, read the target block or export the target document and make sure it is unique.
6. In the final answer, describe the note title/path or action result in human terms; include IDs only when useful for later edits.

## References

Read `references/api-workflows.md` for safe sequencing and `references/official/` for the current vendored official API docs.
