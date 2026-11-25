"""Look up public GitHub repositories and branches for the hosted comparison form."""
from __future__ import annotations

from functools import lru_cache
import json
from threading import BoundedSemaphore
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import ProxyHandler, Request, build_opener

from mergerisk.hosted_auth import _NoRedirect
from mergerisk.hosted_ingest import parse_repository_url, validate_branch


_PAGE_SIZE = 50
_CACHE_SECONDS = 180
_MAX_REPLY_BYTES = 512 * 1024
_LOOKUPS = BoundedSemaphore(4)


class CatalogError(ValueError):
    """A provider error with a message safe for the comparison form."""


@lru_cache(maxsize=32)
def _fetch_page(resource: str, page: int, cache_window: int) -> tuple[list, bool]:
    query = urlencode({"per_page": _PAGE_SIZE, "page": page})
    request = Request(f"https://api.github.com/{resource}?{query}", headers={
        "Accept": "application/vnd.github+json", "User-Agent": "MergeRisk-Hosted",
    })
    if not _LOOKUPS.acquire(blocking=False):
        raise CatalogError("GitHub lookups are busy. Try again shortly.")
    try:
        opener = build_opener(ProxyHandler({}), _NoRedirect())
        with opener.open(request, timeout=5) as response:
            payload = response.read(_MAX_REPLY_BYTES + 1)
            has_more = 'rel="next"' in response.headers.get("Link", "")
        if len(payload) > _MAX_REPLY_BYTES:
            raise ValueError("GitHub response too large")
        items = json.loads(payload)
        if not isinstance(items, list) or len(items) > _PAGE_SIZE:
            raise ValueError("Unexpected GitHub catalog response")
        return items, has_more
    except HTTPError as error:
        with error:
            if error.code in {403, 429}:
                raise CatalogError("GitHub is limiting repository lookups. Try again shortly.") from error
            if error.code == 404:
                raise CatalogError("GitHub could not find that public repository or account.") from error
        raise CatalogError("GitHub lookups are temporarily unavailable.") from error
    except (URLError, OSError, ValueError) as error:
        raise CatalogError("GitHub lookups are temporarily unavailable.") from error
    finally:
        _LOOKUPS.release()


def repositories(login: str, page: int) -> dict:
    rows, has_more = _fetch_page(f"users/{quote(login, safe='')}/repos", page, int(time.monotonic() // _CACHE_SECONDS))
    items = []
    for row in rows:
        if not isinstance(row, dict) or row.get("private") is not False or not isinstance(row.get("full_name"), str):
            continue
        try:
            slug = parse_repository_url("https://github.com/" + row["full_name"])
        except ValueError:
            continue
        default_branch = row.get("default_branch")
        try:
            default_branch = validate_branch(default_branch) if isinstance(default_branch, str) else None
        except ValueError:
            default_branch = None
        items.append({"name": slug, "url": f"https://github.com/{slug}", "default_branch": default_branch})
    return {"items": items, "has_more": has_more}


def branches(slug: str, page: int) -> dict:
    rows, has_more = _fetch_page(f"repos/{slug}/branches", page, int(time.monotonic() // _CACHE_SECONDS))
    items = []
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get("name"), str):
            try:
                items.append(validate_branch(row["name"]))
            except ValueError:
                continue
    return {"items": items, "has_more": has_more}
