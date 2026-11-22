"""Config discovery, HTTP transport, SiYuan /api/* and built-in /mcp calls."""

from __future__ import annotations

import fnmatch
import ipaddress
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, NoReturn

from . import __version__

SKILL_NAME = "siyuan-cli"
DEFAULT_BASE_URL = "http://127.0.0.1:6806"
TOKEN_LOCATION = "SiYuan Settings > Auth > API token (设置 - 鉴权 - API token)"
USER_AGENT = f"{SKILL_NAME}/{__version__}"
MCP_PROTOCOL_VERSION = "2025-03-26"

CONFIG_TEMPLATE: dict[str, Any] = {
    "active": "default",
    "disable_update_check": False,
    "profiles": {
        "default": {
            "base_url": DEFAULT_BASE_URL,
            "token": "",
            "timeout_seconds": 30,
            "default_notebook": "",
            "default_doc_path": "/Inbox",
        }
    },
}


def eprint(message: str) -> None:
    print(message, file=sys.stderr)


def json_out(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def fail(payload: dict[str, Any], code: int = 1) -> NoReturn:
    eprint(json.dumps(payload, ensure_ascii=False, indent=2))
    raise SystemExit(code)


# --- config -----------------------------------------------------------------


def user_data_dir(env: dict[str, str] | None = None) -> Path:
    env_map = os.environ if env is None else env
    override = (env_map.get("SIYUAN_CLI_HOME") or "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".config" / "agent-skills" / SKILL_NAME


def user_config_path(env: dict[str, str] | None = None) -> Path:
    return user_data_dir(env) / "config.json"


def searched_config_paths(explicit: str | None = None) -> list[Path]:
    """Return candidate config paths.

    Never searches Path.cwd(): implicit working-directory configs break calls
    made inside unrelated projects and allow untrusted repos to redirect API calls.
    """
    if explicit:
        return [Path(explicit).expanduser()]
    return [user_config_path()]


def _quote_shell_path(path: Path) -> str:
    s = str(path)
    if " " in s or "\t" in s:
        return f'"{s}"'
    return s


def init_config(overwrite: bool = False) -> dict[str, Any]:
    target = user_config_path()
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    quoted = _quote_shell_path(target)
    if target.exists() and not overwrite:
        return {"ok": True, "message": "config already exists", "path": str(target), "next": f"Edit {quoted}"}
    tmp = target.parent / f".config.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    try:
        tmp.write_text(json.dumps(CONFIG_TEMPLATE, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, target)
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
    return {"ok": True, "message": "created config from template", "path": str(target), "next": f"Edit {quoted}"}


def inspect_config(explicit: str | None = None, profile_override: str | None = None) -> dict[str, Any]:
    """Validate config without exiting; used by both load_config and doctor."""
    searched = searched_config_paths(explicit)
    searched_str = [str(p) for p in searched]
    default_target = _quote_shell_path(user_config_path())
    repair = f"siyuan-cli init-config  # then edit {default_target}"
    for path in searched:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return {
                "ok": False,
                "error": {"error": "invalid config json", "path": str(path), "detail": str(exc), "searched": searched_str, "repair": repair},
            }
        if not isinstance(data, dict):
            return {
                "ok": False,
                "error": {"error": "config root must be a JSON object", "path": str(path), "searched": searched_str, "repair": repair},
            }
        if "disable_update_check" in data and not isinstance(data["disable_update_check"], bool):
            return {
                "ok": False,
                "error": {"error": "disable_update_check must be boolean", "path": str(path)},
            }
        profiles = data.get("profiles")
        if not isinstance(profiles, dict):
            return {
                "ok": False,
                "error": {"error": "config missing profiles object", "path": str(path), "searched": searched_str, "repair": repair},
            }
        profile_name = profile_override or data.get("active") or "default"
        profile = profiles.get(profile_name)
        if not isinstance(profile, dict):
            return {
                "ok": False,
                "error": {
                    "error": "profile not found",
                    "profile": profile_name,
                    "path": str(path),
                    "available_profiles": sorted(profiles),
                },
            }
        base_url = profile.get("base_url") or DEFAULT_BASE_URL
        token = profile.get("token", "")
        if not isinstance(base_url, str) or not base_url.startswith(("http://", "https://")):
            return {
                "ok": False,
                "error": {"error": "invalid base_url", "profile": profile_name, "path": str(path)},
            }
        timeout_val = profile.get("timeout_seconds", 30)
        if isinstance(timeout_val, bool) or not isinstance(timeout_val, int) or timeout_val < 1:
            return {
                "ok": False,
                "error": {"error": "timeout_seconds must be a positive integer", "profile": profile_name, "path": str(path)},
            }
        if not isinstance(token, str) or not token.strip():
            return {
                "ok": False,
                "path": path,
                "profile_name": profile_name,
                "disable_update_check": bool(data.get("disable_update_check", False)),
                "error": {
                    "error": "SiYuan API token is not configured",
                    "profile": profile_name,
                    "path": str(path),
                    "searched": searched_str,
                    "repair": f"Edit {_quote_shell_path(path)}",
                    "repair_note": f"Set profiles.{profile_name}.token from {TOKEN_LOCATION}.",
                },
            }
        return {
            "ok": True,
            "path": path,
            "profile_name": profile_name,
            "profile": profile,
            "disable_update_check": bool(data.get("disable_update_check", False)),
            "available_profiles": sorted(profiles),
        }
    return {
        "ok": False,
        "error": {"error": "config not found", "searched": searched_str, "repair": repair},
    }


def load_config(explicit: str | None, profile_override: str | None) -> tuple[Path, str, dict[str, Any]]:
    info = inspect_config(explicit, profile_override)
    if not info["ok"]:
        fail(info["error"])
    profile = dict(info["profile"])
    profile["_disable_update_check"] = info["disable_update_check"]
    return info["path"], info["profile_name"], profile


def read_disable_update_check(explicit: str | None = None) -> bool:
    for path in searched_config_paths(explicit):
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("disable_update_check") is True:
                return True
        except (OSError, json.JSONDecodeError):
            return False
    return False


# --- transport --------------------------------------------------------------


def no_proxy_bypass(host: str) -> bool:
    """Return True if *host* should bypass the proxy per no_proxy/NO_PROXY.

    The stdlib matcher urllib uses (proxy_bypass_environment) only does plain
    host/domain-suffix matching -- it ignores CIDR ranges (e.g. 100.64.0.0/10)
    and glob wildcards (e.g. 100.64.*, *.local). Tailscale/CGNAT hosts like
    100.64.0.6 are only expressible that way, so the stdlib silently sends them
    through the proxy (which can't reach the tailnet). This matcher honors all
    three forms.
    """
    no_proxy = os.environ.get("no_proxy") or os.environ.get("NO_PROXY") or ""
    if not no_proxy or not host:
        return False
    host = host.strip().strip("[]").lower()
    host_ip = None
    try:
        host_ip = ipaddress.ip_address(host)
    except ValueError:
        pass
    for raw in no_proxy.split(","):
        entry = raw.strip()
        if not entry:
            continue
        if entry == "*":
            return True
        if "/" in entry:  # CIDR, e.g. 100.64.0.0/10
            if host_ip is not None:
                try:
                    if host_ip in ipaddress.ip_network(entry, strict=False):
                        return True
                except ValueError:
                    pass
            continue
        if "*" in entry or "?" in entry:  # glob, e.g. 100.64.* or *.local
            if fnmatch.fnmatch(host, entry.lower()):
                return True
            continue
        name = entry.strip("[]").lstrip(".").lower()  # plain host or domain suffix
        if host == name or host.endswith("." + name):
            return True
    return False


def _open(req: urllib.request.Request, timeout: float, extra_handlers: list[urllib.request.BaseHandler] | None = None):
    """Open *req* while honoring no_proxy correctly."""
    host = urllib.parse.urlsplit(req.full_url).hostname or ""
    handlers: list[urllib.request.BaseHandler] = []
    if no_proxy_bypass(host):
        handlers.append(urllib.request.ProxyHandler({}))
    if extra_handlers:
        handlers.extend(extra_handlers)
    opener = urllib.request.build_opener(*handlers)
    return opener.open(req, timeout=timeout)


class FetchError(Exception):
    def __init__(self, info: dict[str, Any]):
        super().__init__(info.get("error", "fetch error"))
        self.info = info


def fetch_text_url(url: str, timeout: float = 30, attempts: int = 3) -> str:
    """GET *url* as text, retrying transient network failures (GET is idempotent)."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    info: dict[str, Any] = {}
    for attempt in range(1, attempts + 1):
        try:
            with _open(req, timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            info = {"error": "http error", "status": exc.code, "url": url}
            if exc.code < 500:
                break
        except (urllib.error.URLError, ConnectionError, TimeoutError) as exc:
            info = {"error": "network error", "url": url, "detail": str(exc)}
        if attempt < attempts:
            time.sleep(attempt)
    raise FetchError({**info, "attempts": attempt})


def _parse_mcp_response_body(body: str, content_type: str) -> dict[str, Any]:
    if "text/event-stream" in content_type.lower():
        last_json: dict[str, Any] | None = None
        for line in body.splitlines():
            if line.startswith("data:"):
                raw = line[5:].strip()
                if raw:
                    parsed = json.loads(raw)
                    if isinstance(parsed, dict):
                        last_json = parsed
        if last_json is not None:
            return last_json
    parsed = json.loads(body)
    if not isinstance(parsed, dict):
        raise ValueError("MCP response is not a JSON object")
    return parsed


class SiYuanClient:
    """Thin wrapper over both the SiYuan HTTP API (/api/*) and built-in MCP (/mcp).

    Writes are never retried automatically: the official API only guarantees
    idempotency where an endpoint says so.
    """

    def __init__(self, profile: dict[str, Any]):
        self.profile = profile
        self.base_url = (profile.get("base_url") or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = int(profile.get("timeout_seconds") or 30)
        self.token = profile["token"]

    def _send(self, endpoint: str, body: bytes, content_type: str, *, raise_on_error: bool = False) -> Any:
        req = urllib.request.Request(
            f"{self.base_url}{endpoint}",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Token {self.token}",
                "Content-Type": content_type,
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            },
        )
        try:
            with _open(req, self.timeout) as resp:
                response_body = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            hint = {"hint": f"Check the API token ({TOKEN_LOCATION})."} if exc.code in (401, 403) else {}
            err = {"error": "http error", "status": exc.code, "endpoint": endpoint, "body": detail, **hint}
            if raise_on_error:
                raise FetchError(err) from exc
            fail(err)
        except urllib.error.URLError as exc:
            err = {
                "error": "network error",
                "endpoint": endpoint,
                "base_url": self.base_url,
                "detail": str(exc),
                "hint": "Is SiYuan running and base_url reachable?",
            }
            if raise_on_error:
                raise FetchError(err) from exc
            fail(err)
        except (ConnectionError, TimeoutError) as exc:
            err = {"error": "network error", "endpoint": endpoint, "base_url": self.base_url, "detail": str(exc)}
            if raise_on_error:
                raise FetchError(err) from exc
            fail(err)

        try:
            data = json.loads(response_body)
        except json.JSONDecodeError:
            return {"raw": response_body}
        if isinstance(data, dict) and data.get("code", 0) != 0:
            err = {"error": "SiYuan API error", "endpoint": endpoint, "response": data}
            if raise_on_error:
                raise FetchError(err)
            fail(err)
        return data

    def post(self, endpoint: str, payload: dict[str, Any] | None = None, *, raise_on_error: bool = False) -> Any:
        endpoint = endpoint if endpoint.startswith("/") else f"/{endpoint}"
        body = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
        return self._send(endpoint, body, "application/json", raise_on_error=raise_on_error)

    def upload_assets(self, files: list[str], assets_dir: str = "/assets/") -> Any:
        boundary = uuid.uuid4().hex
        parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="assetsDirPath"\r\n\r\n{assets_dir}\r\n'.encode()]
        for filepath in files:
            p = Path(filepath).expanduser()
            if not p.is_file():
                fail({"error": "file not found", "path": str(p)})
            mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
            filename = p.name.replace('"', "%22")
            header = f'--{boundary}\r\nContent-Disposition: form-data; name="file[]"; filename="{filename}"\r\nContent-Type: {mime}\r\n\r\n'
            parts.append(header.encode() + p.read_bytes() + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        return self._send("/api/asset/upload", b"".join(parts), f"multipart/form-data; boundary={boundary}")

    # --- Built-in SiYuan MCP (/mcp Streamable HTTP) -------------------------

    def _mcp_http(
        self,
        method_http: str,
        payload: dict[str, Any] | None = None,
        session_id: str | None = None,
        timeout: float | None = None,
    ) -> tuple[str | None, str, str]:
        headers = {
            "Authorization": f"Token {self.token}",
            "Accept": "application/json, text/event-stream",
            "User-Agent": USER_AGENT,
        }
        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if session_id:
            headers["Mcp-Session-Id"] = session_id
        req = urllib.request.Request(f"{self.base_url}/mcp", data=data, headers=headers, method=method_http)
        with _open(req, timeout or self.timeout) as resp:
            sid = resp.headers.get("Mcp-Session-Id") or session_id
            ct = resp.headers.get("Content-Type") or "application/json"
            body = resp.read().decode("utf-8", errors="replace")
            return sid, ct, body

    def _mcp_request(self, method: str, params: dict[str, Any], *, raise_on_error: bool = False) -> dict[str, Any]:
        session_id: str | None = None
        try:
            session_id, ct_init, body_init = self._mcp_http(
                "POST",
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": MCP_PROTOCOL_VERSION,
                        "capabilities": {},
                        "clientInfo": {"name": SKILL_NAME, "version": __version__},
                    },
                },
            )
            init_msg = _parse_mcp_response_body(body_init, ct_init)
            if "error" in init_msg:
                raise FetchError({"error": "SiYuan MCP initialize error", "detail": init_msg["error"]})
            try:
                self._mcp_http(
                    "POST",
                    {"jsonrpc": "2.0", "method": "notifications/initialized"},
                    session_id=session_id,
                    timeout=min(self.timeout, 5),
                )
            except Exception:
                pass
            session_id, ct_call, body_call = self._mcp_http(
                "POST",
                {"jsonrpc": "2.0", "id": 2, "method": method, "params": params},
                session_id=session_id,
            )
            return _parse_mcp_response_body(body_call, ct_call)
        except FetchError as exc:
            if raise_on_error:
                raise
            fail(exc.info)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            hint: dict[str, Any] = {}
            if exc.code in (401, 403):
                hint["hint"] = f"Check the API token ({TOKEN_LOCATION})."
            elif exc.code == 404:
                hint["hint"] = "SiYuan /mcp endpoint requires SiYuan >= 3.7.0 (tested on 3.8.11+)."
            err = {"error": "http error", "status": exc.code, "endpoint": "/mcp", "body": detail, **hint}
            if raise_on_error:
                raise FetchError(err) from exc
            fail(err)
        except (urllib.error.URLError, ConnectionError, TimeoutError) as exc:
            err = {
                "error": "network error",
                "endpoint": "/mcp",
                "base_url": self.base_url,
                "detail": str(exc),
                "hint": "Is SiYuan running and base_url reachable?",
            }
            if raise_on_error:
                raise FetchError(err) from exc
            fail(err)
        except (ValueError, json.JSONDecodeError) as exc:
            err = {"error": "invalid MCP response", "endpoint": "/mcp", "detail": str(exc)}
            if raise_on_error:
                raise FetchError(err) from exc
            fail(err)
        finally:
            if session_id:
                try:
                    self._mcp_http("DELETE", None, session_id=session_id, timeout=2)
                except Exception:
                    pass

    def mcp_list_tools(self, *, raise_on_error: bool = False) -> list[dict[str, Any]]:
        msg = self._mcp_request("tools/list", {}, raise_on_error=raise_on_error)
        if "error" in msg:
            err = {"error": "SiYuan MCP error", "method": "tools/list", "detail": msg["error"]}
            if raise_on_error:
                raise FetchError(err)
            fail(err)
        tools = (msg.get("result") or {}).get("tools") or []
        return tools if isinstance(tools, list) else []

    def mcp_call(
        self,
        tool: str,
        arguments: dict[str, Any] | None = None,
        *,
        parse_json_text: bool = True,
    ) -> dict[str, Any]:
        clean_args = {k: v for k, v in (arguments or {}).items() if v is not None}
        msg = self._mcp_request("tools/call", {"name": tool, "arguments": clean_args})
        if "error" in msg:
            fail(
                {
                    "error": "SiYuan MCP error",
                    "tool": tool,
                    **({"action": clean_args["action"]} if "action" in clean_args else {}),
                    "detail": msg["error"],
                }
            )
        result = msg.get("result") or {}
        content = result.get("content") or []
        texts = [item.get("text", "") for item in content if isinstance(item, dict) and item.get("type") == "text"]
        joined = "\n".join(t for t in texts if t != "")
        if result.get("isError"):
            fail(
                {
                    "error": "SiYuan MCP tool error",
                    "tool": tool,
                    **({"action": clean_args["action"]} if "action" in clean_args else {}),
                    "detail": joined or result,
                }
            )
        if "structuredContent" in result and result["structuredContent"] is not None:
            return {"code": 0, "msg": "", "data": result["structuredContent"]}
        if parse_json_text and len(texts) == 1:
            stripped = texts[0].strip()
            if stripped.startswith(("{", "[")):
                try:
                    return {"code": 0, "msg": "", "data": json.loads(stripped)}
                except json.JSONDecodeError:
                    pass
        if not texts and content:
            return {"code": 0, "msg": "", "data": content}
        return {"code": 0, "msg": "", "data": joined}
