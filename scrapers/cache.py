"""
Simple file-based cache for scraped pages.
Saves fetched HTML to avoid re-fetching unchanged pages.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

CACHE_DIR = Path(__file__).parent.parent / "data" / "cache"
CACHE_INDEX = CACHE_DIR / "index.json"

# Cache expires after 12 hours by default
DEFAULT_TTL_HOURS = 12


def _url_to_filename(url: str) -> str:
    """Convert URL to safe filename."""
    return hashlib.md5(url.encode()).hexdigest() + ".html"


def _load_index() -> dict:
    """Load cache index."""
    if not CACHE_INDEX.exists():
        return {}
    try:
        with open(CACHE_INDEX) as f:
            return json.load(f)
    except:
        return {}


def _save_index(index: dict):
    """Save cache index."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(CACHE_INDEX, "w") as f:
        json.dump(index, f, indent=2)


def get(url: str, ttl_hours: int = DEFAULT_TTL_HOURS) -> str | None:
    """
    Get cached HTML for URL if not expired.
    Returns None if not cached or expired.
    """
    index = _load_index()

    if url not in index:
        return None

    entry = index[url]
    cached_at = datetime.fromisoformat(entry["cached_at"])

    # Check if expired
    if datetime.now(timezone.utc) - cached_at > timedelta(hours=ttl_hours):
        return None

    # Read cached file
    cache_file = CACHE_DIR / entry["filename"]
    if not cache_file.exists():
        return None

    return cache_file.read_text()


def set(url: str, html: str):
    """Cache HTML for URL."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    filename = _url_to_filename(url)
    cache_file = CACHE_DIR / filename
    cache_file.write_text(html)

    index = _load_index()
    index[url] = {
        "filename": filename,
        "cached_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_index(index)


def clear():
    """Clear all cached files."""
    if CACHE_DIR.exists():
        for f in CACHE_DIR.glob("*.html"):
            f.unlink()
        if CACHE_INDEX.exists():
            CACHE_INDEX.unlink()
    print("Cache cleared.")


def stats():
    """Print cache statistics."""
    index = _load_index()
    print(f"Cached pages: {len(index)}")

    if index:
        now = datetime.now(timezone.utc)
        oldest = min(datetime.fromisoformat(e["cached_at"]) for e in index.values())
        newest = max(datetime.fromisoformat(e["cached_at"]) for e in index.values())
        print(f"Oldest: {(now - oldest).total_seconds() / 3600:.1f} hours ago")
        print(f"Newest: {(now - newest).total_seconds() / 3600:.1f} hours ago")
