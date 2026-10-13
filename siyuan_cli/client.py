"""Config discovery, HTTP transport, and SiYuan API calls."""

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

CONFIG_TEMPLATE = {
    "active": "default",
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


def user_config_path() -> Path:
    return Path.home() / ".config" / "agent-skills" / SKILL_NAME / "config.json"


def searched_config_paths(explicit: str | None = None) -> list[Path]:
    paths: list[Path] = []
    if explicit:
        paths.append(Path(explicit).expanduser())
    paths.extend(
        [
            Path.cwd() / ".config.json",
            Path.cwd() / "skill" / ".config.json",
            user_config_path(),
        ]
    )
    unique: list[Path] = []
    for path in paths:
        if path not in unique:
            unique.append(path)
    return unique


def init_config(overwrite: bool = False) -> dict[str, Any]:
    target = user_config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not overwrite:
        return {"ok": True, "message": "config already exists", "path": str(target), "next": f"open {target}"}
    target.write_text(json.dumps(CONFIG_TEMPLATE, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "message": "created config from template", "path": str(target), "next": f"open {target}"}


def load_config(explicit: str | None, profile_override: str | None) -> tuple[Path, str, dict[str, Any]]:
    searched = searched_config_paths(explicit)
    searched_str = [str(p) for p in searched]
    repair = f"siyuan-cli init-config && open {user_config_path()}"
    for path in searched:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            fail({"error": "invalid config json", "path": str(path), "detail": str(exc), "searched": searched_str, "repair": repair})
        profiles = data.get("profiles")
        if not isinstance(profiles, dict):
            fail({"error": "config missing profiles object", "path": str(path), "searched": searched_str, "repair": repair})
        profile_name = profile_override or data.get("active") or "default"
        profile = profiles.get(profile_name)
        if not isinstance(profile, dict):
            fail({"error": "profile not found", "profile": profile_name, "path": str(path), "available_profiles": sorted(profiles)})
        base_url = profile.get("base_url") or DEFAULT_BASE_URL
        token = profile.get("token", "")
        if not isinstance(base_url, str) or not base_url.startswith(("http://", "https://")):
            fail({"error": "invalid base_url", "profile": profile_name, "path": str(path)})
        if not isinstance(token, str) or not token.strip():
            fail(
                {
                    "error": "SiYuan API token is not configured",
                    "profile": profile_name,
                    "path": str(path),
                    "searched": searched_str,
                    "repair": f"open {path}",
                    "repair_note": f"Set profiles.{profile_name}.token from {TOKEN_LOCATION}.",
                }
            )
        return path, profile_name, profile
    fail({"error": "config not found", "searched": searched_str, "repair": repair})


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


def _open(req: urllib.request.Request, timeout: float):
    """Open *req* while honoring no_proxy correctly.

    For no_proxy-matched hosts, use an empty ProxyHandler so the request goes
    direct; otherwise use the default opener (which routes via env proxies).
    """
    host = urllib.parse.urlsplit(req.full_url).hostname or ""
    if no_proxy_bypass(host):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    else:
        opener = urllib.request.build_opener()
    return opener.open(req, timeout=timeout)


class FetchError(Exception):
    def __init__(self, info: dict[str, Any]):
        super().__init__(info.get("error", "fetch error"))
        self.info = info


def fetch_text_url(url: str, timeout: float = 30, attempts: int = 3) -> str:
    """GET *url* as text, retrying transient network failures (GET is idempotent).

    Raises FetchError; callers decide whether the failure is fatal.
    """
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


class SiYuanClient:
    """Thin wrapper over the SiYuan kernel HTTP API.

    Writes are never retried automatically: the official API only guarantees
    idempotency where an endpoint says so.
    """

    def __init__(self, profile: dict[str, Any]):
        self.profile = profile
        self.base_url = (profile.get("base_url") or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = int(profile.get("timeout_seconds") or 30)
        self.token = profile["token"]

    def _send(self, endpoint: str, body: bytes, content_type: str) -> Any:
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
            fail({"error": "http error", "status": exc.code, "endpoint": endpoint, "body": detail, **hint})
        except urllib.error.URLError as exc:
            fail({"error": "network error", "endpoint": endpoint, "base_url": self.base_url, "detail": str(exc), "hint": "Is SiYuan running and base_url reachable?"})
        except (ConnectionError, TimeoutError) as exc:
            fail({"error": "network error", "endpoint": endpoint, "base_url": self.base_url, "detail": str(exc)})

        try:
            data = json.loads(response_body)
        except json.JSONDecodeError:
            return {"raw": response_body}
        if isinstance(data, dict) and data.get("code", 0) != 0:
            fail({"error": "SiYuan API error", "endpoint": endpoint, "response": data})
        return data

    def post(self, endpoint: str, payload: dict[str, Any] | None = None) -> Any:
        endpoint = endpoint if endpoint.startswith("/") else f"/{endpoint}"
        body = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
        return self._send(endpoint, body, "application/json")

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
