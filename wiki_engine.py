from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus

import requests

from config import settings
import database as db

WIKIPEDIA_USER_AGENT = "Aiya/1.0 (https://github.com/Maxym-Bohatch/Aiya; contact: installer)"


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
    headers = {
        "User-Agent": WIKIPEDIA_USER_AGENT,
        "Accept": "application/json",
    }
    try:
        response = requests.get(
            search_url,
            params={"q": normalized_query, "limit": max(1, min(limit, 10))},
            headers=headers,
            timeout=20,
        )
        response.raise_for_status()
        pages = response.json().get("pages", [])
        items: list[dict[str, Any]] = []
        for page in pages[:limit]:
            title = page.get("title") or normalized_query
            page_key = page.get("key") or title.replace(" ", "_")
            summary_url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{quote_plus(page_key)}"
            summary_data: dict[str, Any] = {}
            try:
                summary_response = requests.get(summary_url, headers=headers, timeout=20)
                summary_response.raise_for_status()
                summary_data = summary_response.json()
            except requests.HTTPError:
                # Some search hits do not have a summary endpoint; keep the page-level metadata instead.
                summary_data = {}
            items.append(
                {
                    "title": summary_data.get("title") or title,
                    "description": page.get("description") or summary_data.get("description") or "",
                    "extract": summary_data.get("extract") or page.get("excerpt") or "",
                    "url": (
                        summary_data.get("content_urls", {}).get("desktop", {}).get("page", "")
                        or f"https://{lang}.wikipedia.org/wiki/{quote_plus(page_key)}"
                    ),
                    "language": lang,
                }
            )
        db.save_wiki_entries(normalized_query, lang, items)
        return {"ok": True, "items": items, "language": lang, "query": normalized_query}
    except Exception as exc:
        return {"ok": False, "message": f"Wiki request failed: {exc}", "items": [], "language": lang}


def should_use_wiki(query: str) -> bool:
    normalized = " ".join((query or "").strip().lower().split())
    if len(normalized) < 6:
        return False
    triggers = [
        "хто", "що таке", "що це", "де знаходиться", "коли", "вікі", "вікіпеді",
        "who is", "what is", "wikipedia", "tell me about",
    ]
    return any(trigger in normalized for trigger in triggers)


def get_wiki_context(query: str, language: str = "uk", limit: int = 2) -> list[str]:
    cached = db.find_wiki_context(query, language=language, limit=limit)
    if cached:
        return [f"wiki-context: {item}" for item in cached]
    if not should_use_wiki(query):
        return []
    result = search_wiki(query, language=language, limit=limit)
    if not result.get("ok"):
        return []
    context = []
    for item in result.get("items", [])[:limit]:
        line = f"{item.get('title', '')}: {(item.get('extract') or item.get('description') or '').strip()}"
        if item.get("url"):
            line += f" [{item['url']}]"
        context.append(f"wiki-context: {line}")
    return context
