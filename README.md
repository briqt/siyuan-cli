# siyuan-note-cli

Local-first CLI and agent skill for SiYuan Note.

Official references:

- SiYuan repository: https://github.com/siyuan-note/siyuan
- Official API documentation: https://github.com/siyuan-note/siyuan/blob/master/API.md
- Official Chinese API documentation: https://github.com/siyuan-note/siyuan/blob/master/API_zh_CN.md
- API router source: https://github.com/siyuan-note/siyuan/blob/master/kernel/api/router.go

Install from GitHub:

```bash
pipx install git+https://github.com/briqt/siyuan-note-cli.git
siyuan-note-cli init-config
open ~/.config/agent-skills/siyuan-note-cli/config.json
```

Set the SiYuan API token from `Settings > About`, then run:

```bash
siyuan-note-cli notebooks
siyuan-note-cli api-docs --query "/api/block/appendBlock"
siyuan-note-cli api-docs --lang en --query "Append blocks"
siyuan-note-cli search "keyword"
siyuan-note-cli export-md <doc-id>
siyuan-note-cli create-doc --notebook <notebook-id> --path /Inbox/hello --markdown "# Hello"
siyuan-note-cli api /api/system/version
```

Install the agent skill from `skill/` with your preferred skills installer.
