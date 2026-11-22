# Changelog

## v0.4.1 — 2026-11-22

- Move the companion skill to `skills/siyuan-cli/`. Installed skills follow automatically on the next `npx skills add briqt/siyuan-cli -g -y` or `npx skills update`; `doctor` and `update-docs` look in the new location.
- Skill description states the capability boundary instead of listing individual operations.
- Add the MIT `LICENSE` file; drop leftover `.gitignore` entries for in-repo config files, which the CLI has not read since v0.4.0.

## v0.4.0 — 2026-11-22

- **Dual-channel official SiYuan engine (`/api/*` + `/mcp`)**:
  - Add stdlib Streamable HTTP `/mcp` client (`POST /mcp` + `DELETE /mcp` session cleanup) alongside `/api/*`, unlocking SiYuan's built-in official agent capabilities with zero third-party dependencies and zero idle MCP schema token overhead.
  - Add `mcp-tools [tool]` and `mcp <tool> [action] --args '{...}'` for 100% lossless access to all 31 built-in SiYuan MCP tools.
- **Follow SiYuan `3.8.11` structured document addressing & common official capabilities**:
  - Upgrade `create-doc` with `--title` + `--parent-id` mode (`/api/filetree/createDocByParent`), preserving literal `/` in titles (such as `C/C++`), while keeping `--path` hPath mode compatible.
  - Add `resolve-doc-path`, `doc-paths`, `duplicate-doc`, and cross-notebook `move-doc --notebook`.
  - Add `semantic-search`, `search-assets`, `asset-content`, `sql-schema`, `block-dom`, `tree-stat`, `batch-attrs`, `transfer-ref`, and `refresh-backlinks`.
  - Add `db` subcommand covering SiYuan Attribute Views (databases), plus tag/bookmark write commands (`rename-tag`, `remove-tag`, `bookmark-labels`, `rename-bookmark`, `remove-bookmark`), multi-format `export`/`export-data`, `import`, `unused-assets`/`clean-assets`/`asset-stat`, `template`, `render-sprig`, `history`, `repo`, `sync`, `inbox`, `workspaces`/`workspace-list`, `set-notebook-conf`, and `notebook-icon`.
  - Refresh vendored official references to SiYuan `3.8.11` and vendor `DOCUMENT-ADDRESSING_zh_CN.md`.
- **Configuration, update checks & diagnostics hardening**:
  - Remove implicit `./.config.json` and `./skill/.config.json` working-directory config lookup; load strictly from `~/.config/agent-skills/siyuan-cli/config.json` (or explicit `--config` / `SIYUAN_CLI_HOME`) and write initialized config with `0600` permissions.
  - Add bounded optional update & notice checks (`notice.json`, `check-update`, `--no-update-check`, `disable_update_check`) and `doctor` diagnostics.
  - Convert missing `--markdown-file` / `--data-file` / `--attrs-file` errors into structured JSON on `stderr` instead of raw Python tracebacks; complete `ENDPOINT_TO_COMMAND` hints.
- **Skill & repository hygiene**:
  - Remove external `knowledge-project` coupling from `skill/SKILL.md`, add `metadata.version` sync tests, `.gitignore`, `AGENTS.md`, and `.handoff/` maintenance records.

## v0.3.1 — 2026-10-13

- Broaden skill trigger description, add ID primer and troubleshooting table.

## v0.3.0 — 2026-10-12

- Follow SiYuan 3.8.6 API, add common commands, and restructure Python package.

## v0.2.2

- Warn on `stderr` when `/api/query/sql` truncates results at the server default limit (~64 rows).

## v0.2.1

- Update official doc URLs to `docs/` path and honor `no_proxy` CIDR/wildcard entries.
