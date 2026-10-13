# siyuan-cli

Local-first CLI and agent skill for SiYuan Note. Zero dependencies (Python ≥ 3.10 stdlib only).

Official references are vendored under `skill/references/official/` so agents can read and grep the docs locally before calling APIs.

Install from GitHub:

```bash
pipx install git+https://github.com/briqt/siyuan-cli.git
# upgrade: pipx install --force git+https://github.com/briqt/siyuan-cli.git
siyuan-cli init-config
open ~/.config/agent-skills/siyuan-cli/config.json
```

Set the SiYuan API token from `设置 - 鉴权 - API token` (Settings > Auth > API token), then run:

```bash
siyuan-cli notebooks
siyuan-cli search "keyword"
siyuan-cli search-docs "title"
siyuan-cli export-md <doc-id>
siyuan-cli create-doc --notebook <notebook-id> --path /Inbox/hello --markdown "# Hello"
siyuan-cli daily-note --notebook <notebook-id> --markdown "- captured"
siyuan-cli --help          # all commands
siyuan-cli -V              # siyuan-cli's own version
siyuan-cli version         # the connected SiYuan server's version
```

Update vendored official docs (pinned to the latest upstream commit, recorded in `manifest.json`):

```bash
siyuan-cli update-docs
```

Run tests:

```bash
python3 -m unittest discover -s tests
```

Install the agent skill from `skill/` with your preferred skills installer.
