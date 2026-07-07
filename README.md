# siyuan-cli

Local-first CLI and agent skill for SiYuan Note.

Official references are vendored under `skill/references/official/` so agents can read and grep the docs locally before calling APIs.

Install from GitHub:

```bash
pipx install git+https://github.com/briqt/siyuan-cli.git
siyuan-cli init-config
open ~/.config/agent-skills/siyuan-cli/config.json
```

Set the SiYuan API token from `Settings > About`, then run:

```bash
siyuan-cli notebooks
siyuan-cli search "keyword"
siyuan-cli export-md <doc-id>
siyuan-cli create-doc --notebook <notebook-id> --path /Inbox/hello --markdown "# Hello"
siyuan-cli -V              # siyuan-cli's own version
siyuan-cli version        # the connected SiYuan server's version
```

Update vendored official docs:

```bash
siyuan-cli update-docs
```

Install the agent skill from `skill/` with your preferred skills installer.
