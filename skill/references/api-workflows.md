# SiYuan API Workflows

Load this file when a task needs endpoint details, safe write sequencing, or an endpoint that has no dedicated command. SKILL.md Quick Commands lists every dedicated command; `siyuan-cli <command> --help` shows all flags.

## Official Sources

The official docs are vendored locally for clarity and repeatability:

- `references/official/API_zh_CN.md` - official Chinese API docs from `siyuan-note/siyuan`
- `references/official/API.md` - official English API docs
- `references/official/DOCUMENT-HPATH.md` - how document titles, renames, and hPaths relate
- `references/official/kernel-api-router.go` - official API router source (every route, including internal ones)
- `references/official/manifest.json` - upstream commit, source URLs, and checksums for the vendored files

Use `rg` on local docs before calling less common endpoints:

```bash
rg -n "/api/filetree/createDocWithMd|通过 Markdown 创建文档" references/official/API_zh_CN.md
rg -n "/api/block/moveBlock|移动块" references/official/API_zh_CN.md
rg -n "moveBlock|createDocWithMd" references/official/kernel-api-router.go
```

Refresh the vendored official docs only when they are missing or stale:

```bash
siyuan-cli update-docs --references-dir <skill-root>/references
```

The source of truth is the official GitHub repo `https://github.com/siyuan-note/siyuan`. Treat `docs.siyuan-note.club` as supplementary community developer documentation unless an official source links to the exact page.

## API Basics

- Default base URL: `http://127.0.0.1:6806`
- Endpoints use `POST` with a JSON body unless the docs say otherwise.
- Auth header: `Authorization: Token <token>`; the token is in `设置 - 鉴权 - API token`.
- Responses follow `{ "code": 0, "msg": "", "data": ... }`. Nonzero `code` means failure; do not treat partial data as success.
- Requests are type-checked strictly: unknown fields and wrong JSON types (e.g. a string where a number is expected) are rejected with `Field [...] has an invalid type`.
- Only endpoints with their own section in `API*.md` are public. Other routes are internal and may change without notice; prefer public ones when both work.
- `code: 0` only covers what the endpoint documents; indexes, caches, and sync may lag. Do not infer read-only behavior from an endpoint name, and do not blindly retry writes after an ambiguous failure — read the current state first.

## CLI Shape

The CLI prints machine-readable JSON to stdout and diagnostics to stderr. The first stderr line is always `[profile: <name>]` (`[profile: none]` for `init-config` and `update-docs`). `[warn]` lines flag results that need attention (e.g. truncated SQL); `[hint]` lines point from `api` calls to dedicated commands.

`search`, `search-docs`, `backlinks`, and `recent` return compact `data` (IDs, hPath, type, plain-text snippet). Pass `search --raw` for the full API response.

## Lookup Strategy

- `search` for user-facing keyword lookup; `--types`, `--notebook`, `--order-by`, and `--method query|regex` narrow it.
- `search-docs` when the user names a document rather than content.
- `sql` for structured filtering: time ranges, attributes, paths, block metadata. Tables: `blocks`, `refs`, `attributes`, `spans`, `assets`. Always add `ORDER BY ... LIMIT/OFFSET`.
- `backlinks --blocks` lists every referencing block with its content; plain `backlinks` lists referencing documents.

## Safe Writes

Before destructive writes:

1. Resolve the target to a unique block or document ID.
2. Read the existing block with `get-block` (or `export-md` for documents) when replacing, moving, or deleting.
3. Mention the target title/path in the final answer, not just the raw ID.

`remove-doc` removes subdocuments too; `remove-notebook` removes the whole notebook — confirm with the user before either.

## Common Raw Endpoints

Endpoints without a dedicated command; check the vendored docs for current payloads:

```bash
siyuan-cli api /api/filetree/getHPathByPath --data '{"notebook":"<id>","path":"/<doc-id>.sy"}'
siyuan-cli api /api/block/transferBlockRef --data '{"fromID":"<id>","toID":"<id>"}'
siyuan-cli api /api/template/renderSprig --data '{"template":"{{now | date \"2006-01-02\"}}"}'
siyuan-cli api /api/notification/pushMsg --data '{"msg":"done","timeout":5000}'
siyuan-cli api /api/av/getAttributeView --data '{"id":"<av-id>"}'
```

## Markdown Notes

Use Markdown for agent-generated note content unless the user asks for raw DOM or another representation. For long content, write a temporary file in the current workspace and pass `--markdown-file`. Block references use `((block-id "anchor text"))`.
