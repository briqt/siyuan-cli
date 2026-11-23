import json
import re
import tempfile
import unittest
from pathlib import Path

from siyuan_cli import __version__
from siyuan_cli.client import CONFIG_TEMPLATE
from siyuan_cli.update_check import (
    DAY_MS,
    HOUR_MS,
    check_update,
    evaluate_notifications,
    is_update_disabled,
    newer,
    stable_version,
    upgrade_command,
    validate_manifest,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


class UpdateCheckTests(unittest.TestCase):
    def test_semver_and_manifest_validation(self):
        self.assertEqual(stable_version("v0.4.0"), (0, 4, 0))
        self.assertIsNone(stable_version("0.4.0-rc.1"))
        self.assertTrue(newer("0.10.0", "0.9.0"))
        self.assertFalse(newer("0.4.0", "0.4.0"))
        self.assertFalse(newer("0.3.1", "0.4.0"))

        valid = validate_manifest(
            {
                "schema_version": 1,
                "latest_version": "v0.5.0",
                "release_url": "https://github.com/briqt/siyuan-cli/releases/tag/v0.5.0",
                "notice_id": "v0.5.0-note",
                "notice": "Hello\x1b[31mWorld",
            }
        )
        self.assertEqual(valid["latest_version"], "0.5.0")
        self.assertNotIn("\x1b", valid["notice"])

        with self.assertRaises(ValueError):
            validate_manifest(
                {
                    "schema_version": 1,
                    "latest_version": "0.5.0",
                    "release_url": "https://evil.example.com/briqt/siyuan-cli/releases/tag/v0.5.0",
                    "notice_id": "",
                    "notice": "",
                }
            )

    def test_throttle_cooldown_backoff_and_stale_notice_suppression(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            calls = 0

            def fake_opener(_url, _timeout):
                nonlocal calls
                calls += 1
                return json.dumps(
                    {
                        "schema_version": 1,
                        "latest_version": "0.5.0",
                        "release_url": "https://github.com/briqt/siyuan-cli/releases/tag/v0.5.0",
                        "notice_id": "n1",
                        "notice": "Important notice",
                    }
                ).encode("utf-8")

            emitted = []
            t0 = 1_800_000_000_000
            r1 = check_update(cache_dir, current="0.4.0", now_ms=t0, opener_fn=fake_opener, emit=emitted.append)
            self.assertEqual(r1["status"], "checked")
            self.assertTrue(r1["update_available"])
            self.assertEqual(len(emitted), 2)
            self.assertIn(f"Upgrade CLI: {upgrade_command()}", emitted[0])

            # Within 1h throttle and 24h cooldown: zero network calls, zero new notices
            r2 = check_update(cache_dir, current="0.4.0", now_ms=t0 + 60_000, opener_fn=fake_opener, emit=emitted.append)
            self.assertEqual(r2["status"], "cached")
            self.assertEqual(calls, 1)
            self.assertEqual(len(emitted), 2)

            # After 25h: fetches again and notifies again
            r3 = check_update(cache_dir, current="0.4.0", now_ms=t0 + 25 * HOUR_MS, opener_fn=fake_opener, emit=emitted.append)
            self.assertEqual(r3["status"], "checked")
            self.assertEqual(calls, 2)
            self.assertEqual(len(emitted), 4)

            # Stale manifest notice (latest_version < current) is suppressed
            old_state = {
                "last_success_at": t0,
                "manifest": {
                    "schema_version": 1,
                    "latest_version": "0.3.1",
                    "release_url": "https://github.com/briqt/siyuan-cli/releases/tag/v0.3.1",
                    "notice_id": "old-notice",
                    "notice": "Old notice",
                },
            }
            self.assertEqual(evaluate_notifications(old_state, "0.4.0", t0), [])
            # Expired cache (>7d) produces no notifications
            old_state["manifest"]["latest_version"] = "0.9.0"
            self.assertEqual(evaluate_notifications(old_state, "0.4.0", t0 + 8 * DAY_MS), [])

            # Opt-out flags
            self.assertTrue(is_update_disabled(no_update_check=True))
            self.assertTrue(is_update_disabled(config_disabled=True))
            self.assertTrue(is_update_disabled(env={"SIYUAN_CLI_NO_UPDATE_CHECK": "1"}))


class RepoConsistencyTests(unittest.TestCase):
    def test_version_skill_config_and_notice_stay_in_sync(self):
        skill_md = (REPO_ROOT / "skills" / "siyuan-cli" / "SKILL.md").read_text(encoding="utf-8")
        m = re.search(r'^\s*version:\s*"?([0-9]+\.[0-9]+\.[0-9]+)"?\s*$', skill_md, re.MULTILINE)
        self.assertIsNotNone(m, "skills/siyuan-cli/SKILL.md must declare metadata.version")
        self.assertEqual(m.group(1), __version__)

        # Config template matches skills/siyuan-cli/config.json and schema properties
        skill_cfg = json.loads((REPO_ROOT / "skills" / "siyuan-cli" / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(skill_cfg, CONFIG_TEMPLATE)
        schema = json.loads((REPO_ROOT / "skills" / "siyuan-cli" / "config.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(set(schema["properties"].keys()), set(CONFIG_TEMPLATE.keys()))

        # notice.json is valid and never ahead of local __version__
        notice_data = json.loads((REPO_ROOT / "notice.json").read_text(encoding="utf-8"))
        validated = validate_manifest(notice_data)
        self.assertFalse(newer(validated["latest_version"], __version__))



class UpgradeCommandTests(unittest.TestCase):
    def test_matches_install_channel(self):
        uv = upgrade_command("/home/u/.local/share/uv/tools/siyuan-cli")
        self.assertEqual(uv, "uv tool install --force --reinstall --refresh git+https://github.com/briqt/siyuan-cli.git")
        self.assertEqual(upgrade_command(r"C:\Users\u\AppData\Roaming\uv\tools\siyuan-cli"), uv)
        pipx = upgrade_command("/home/u/.local/share/pipx/venvs/siyuan-cli")
        self.assertEqual(pipx, "pipx uninstall siyuan-cli; pipx install git+https://github.com/briqt/siyuan-cli.git")
        self.assertNotIn("--force", pipx)
        other = upgrade_command("/usr")
        self.assertIn(uv, other)
        self.assertIn(pipx, other)


if __name__ == "__main__":
    unittest.main()
