import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from siyuan_cli import cli, docs
from siyuan_cli.client import no_proxy_bypass

DOC_ID = "20240101120000-abc1234"


class FakeClient:
    def __init__(self, profile=None, responses=None):
        self.profile = {"token": "t", "default_notebook": "nb", "default_doc_path": "/Inbox", **(profile or {})}
        self.calls = []
        self.responses = responses or {}

    def post(self, endpoint, payload=None):
        self.calls.append((endpoint, payload))
        return self.responses.get(endpoint, {"code": 0, "msg": "", "data": None})

    def upload_assets(self, files, assets_dir="/assets/"):
        self.calls.append(("/api/asset/upload", {"files": files, "assetsDirPath": assets_dir}))
        return {"code": 0}


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

    def test_markdown_flags_are_exclusive(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            cli.build_parser().parse_args(["append-block", DOC_ID, "--markdown", "a", "--markdown-file", "b"])

    def test_append_and_prepend_use_own_endpoints(self):
        client, _ = run(["append-block", DOC_ID, "--markdown", "a"])
        run_prepend, _ = run(["prepend-block", DOC_ID, "--markdown", "b"])
        self.assertEqual(client.calls[0], ("/api/block/appendBlock", {"parentID": DOC_ID, "dataType": "markdown", "data": "a"}))
        self.assertEqual(run_prepend.calls[0][0], "/api/block/prependBlock")

    def test_move_doc(self):
        client, _ = run(["move-doc", "a", "b", "--to", "nb"])
        self.assertEqual(client.calls[0], ("/api/filetree/moveDocsByID", {"fromIDs": ["a", "b"], "toID": "nb"}))

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
