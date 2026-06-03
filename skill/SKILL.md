---
name: siyuan-note-cli
description: Operate SiYuan Note / 思源笔记 through a local CLI backed by the official HTTP API. Use when the user asks to search, read, create, append, update, delete, organize, export, or inspect SiYuan notebooks, documents, blocks, attributes, or SQL query results; when they mention 思源笔记, SiYuan, block IDs, notebook IDs, or the local SiYuan API; or when an agent needs durable note capture into SiYuan.
---

# SiYuan Note CLI

Use `siyuan-note-cli` instead of ad hoc curl calls. It handles config discovery, profile selection, token auth, JSON output, and common API error reporting.

Official source of truth:

- API docs: `https://github.com/siyuan-note/siyuan/blob/master/API.md`
- 中文 API docs: `https://github.com/siyuan-note/siyuan/blob/master/API_zh_CN.md`
- All API routes: `https://github.com/siyuan-note/siyuan/blob/master/kernel/api/router.go`

## Setup

Install the CLI if it is unavailable:

```bash
pipx install git+https://github.com/briqt/siyuan-note-cli.git
```

Initialize config:

```bash
siyuan-note-cli init-config
open ~/.config/agent-skills/siyuan-note-cli/config.json
```

Set `profiles.default.token` from SiYuan `Settings > About`. Set `base_url` to the current SiYuan API URL if it is not `http://127.0.0.1:6806`.

The CLI prints `[profile: <name>]` to stderr on every run and JSON to stdout. Use `--profile <name>` for alternate SiYuan instances.

## Quick Commands

```bash
siyuan-note-cli api-docs --query "/api/block/appendBlock"
siyuan-note-cli api-docs --lang en --query "Append blocks"
siyuan-note-cli notebooks
siyuan-note-cli list-docs --notebook <notebook-id> --path /
siyuan-note-cli search "关键词" --page-size 10
siyuan-note-cli sql "SELECT id, content, hpath FROM blocks WHERE content LIKE '%关键词%' LIMIT 20"
siyuan-note-cli get-block <block-id>
siyuan-note-cli export-md <doc-id>
siyuan-note-cli children <block-id>
siyuan-note-cli create-doc --notebook <notebook-id> --path /Inbox/Title --markdown-file note.md
siyuan-note-cli insert-block --parent-id <parent-id> --markdown-file note.md
siyuan-note-cli append-block <parent-id> --markdown "New paragraph"
siyuan-note-cli update-block <block-id> --markdown-file replacement.md
siyuan-note-cli delete-block <block-id>
```

Use `siyuan-note-cli api <endpoint> --data '{...}'` for official endpoints not yet wrapped by a dedicated command. Before using a new endpoint, run `siyuan-note-cli api-docs --query "<endpoint>"` to read the latest official `API.md`.

## Workflow

1. For lookup, start with `search` or `sql`, then read the selected block with `get-block`.
2. For whole-document reading, prefer `export-md <doc-id>`; for block-level reading, use `get-block` and `children`.
3. For writes, resolve the destination notebook/document/block first. If a default notebook is configured, it may be used for document commands; otherwise pass `--notebook`.
4. For long Markdown content, write a temporary file in the current workspace and pass `--markdown-file`.
5. Before replacing or deleting content, read the target block or export the target document and make sure it is unique.
6. In the final answer, describe the note title/path or action result in human terms; include IDs only when useful for later edits.

## References

Read `references/api-workflows.md` when a task needs endpoint details, raw API fallback examples, or safe write sequencing.
