from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from langchain_openai import ChatOpenAI

MAX_PAGE_CHARS = 20_000
MAX_LINKS = 80


def get_host(url: str) -> str:
    host = (urlparse(url).hostname or "").lower().rstrip(".")
    return host[4:] if host.startswith("www.") else host


def is_valid_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.hostname)


def _same_source(url: str, source_host: str) -> bool:
    return is_valid_url(url) and get_host(url) == source_host


def extract_json(content: str) -> str:
    content = content.strip()
    match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL)
    return match.group(1) if match else content


def create_model() -> ChatOpenAI:
    model = os.getenv("OPENAI_MODEL")
    if not model:
        raise RuntimeError("Не задана переменная OPENAI_MODEL")

    return ChatOpenAI(
        model=model,
        api_key=os.getenv("OPENAI_API_KEY", "not-required"),
        base_url=os.getenv("OPENAI_BASE_URL") or None,
        temperature=0,
        timeout=60,
        max_retries=2,
    )


async def download_page(url: str, source_host: str | None) -> dict[str, Any]:
    headers = {"User-Agent": "SourceClassifier/0.1 (+https://localhost)"}
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=15,
            headers=headers,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()

        final_url = str(response.url)
        if source_host and not _same_source(final_url, source_host):
            raise ValueError("redirected outside the source website")
        if "text/html" not in response.headers.get("content-type", ""):
            raise ValueError("response is not HTML")

        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()

        links: list[dict[str, str]] = []
        seen: set[str] = set()
        final_host = get_host(final_url)
        for anchor in soup.find_all("a", href=True):
            target = urljoin(final_url, anchor["href"]).split("#", 1)[0]
            if target in seen or not _same_source(target, final_host):
                continue
            seen.add(target)
            links.append(
                {
                    "url": target,
                    "text": " ".join(anchor.get_text(" ", strip=True).split())[:160],
                }
            )
            if len(links) == MAX_LINKS:
                break

        canonical_tag = soup.find("link", rel=lambda value: value and "canonical" in value)
        canonical_url = None
        if canonical_tag and canonical_tag.get("href"):
            candidate = urljoin(final_url, canonical_tag["href"])
            if _same_source(candidate, final_host):
                canonical_url = candidate

        description_tag = soup.find("meta", attrs={"name": "description"})
        text = " ".join(soup.get_text(" ", strip=True).split())[:MAX_PAGE_CHARS]
        return {
            "requested_url": url,
            "url": final_url,
            "available": True,
            "title": soup.title.get_text(" ", strip=True) if soup.title else "",
            "description": description_tag.get("content", "") if description_tag else "",
            "canonical_url": canonical_url,
            "text": text,
            "links": links,
        }
    except (httpx.HTTPError, ValueError) as exc:
        return {
            "requested_url": url,
            "url": url,
            "available": False,
            "error": str(exc),
            "links": [],
        }
