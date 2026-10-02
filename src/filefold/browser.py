"""In-browser request dispatcher (static GitHub Pages build, running under Pyodide).

The web UI talks to `/api/...` with fetch(). On the static site a small JavaScript shim
intercepts those calls and hands them to `handle()` below, which routes them to the same
`filefold.service` functions the FastAPI server uses. No web framework runs in the
browser; the route table here mirrors the FastAPI routes and a test fails if they drift.

`handle()` takes and returns plain values so it is testable in ordinary CPython.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from urllib.parse import unquote

from filefold import service
from filefold.service import ServiceError, UnsafeName


@dataclass
class Request:
    params: dict[str, str]
    json_body: dict = field(default_factory=dict)       # parsed application/json body
    fields: dict[str, str] = field(default_factory=dict)  # multipart text fields
    file_name: str = ""                                  # multipart "file" part
    file_bytes: bytes = b""
    body: bytes = b""                                    # raw body (text/plain PUT)


@dataclass
class Raw:
    """A non-JSON response body."""
    body: bytes
    content_type: str
    headers: dict[str, str] = field(default_factory=dict)


def _json_list(text: str) -> list:
    return json.loads(text) if text else []


# (method, FastAPI-style path template, handler)
ROUTES: list[tuple[str, str, callable]] = [
    ("POST", "/api/inspect", lambda r: service.inspect(r.file_name or "upload.inp", r.file_bytes)),
    ("GET", "/api/sub-options", lambda r: service.static_sub_options()),
    ("GET", "/api/workspaces", lambda r: service.list_all_workspaces()),
    ("POST", "/api/workspaces", lambda r: service.create_workspace(
        r.fields.get("name", ""), r.file_name or "upload.inp", r.file_bytes,
        _json_list(r.fields.get("selections", "")))),
    ("GET", "/api/workspaces/{name}", lambda r: service.get_workspace(r.params["name"])),
    ("PATCH", "/api/workspaces/{name}", lambda r: service.rename_workspace(r.params["name"], r.json_body.get("name", ""))),
    ("DELETE", "/api/workspaces/{name}", lambda r: service.delete_workspace(r.params["name"])),
    ("POST", "/api/workspaces/{name}/extract", lambda r: service.extract_splits(r.params["name"], r.json_body.get("selections", []))),
    ("POST", "/api/workspaces/{name}/resplit-child", lambda r: service.resplit_child(
        r.params["name"], r.json_body.get("category", ""), r.json_body.get("sub_selections", []))),
    ("POST", "/api/workspaces/{name}/rename-file", lambda r: service.rename_file(
        r.params["name"], r.json_body.get("old_filename", ""), r.json_body.get("new_filename", ""))),
    ("POST", "/api/workspaces/{name}/recombine", lambda r: service.recombine(r.params["name"], r.json_body.get("filenames", []))),
    ("POST", "/api/workspaces/{name}/reimport/preview", lambda r: service.reimport_preview(
        r.params["name"], r.file_name or "upload.inp", r.file_bytes)),
    ("POST", "/api/workspaces/{name}/reimport/apply", lambda r: service.reimport_apply(
        r.params["name"], r.file_name or "upload.inp", r.file_bytes,
        _json_list(r.fields.get("filenames", "")), _json_list(r.fields.get("added_selections", "")))),
    ("GET", "/api/workspaces/{name}/export", lambda r: Raw(
        service.export_zip(r.params["name"]), "application/zip",
        {"Content-Disposition": f'attachment; filename="{r.params["name"]}.zip"'})),
    ("GET", "/api/workspaces/{name}/files/{filename}", lambda r: Raw(
        service.read_file(r.params["name"], r.params["filename"]), "text/plain")),
    ("PUT", "/api/workspaces/{name}/files/{filename}", lambda r: service.write_file(
        r.params["name"], r.params["filename"], r.body)),
]


def _compile(template: str) -> re.Pattern:
    return re.compile("^" + re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", template) + "$")


_COMPILED = [(m, _compile(t), h) for m, t, h in ROUTES]


def route_signatures() -> set[tuple[str, str]]:
    """(method, path template) for every route; compared against FastAPI's in tests."""
    return {(m, t) for m, t, _ in ROUTES}


def handle(
    method: str,
    path: str,
    json_body: dict | None = None,
    fields: dict[str, str] | None = None,
    file_name: str = "",
    file_bytes: bytes = b"",
    body: bytes = b"",
) -> tuple[int, str, dict[str, str], bytes]:
    """Route one request. Returns (status, content_type, extra_headers, body_bytes)."""
    def as_json(status: int, payload) -> tuple[int, str, dict[str, str], bytes]:
        return status, "application/json", {}, json.dumps(payload).encode("utf-8")

    path_matched = False
    for m, pattern, handler in _COMPILED:
        hit = pattern.match(path)
        if not hit:
            continue
        path_matched = True
        if m != method.upper():
            continue
        req = Request(
            params={k: unquote(v) for k, v in hit.groupdict().items()},
            json_body=json_body or {}, fields=fields or {},
            file_name=file_name, file_bytes=file_bytes, body=body,
        )
        try:
            result = handler(req)
        except ServiceError as e:
            return as_json(e.status, {"detail": e.detail})
        except UnsafeName as e:
            return as_json(400, {"detail": str(e)})
        except (json.JSONDecodeError, KeyError) as e:
            return as_json(400, {"detail": f"Bad request: {e}"})
        if isinstance(result, Raw):
            return 200, result.content_type, result.headers, result.body
        return as_json(200, result)
    return as_json(405 if path_matched else 404, {"detail": "Method Not Allowed" if path_matched else "Not Found"})
