"""Exclude agency landing pages without excluding dated article subpages."""

from urllib.parse import urlsplit


def is_agency_homepage(link: str, homepage: str = "") -> bool:
    try:
        parsed = urlsplit(link)
        host = (parsed.hostname or "").casefold().removeprefix("www.")
        path = parsed.path.rstrip("/") or "/"
        parts = path.strip("/").split("/")
        if host == "gov.uk" and len(parts) == 3 and parts[:2] == ["government", "organisations"]:
            return True
        if homepage:
            home = urlsplit(homepage)
            return (
                bool(host)
                and host == (home.hostname or "").casefold().removeprefix("www.")
                and path == (home.path.rstrip("/") or "/")
            )
    except ValueError:
        return False
    return False
