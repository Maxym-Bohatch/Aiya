from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus

import requests

from config import settings


def wiki_capabilities() -> dict[str, Any]:
    return {
        "enabled": settings.enable_wiki,
        "provider": "wikipedia-rest",
        "default_language": "uk",
    }


def search_wiki(query: str, language: str = "uk", limit: int = 3) -> dict[str, Any]:
    normalized_query = (query or "").strip()
    lang = (language or "uk").strip().lower()
    if not settings.enable_wiki:
        return {"ok": False, "message": "Wiki module is disabled by ENABLE_WIKI=false.", "items": []}
    if not normalized_query:
        return {"ok": False, "message": "Query is empty.", "items": []}

    search_url = f"https://{lang}.wikipedia.org/w/rest.php/v1/search/title"
    try:
        response = requests.get(search_url, params={"q": normalized_query, "limit": max(1, min(limit, 10))}, timeout=20)
        response.raise_for_status()
        pages = response.json().get("pages", [])
        items: list[dict[str, Any]] = []
        for page in pages[:limit]:
            title = page.get("title") or normalized_query
            summary_url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{quote_plus(title)}"
            summary_response = requests.get(summary_url, timeout=20)
            summary_response.raise_for_status()
            summary_data = summary_response.json()
            items.append(
                {
                    "title": summary_data.get("title") or title,
                    "description": page.get("description") or summary_data.get("description") or "",
                    "extract": summary_data.get("extract") or "",
                    "url": summary_data.get("content_urls", {}).get("desktop", {}).get("page", ""),
                    "language": lang,
                }
            )
        return {"ok": True, "items": items, "language": lang, "query": normalized_query}
    except Exception as exc:
        return {"ok": False, "message": f"Wiki request failed: {exc}", "items": [], "language": lang}
