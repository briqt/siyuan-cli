# siyuan-note-cli

Local-first CLI and agent skill for SiYuan Note.

Install from GitHub:

```bash
pipx install git+https://github.com/briqt/siyuan-note-cli.git
siyuan-note-cli init-config
open ~/.config/agent-skills/siyuan-note-cli/config.json
```

Set the SiYuan API token from `Settings > About`, then run:

```bash
siyuan-note-cli notebooks
siyuan-note-cli search "keyword"
siyuan-note-cli create-doc --notebook <notebook-id> --path /Inbox/hello --markdown "# Hello"
```

Install the agent skill from `skill/` with your preferred skills installer.
