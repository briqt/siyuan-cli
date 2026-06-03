# SiYuan API Workflows

Load this file when a task needs endpoint details, safe write sequencing, or a command that is not already obvious from `siyuan-note-cli --help`.

## API Basics

- Default base URL: `http://127.0.0.1:6806`
- All documented API calls use `POST`.
- Send `Content-Type: application/json`.
- Send `Authorization: Token <token>`.
- Normal JSON responses follow `{ "code": 0, "msg": "", "data": ... }`.
- Nonzero `code` means the operation failed; do not treat partial data as success.

## CLI Shape

The CLI prints machine-readable JSON to stdout and diagnostics to stderr. The first stderr line is always `[profile: <name>]`.

Use `siyuan-note-cli api <endpoint> --data '{...}'` for endpoints that do not have a dedicated command yet.

## Read/Search

```bash
siyuan-note-cli notebooks
siyuan-note-cli search "keyword" --page-size 10
siyuan-note-cli sql "SELECT id, content, hpath FROM blocks WHERE content LIKE '%keyword%' LIMIT 20"
siyuan-note-cli get-block 20240101010101-abcdefg
siyuan-note-cli children 20240101010101-abcdefg
siyuan-note-cli attrs 20240101010101-abcdefg
```

Prefer full-text search for user-facing lookup. Use SQL when the user asks for structured filtering, time ranges, attributes, paths, or block metadata.

## Create/Update

```bash
siyuan-note-cli create-doc --notebook <notebook-id> --path /Inbox/Title --markdown-file note.md
siyuan-note-cli append-block <parent-id> --markdown "New paragraph"
siyuan-note-cli prepend-block <parent-id> --markdown-file prepend.md
siyuan-note-cli update-block <block-id> --markdown-file replacement.md
siyuan-note-cli delete-block <block-id>
```

Before destructive writes:

1. Resolve the target to a unique block or document ID.
2. Read the existing block with `get-block` when replacing or deleting.
3. Mention the target title/path in the final answer, not just the raw ID.

## Common Raw Endpoints

```bash
siyuan-note-cli api /api/filetree/listDocsByPath --data '{"notebook":"<id>","path":"/"}'
siyuan-note-cli api /api/filetree/getHPathByID --data '{"id":"<block-id>"}'
siyuan-note-cli api /api/filetree/getPathByID --data '{"id":"<block-id>"}'
siyuan-note-cli api /api/filetree/renameDocByID --data '{"id":"<doc-id>","title":"New title"}'
siyuan-note-cli api /api/filetree/removeDocByID --data '{"id":"<doc-id>"}'
siyuan-note-cli api /api/attr/setBlockAttrs --data '{"id":"<block-id>","attrs":{"custom-key":"value"}}'
```

## Markdown Notes

Use Markdown for agent-generated note content unless the user asks for raw DOM or another representation. For long content, write a temporary file in the current workspace and pass `--markdown-file`.

