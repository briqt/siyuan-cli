# siyuan-cli

Local-first CLI and companion AI agent skill for [SiYuan Note](https://github.com/siyuan-note/siyuan). Zero third-party dependencies (Python ≥ 3.10 standard library only).

`siyuan-cli` combines SiYuan's official HTTP API (`/api/*`) and built-in MCP service (`/mcp`, SiYuan ≥ 3.7.0, tested on `3.8.11+`) behind one fast, stateless CLI—giving agents full official SiYuan capabilities without paying the ~20,000-token per-turn schema cost of mounting raw MCP tools.

Official SiYuan API and addressing references are vendored under `skills/siyuan-cli/references/official/` so agents can search contracts locally offline.

## Install & Upgrade

```bash
# Install CLI (uv; pipx works too: pipx install git+https://github.com/briqt/siyuan-cli.git)
uv tool install git+https://github.com/briqt/siyuan-cli.git

# Upgrade CLI (update notices print the command matching how it was installed)
uv tool install --force --reinstall --refresh git+https://github.com/briqt/siyuan-cli.git
# with pipx: pipx uninstall siyuan-cli; pipx install git+https://github.com/briqt/siyuan-cli.git

# Install / sync companion agent skill
npx skills add briqt/siyuan-cli -g -y
```

## Configure & Verify

```bash
siyuan-cli init-config
# Edit ~/.config/agent-skills/siyuan-cli/config.json and set profiles.default.token
# from SiYuan: 设置 - 鉴权 - API token (Settings > Auth > API token)

siyuan-cli doctor        # verify CLI/Skill versions, config, server version & /mcp tools
siyuan-cli check-update  # check GitHub release & notice feed
```

## Common Commands

```bash
# Search & inspect
siyuan-cli notebooks
siyuan-cli search "keyword"
siyuan-cli semantic-search "topic"
siyuan-cli search-assets "clause" --ext .pdf
siyuan-cli search-docs "title"
siyuan-cli sql-schema
siyuan-cli sql "SELECT id, content, hpath FROM blocks LIMIT 20"
siyuan-cli export-md <doc-id>

# Structured document creation (3.8.11+, preserves literal '/' in titles) & daily notes
siyuan-cli create-doc --notebook <notebook-id> --title "C/C++ Notes" --markdown "# Hello"
siyuan-cli create-doc --notebook <notebook-id> --path /Inbox/hello --markdown "# Hello"
siyuan-cli daily-note --notebook <notebook-id> --markdown "- captured"

# Databases (Attribute Views), tags, bookmarks, export/import, templates, history & sync
siyuan-cli db search --keyword "Tasks"
siyuan-cli tags
siyuan-cli export <doc-id> --format html
siyuan-cli sync status

# Full official ceiling & help
siyuan-cli mcp-tools [tool]
siyuan-cli mcp <tool> [action] --args '{...}'
siyuan-cli api <endpoint> --data '{...}'
siyuan-cli --help
siyuan-cli -V              # CLI version
siyuan-cli version         # connected SiYuan server version
```

## Development

Refresh vendored official SiYuan docs (pinned to a single upstream commit in `skills/siyuan-cli/references/official/manifest.json`):

```bash
python3 -m siyuan_cli.cli update-docs
```

Run tests:

```bash
python3 -m unittest discover -s tests -v
```

## Community

[学 AI，上 Linux DO](https://linux.do/)

## License

[MIT](LICENSE)
