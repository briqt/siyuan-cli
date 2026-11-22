import contextlib
import io
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from siyuan_cli import cli, docs
from siyuan_cli.client import (
    SiYuanClient,
    init_config,
    load_config,
    no_proxy_bypass,
    searched_config_paths,
)

DOC_ID = "20240101120000-abc1234"
DOC_ID_2 = "20240101120001-def5678"


class FakeClient:
    def __init__(self, profile=None, responses=None, mcp_responses=None, mcp_tools=None):
        self.profile = {"token": "t", "default_notebook": "nb", "default_doc_path": "/Inbox", **(profile or {})}
        self.base_url = "http://127.0.0.1:6806"
        self.calls = []
        self.mcp_calls = []
        self.responses = responses or {}
        self.mcp_responses = mcp_responses or {}
        self.mcp_tools = mcp_tools or [
            {
                "name": "database",
                "description": "Attribute view operations.\nDetails...",
                "inputSchema": {"properties": {"action": {"enum": ["search", "get"]}}},
            }
        ]

    def post(self, endpoint, payload=None, *, raise_on_error=False):
        self.calls.append((endpoint, payload))
        return self.responses.get(endpoint, {"code": 0, "msg": "", "data": None})

    def upload_assets(self, files, assets_dir="/assets/"):
        self.calls.append(("/api/asset/upload", {"files": files, "assetsDirPath": assets_dir}))
        return {"code": 0}

    def mcp_list_tools(self, *, raise_on_error=False):
        return self.mcp_tools

    def mcp_call(self, tool, arguments=None, *, parse_json_text=True):
        clean = {k: v for k, v in (arguments or {}).items() if v is not None}
        self.mcp_calls.append((tool, clean))
        key = (tool, clean.get("action"))
        return self.mcp_responses.get(key, {"code": 0, "msg": "", "data": {"ok": True}})


def run(argv, client=None):
    client = client or FakeClient()
    args = cli.build_parser().parse_args(argv)
    out = args.handler(args, client)
    return client, out


class PayloadTests(unittest.TestCase):
    def test_search_sends_contract_types(self):
        client, _ = run(["search", "kw", "--types", "paragraph", "heading", "--method", "regex", "--notebook", "nb1", "--order-by", "updated-desc"])
        endpoint, payload = client.calls[0]
        self.assertEqual(endpoint, "/api/search/fullTextSearchBlock")
        self.assertEqual(payload["types"], {"paragraph": True, "heading": True})
        self.assertEqual(payload["method"], 3)
        self.assertEqual(payload["orderBy"], 4)
        self.assertEqual(payload["paths"], ["nb1"])

    def test_search_compacts_output(self):
        resp = {"code": 0, "msg": "", "data": {"blocks": [{"id": "x", "content": "a <mark>hit</mark> &amp; more", "hPath": "/d"}], "matchedBlockCount": 1}}
        _, out = run(["search", "hit"], FakeClient(responses={"/api/search/fullTextSearchBlock": resp}))
        self.assertEqual(out["data"]["blocks"][0]["content"], "a hit & more")
        self.assertEqual(out["data"]["matchedBlockCount"], 1)

    def test_create_doc_bare_title_uses_default_doc_path(self):
        client, _ = run(["create-doc", "--path", "Hello", "--markdown", "# x"])
        self.assertEqual(client.calls[0][1], {"notebook": "nb", "path": "/Inbox/Hello", "markdown": "# x"})

    def test_create_doc_absolute_path_untouched(self):
        client, _ = run(["create-doc", "--notebook", "n2", "--path", "/A/B", "--markdown", "x"])
        self.assertEqual(client.calls[0][1]["path"], "/A/B")
        self.assertEqual(client.calls[0][1]["notebook"], "n2")

    def test_create_doc_structured_title_mode_preserves_slash_and_null_root_parent(self):
        client, _ = run(["create-doc", "--title", "C/C++ Guide", "--markdown", "body", "--tags", "cpp,lang"])
        endpoint, payload = client.calls[0]
        self.assertEqual(endpoint, "/api/filetree/createDocByParent")
        self.assertEqual(payload["notebook"], "nb")
        self.assertIsNone(payload["parentID"])
        self.assertEqual(payload["title"], {"format": "plain", "text": "C/C++ Guide"})
        self.assertEqual(payload["markdown"], "body")
        self.assertEqual(payload["tags"], "cpp,lang")
        self.assertRegex(payload["id"], r"^\d{14}-[0-9a-z]{7}$")

        client2, _ = run(["create-doc", "--title", "Sub/Topic", "--parent-id", DOC_ID, "--id", DOC_ID_2])
        self.assertEqual(client2.calls[0][1]["parentID"], DOC_ID)
        self.assertEqual(client2.calls[0][1]["id"], DOC_ID_2)
        self.assertEqual(client2.calls[0][1]["markdown"], "")

    def test_resolve_doc_path_and_doc_paths(self):
        client, _ = run(["resolve-doc-path", "Notes", "C/C++"])
        self.assertEqual(
            client.calls[0],
            ("/api/filetree/resolveDocPath", {"notebook": "nb", "start": {"kind": "root"}, "segments": ["Notes", "C/C++"]}),
        )
        client2, _ = run(["doc-paths", DOC_ID, DOC_ID_2, "--include-icons"])
        self.assertEqual(
            client2.calls[0],
            ("/api/filetree/getDocPaths", {"notebook": "nb", "ids": [DOC_ID, DOC_ID_2], "includeIcons": True}),
        )

    def test_markdown_flags_are_exclusive(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            cli.build_parser().parse_args(["append-block", DOC_ID, "--markdown", "a", "--markdown-file", "b"])

    def test_missing_input_files_emit_json_error_without_traceback(self):
        for argv in (
            ["append-block", DOC_ID, "--markdown-file", "/nonexistent/missing-note-file.md"],
            ["api", "/api/system/version", "--data-file", "/nonexistent/missing-data.json"],
            ["set-attrs", DOC_ID, "--attrs-file", "/nonexistent/missing-attrs.json"],
        ):
            err = io.StringIO()
            with self.assertRaises(SystemExit) as cm, contextlib.redirect_stderr(err):
                run(argv)
            self.assertEqual(cm.exception.code, 1)
            parsed = json.loads(err.getvalue())
            self.assertEqual(parsed["error"], "file read error")

    def test_append_and_prepend_use_own_endpoints(self):
        client, _ = run(["append-block", DOC_ID, "--markdown", "a"])
        run_prepend, _ = run(["prepend-block", DOC_ID, "--markdown", "b"])
        self.assertEqual(client.calls[0], ("/api/block/appendBlock", {"parentID": DOC_ID, "dataType": "markdown", "data": "a"}))
        self.assertEqual(run_prepend.calls[0][0], "/api/block/prependBlock")

    def test_move_doc_same_and_cross_notebook(self):
        client, _ = run(["move-doc", "a", "b", "--to", "nb"])
        self.assertEqual(client.calls[0], ("/api/filetree/moveDocsByID", {"fromIDs": ["a", "b"], "toID": "nb"}))

        cross, _ = run(["move-doc", DOC_ID, "--to", "nb2", "--notebook", "nb2"])
        self.assertEqual(cross.mcp_calls[0], ("document", {"action": "move", "id": DOC_ID, "notebook": "nb2", "parentID": ""}))

    def test_move_block_requires_anchor(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            run(["move-block", DOC_ID])
        client, _ = run(["move-block", DOC_ID, "--previous-id", "p"])
        self.assertEqual(client.calls[0][1], {"id": DOC_ID, "previousID": "p"})

    def test_update_block_lock_type(self):
        client, _ = run(["update-block", DOC_ID, "--markdown", "x", "--lock-type"])
        self.assertTrue(client.calls[0][1]["lockType"])

    def test_daily_note_modes(self):
        client, _ = run(["daily-note"])
        self.assertEqual(client.calls[0], ("/api/filetree/createDailyNote", {"notebook": "nb"}))
        client, _ = run(["daily-note", "--prepend", "--markdown", "x"])
        self.assertEqual(client.calls[0][0], "/api/block/prependDailyNoteBlock")

    def test_backlinks_rejects_non_id_before_sql(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            cli.build_parser().parse_args(["backlinks", "x' OR 1=1 --", "--blocks"])
        client, _ = run(["backlinks", DOC_ID, "--blocks"])
        self.assertIn(f"def_block_id = '{DOC_ID}'", client.calls[0][1]["stmt"])

    def test_search_docs_derives_id(self):
        resp = {"code": 0, "data": [{"path": f"/x/{DOC_ID}.sy", "hPath": "a/b", "box": "nb"}]}
        _, out = run(["search-docs", "b"], FakeClient(responses={"/api/filetree/searchDocs": resp}))
        self.assertEqual(out["data"][0]["id"], DOC_ID)

    def test_sql_warns_when_truncated(self):
        resp = {"code": 0, "data": [], "limit": 64, "truncated": True}
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            run(["sql", "SELECT 1"], FakeClient(responses={"/api/query/sql": resp}))
        self.assertIn("truncated", err.getvalue())

    def test_api_hint_for_wrapped_endpoint(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            run(["api", "api/block/moveBlock", "--data", "{}"])
        self.assertIn("move-block", err.getvalue())

    def test_every_hinted_command_exists(self):
        commands = set(cli.build_parser()._subparsers._group_actions[0].choices)
        for hint in cli.ENDPOINT_TO_COMMAND.values():
            self.assertIn(hint.split()[0], commands)

    def test_mcp_backed_commands_route_cleanly(self):
        c, _ = run(["db", "item-update", "--id", "av1", "--item-id", "row1", "--key-id", "col1", "--value", '{"text":{"content":"ok"}}'])
        self.assertEqual(
            c.mcp_calls[0],
            ("database", {"action": "item_update", "id": "av1", "itemID": "row1", "keyID": "col1", "value": {"text": {"content": "ok"}}}),
        )

        c2, _ = run(["rename-tag", "old/tag", "new/tag"])
        self.assertEqual(c2.mcp_calls[0], ("tag", {"action": "rename", "old": "old/tag", "new": "new/tag"}))

        c3, _ = run(["search-assets", "invoice", "--ext", ".pdf"])
        self.assertEqual(c3.mcp_calls[0], ("search", {"action": "asset", "query": "invoice", "ext": ".pdf", "page": 1, "pageSize": 20}))

        c4, _ = run(["sync", "perform"])
        self.assertEqual(c4.mcp_calls[0], ("sync", {"action": "perform"}))

        _, tools_out = run(["mcp-tools"], c4)
        self.assertEqual(tools_out["data"]["count"], 1)
        self.assertEqual(tools_out["data"]["tools"][0]["name"], "database")


class ConfigAndMcpTransportTests(unittest.TestCase):
    def test_cwd_dot_config_is_never_implicitly_loaded(self):
        with tempfile.TemporaryDirectory() as home_dir, tempfile.TemporaryDirectory() as cwd_dir:
            # Plant a broken/hostile .config.json in CWD and in a skill directory under CWD
            (Path(cwd_dir) / ".config.json").write_text("{broken", encoding="utf-8")
            (Path(cwd_dir) / "skills" / "siyuan-cli").mkdir(parents=True)
            (Path(cwd_dir) / "skills" / "siyuan-cli" / ".config.json").write_text('{"profiles":{"default":{"base_url":"http://evil.example","token":"x"}}}', encoding="utf-8")

            prev_cwd = os.getcwd()
            os.chdir(cwd_dir)
            try:
                with mock.patch.dict(os.environ, {"SIYUAN_CLI_HOME": home_dir}):
                    res = init_config()
                    self.assertTrue(res["ok"])
                    cfg_path = Path(res["path"])
                    if os.name != "nt":
                        self.assertEqual(stat.S_IMODE(cfg_path.stat().st_mode), 0o600)
                    cfg_data = json.loads(cfg_path.read_text(encoding="utf-8"))
                    cfg_data["profiles"]["default"]["token"] = "real-token"
                    cfg_path.write_text(json.dumps(cfg_data), encoding="utf-8")

                    self.assertEqual(searched_config_paths(), [cfg_path])
                    loaded_path, prof_name, prof = load_config(None, None)
                    self.assertEqual(loaded_path, cfg_path)
                    self.assertEqual(prof_name, "default")
                    self.assertEqual(prof["base_url"], "http://127.0.0.1:6806")
            finally:
                os.chdir(prev_cwd)

    def test_mcp_streamable_http_session_lifecycle_and_json_unwrap(self):
        client = SiYuanClient({"base_url": "http://127.0.0.1:6806", "token": "sec"})
        seen = []

        def fake_mcp_http(method_http, payload=None, session_id=None, timeout=None):
            seen.append((method_http, payload.get("method") if isinstance(payload, dict) else None, session_id))
            if method_http == "POST" and payload.get("method") == "initialize":
                return "sid-123", "application/json", json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2025-03-26"}})
            if method_http == "POST" and payload.get("method") == "notifications/initialized":
                return "sid-123", "application/json", ""
            if method_http == "POST" and payload.get("method") == "tools/call":
                return "sid-123", "application/json", json.dumps({
                    "jsonrpc": "2.0",
                    "id": 2,
                    "result": {"content": [{"type": "text", "text": '{"action":"get","data":{"id":"av1"}}'}]},
                })
            if method_http == "DELETE":
                return "sid-123", "text/plain", ""
            raise AssertionError(f"Unexpected call: {method_http} {payload}")

        with mock.patch.object(client, "_mcp_http", side_effect=fake_mcp_http):
            out = client.mcp_call("database", {"action": "get", "id": "av1", "unused": None})
        self.assertEqual(out, {"code": 0, "msg": "", "data": {"action": "get", "data": {"id": "av1"}}})
        self.assertEqual(
            seen,
            [
                ("POST", "initialize", None),
                ("POST", "notifications/initialized", "sid-123"),
                ("POST", "tools/call", "sid-123"),
                ("DELETE", None, "sid-123"),
            ],
        )


class NoProxyTests(unittest.TestCase):
    def check(self, no_proxy, host):
        with mock.patch.dict(os.environ, {"no_proxy": no_proxy, "NO_PROXY": no_proxy}):
            return no_proxy_bypass(host)

    def test_forms(self):
        self.assertTrue(self.check("100.64.0.0/10", "100.64.0.6"))
        self.assertTrue(self.check("100.64.*", "100.64.0.6"))
        self.assertTrue(self.check(".local", "box.local"))
        self.assertTrue(self.check("[::1]", "::1"))
        self.assertFalse(self.check("10.0.0.0/8", "100.64.0.6"))
        self.assertFalse(self.check("", "127.0.0.1"))


class UpdateDocsTests(unittest.TestCase):
    def test_manifest_is_portable_and_writes_nothing_on_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            refs = Path(tmp) / "references"
            refs.mkdir()
            with mock.patch.object(docs, "latest_commit", return_value="abc"), \
                    mock.patch.object(docs, "fetch_text_url", side_effect=lambda url, **_: f"content of {url}"):
                result = docs.update_docs(str(refs), timeout=5)
            manifest = json.loads((refs / "official" / "manifest.json").read_text())
            self.assertEqual(manifest["commit"], "abc")
            for entry in manifest["files"]:
                self.assertFalse(Path(entry["path"]).is_absolute())
                self.assertIn("/blob/abc/", entry["source_url"])
            self.assertEqual(len(result["changed"]), len(docs.OFFICIAL_DOCS))

            def flaky(url, **_):
                if "router" in url:
                    raise docs.FetchError({"error": "network error", "url": url})
                return "new"

            before = (refs / "official" / "API.md").read_text()
            with mock.patch.object(docs, "latest_commit", return_value=None), \
                    mock.patch.object(docs, "fetch_text_url", side_effect=flaky), \
                    self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                docs.update_docs(str(refs), timeout=5)
            self.assertEqual((refs / "official" / "API.md").read_text(), before)


if __name__ == "__main__":
    unittest.main()
