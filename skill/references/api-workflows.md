# SiYuan API & Built-in MCP Workflows

Load this file when a task needs dual-channel (`/api/*` vs `/mcp`) details, structured document addressing (`3.8.11+`), Attribute View (database) payload shapes, or endpoints without dedicated commands.

## Dual-Channel Architecture (`/api/*` + `/mcp`)

SiYuan exposes two official local HTTP interfaces on the same `base_url` and `Authorization: Token <token>`:

1. **`POST /api/*` (Kernel HTTP API)**: Direct JSON endpoints with strict TypeScript-contract validation (`code: 0` on success) and multipart asset upload (`/api/asset/upload`).
2. **`POST /mcp` (Built-in Streamable HTTP MCP, SiYuan ≥ 3.7.0, tested on 3.8.11+)**: 31 official macro-tools (`document`, `block`, `search`, `database`, `export`, `import`, `tag`, `bookmark`, `template`, `history`, `repo`, `sync`, `inbox`, `pdf`, `image`, `bazaar`, etc.) that enforce workspace read-only mode, encrypted-notebook guards, and MCP exposure policies.

`siyuan-cli` speaks both channels over Python stdlib `urllib.request`, opening and closing `/mcp` sessions per call (`DELETE /mcp`) and normalizing all outputs to `{"code": 0, "msg": "", "data": ...}` on `stdout`.

## Official Vendored Docs

Official docs from `https://github.com/siyuan-note/siyuan` are vendored under `references/official/`:

- `references/official/API_zh_CN.md` & `API.md` — public `/api/*` contracts
- `references/official/DOCUMENT-ADDRESSING_zh_CN.md` & `DOCUMENT-HPATH.md` — structured IDs, title segments, literal `/` rules, and hPath behavior
- `references/official/kernel-api-router.go` — all registered HTTP & MCP routes
- `references/official/manifest.json` — pinned upstream commit and SHA-256 checksums

Search locally with `rg` or inspect live MCP schemas on demand:

```bash
rg -n "createDocByParent|resolveDocPath|getDocPaths" references/official/API_zh_CN.md
siyuan-cli mcp-tools                 # list all live /mcp tools and action names
siyuan-cli mcp-tools database        # inspect full inputSchema & docs of one /mcp tool
```

Refresh vendored official docs when upstream SiYuan adds new public contracts:

```bash
siyuan-cli update-docs --references-dir <skill-root>/references
```

## Structured Document Addressing vs hPath (SiYuan 3.8.11+)

- **`create-doc --title <title> [--parent-id <doc-id>]` (`/api/filetree/createDocByParent`)**:
  - Preserves literal `/` inside `title` (e.g. `"C/C++"` or `"TCP/IP"`).
  - Omit `--parent-id` to create at the notebook root (`parentID: null`); pass an existing document ID to create a child document.
  - Supports `--id <doc-id>` (auto-generated if omitted), `--tags`, `--with-math`, `--template-path`, and `--expected-parent-revision`.
- **`resolve-doc-path <seg1> <seg2> ... --notebook <nb>` (`/api/filetree/resolveDocPath`)**:
  - Resolves exact title segments step-by-step without splitting on `/`. Returns `status` (`resolved` | `missing` | `ambiguous`), `resolved` metadata, `candidates`, and `nameConditions`.
- **`doc-paths <id>... --notebook <nb>` (`/api/filetree/getDocPaths`)**:
  - Batch-reads structured document metadata and ancestor `segments` without fetching body content.
- **`create-doc --path /A/B/C` (`/api/filetree/createDocWithMd`)**:
  - Convenience hPath creation that splits on `/` and auto-creates missing intermediate parents. Fails with `pathAmbiguous` if an ancestor has a literal `/` or empty title—switch to `resolve-doc-path` + `create-doc --title --parent-id` in those notebooks.

## Attribute Views (Databases) via `siyuan-cli db`

Run `siyuan-cli mcp-tools database` whenever unsure of a field type or view payload. Common patterns:

```bash
# 1. Inspect database schema, columns (keys), and views
siyuan-cli db search --keyword "Tasks"
siyuan-cli db get --id <av-id>
siyuan-cli db keys --id <av-id>

# 2. Add a column and add/update rows
siyuan-cli db key-add --id <av-id> --name "Priority" --type select
siyuan-cli db item-add --id <av-id> --args '{"items":[{"fields":{"<pk-key-id>":{"block":{"content":"Ship v0.4.0"}}}}]}'
siyuan-cli db item-update --id <av-id> --item-id <item-id> --key-id <key-id> --value '{"select":{"content":"High"}}'

# 3. View filter/sort updates: always read `view-get` first to obtain `revision` and existing filters/sorts
siyuan-cli db view-get --id <av-id> --view-id <view-id>
siyuan-cli db view-sorts-set --id <av-id> --view-id <view-id> --revision <rev> --args '{"sorts":[{"column":"<key-id>","order":"DESC"}]}'
```

## Safe Write & Timeout Recovery Rules

1. Writes are never retried automatically by `siyuan-cli`. If a write times out or returns `commitState: "unknown"`, read back the target document (`doc-paths` / `export-md` / `children`) before re-issuing the write so you do not create duplicates.
2. Before `update-block`, `move-block`, `delete-block`, `remove-doc`, or `remove-notebook`, inspect the target first (`get-block` / `doc-info`) and report human-readable titles/paths in your response.
3. Confirm with the user before `remove-doc`, `remove-notebook`, `remove-tag`, `clean-assets` (all), `history clear`, or `repo checkout` / `purge`.

## Raw Passthrough Examples

```bash
# Built-in /mcp tools without dedicated wrappers (pdf, image, bazaar):
siyuan-cli mcp image list --args '{"id":"<doc-id>"}'
siyuan-cli mcp pdf list --args '{"documentID":"<doc-id>","path":"assets/paper.pdf"}'
siyuan-cli mcp bazaar installed

# Raw /api/* endpoints:
siyuan-cli api /api/notification/pushMsg --data '{"msg":"Done","timeout":5000}'
siyuan-cli api /api/filetree/getHPathByPath --data '{"notebook":"<nb-id>","path":"/<doc-id>.sy"}'
```
