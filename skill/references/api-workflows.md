# SiYuan API Workflows

Load this file when a task needs endpoint details, safe write sequencing, or a command that is not already obvious from `siyuan-cli --help`.

## Official Sources

The official docs are vendored locally for clarity and repeatability:

- `references/official/API_zh_CN.md` - official Chinese API docs from `siyuan-note/siyuan`
- `references/official/API.md` - official English API docs from `siyuan-note/siyuan`
- `references/official/kernel-api-router.go` - official API router source
- `references/official/manifest.json` - source URLs for the vendored files

Use `rg` on local docs before calling less common endpoints:

```bash
rg -n "/api/filetree/createDocWithMd|通过 Markdown 创建文档" references/official/API_zh_CN.md
rg -n "/api/block/appendBlock|插入后置子块" references/official/API_zh_CN.md
rg -n "appendBlock|createDocWithMd" references/official/kernel-api-router.go
```

Refresh the vendored official docs only when they are missing or stale:

```bash
siyuan-cli update-docs --references-dir <skill-root>/references
```

The source of truth is the official GitHub repo `https://github.com/siyuan-note/siyuan`. Treat `docs.siyuan-note.club` as supplementary community developer documentation unless an official source links to the exact page.

## API Basics

- Default base URL: `http://127.0.0.1:6806`
- All documented API calls use `POST`.
- Send `Content-Type: application/json`.
- Send `Authorization: Token <token>`.
- Normal JSON responses follow `{ "code": 0, "msg": "", "data": ... }`.
- Nonzero `code` means the operation failed; do not treat partial data as success.

## CLI Shape

The CLI prints machine-readable JSON to stdout and diagnostics to stderr. The first stderr line is always `[profile: <name>]`, except docs maintenance commands which print `[profile: none]`.

Use `siyuan-cli api <endpoint> --data '{...}'` for official endpoints that do not have a dedicated command yet. Check the local official docs first.

## Read/Search

```bash
siyuan-cli notebooks
siyuan-cli list-docs --notebook <id> --path /
siyuan-cli search "keyword" --page-size 10
siyuan-cli sql "SELECT id, content, hpath FROM blocks WHERE content LIKE '%keyword%' LIMIT 20"
siyuan-cli get-block 20240101010101-abcdefg
siyuan-cli export-md 20240101010101-abcdefg
siyuan-cli children 20240101010101-abcdefg
siyuan-cli attrs 20240101010101-abcdefg
```

Prefer full-text search for user-facing lookup. Use SQL when the user asks for structured filtering, time ranges, attributes, paths, or block metadata.

## Create/Update/Delete

```bash
siyuan-cli create-notebook "Research"
siyuan-cli rename-notebook <notebook-id> "Archive"
siyuan-cli create-doc --notebook <notebook-id> --path /Inbox/Title --markdown-file note.md
siyuan-cli rename-doc --id <doc-id> --title "New title"
siyuan-cli remove-doc --id <doc-id>
siyuan-cli insert-block --previous-id <block-id> --markdown "Inserted after previous block"
siyuan-cli append-block <parent-id> --markdown "New paragraph"
siyuan-cli prepend-block <parent-id> --markdown-file prepend.md
siyuan-cli update-block <block-id> --markdown-file replacement.md
siyuan-cli delete-block <block-id>
```

Before destructive writes:

1. Resolve the target to a unique block or document ID.
2. Read the existing block with `get-block` when replacing or deleting.
3. Mention the target title/path in the final answer, not just the raw ID.

## Common Raw Endpoints

```bash
siyuan-cli api /api/filetree/listDocsByPath --data '{"notebook":"<id>","path":"/"}'
siyuan-cli api /api/filetree/getHPathByID --data '{"id":"<block-id>"}'
siyuan-cli api /api/filetree/getPathByID --data '{"id":"<block-id>"}'
siyuan-cli api /api/filetree/renameDocByID --data '{"id":"<doc-id>","title":"New title"}'
siyuan-cli api /api/filetree/removeDocByID --data '{"id":"<doc-id>"}'
siyuan-cli api /api/attr/setBlockAttrs --data '{"id":"<block-id>","attrs":{"custom-key":"value"}}'
```

## Markdown Notes

Use Markdown for agent-generated note content unless the user asks for raw DOM or another representation. For long content, write a temporary file in the current workspace and pass `--markdown-file`.
