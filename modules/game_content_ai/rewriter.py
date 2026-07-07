import json
import os
from typing import Any, Dict

import requests

from .prompts import SYSTEM_PROMPT, build_user_prompt


OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"


def _extract_output_text(response_json: Dict[str, Any]) -> str:
    if response_json.get("output_text"):
        return response_json["output_text"]

    chunks = []
    for item in response_json.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in ("output_text", "text") and content.get("text"):
                chunks.append(content["text"])
    return "\n".join(chunks)


def _fallback_rewrite(payload: Dict[str, Any]) -> Dict[str, Any]:
    title = payload.get("title") or payload.get("name") or "Game"
    genre = payload.get("genre") or "mobile game"
    source = payload.get("source") or "official store listing"
    version = payload.get("version") or "latest available version"
    current = payload.get("description") or payload.get("current_description") or ""
    short_current = " ".join(current.split())[:220]

    return {
        "title": title,
        "meta_title": f"{title} - Gameplay, Features, and Safe Install Info",
        "meta_description": f"Read a clear overview of {title}, including gameplay, key features, version notes, and safe install guidance.",
        "intro": f"{title} is a {genre}. This draft summarizes the available listing information and avoids unverified claims.",
        "gameplay_overview": short_current or f"Use verified gameplay details for {title} here. Add concrete modes, objectives, controls, and progression only after checking the source.",
        "key_features": [
            "Clear gameplay summary based on verified source details.",
            "Version and compatibility notes can be added when available.",
            "Safety-focused install guidance for users.",
        ],
        "whats_new": f"Version: {version}. Add changelog details only when they are verified from {source}.",
        "install_safety_note": "Download only from trusted sources. Check package name, developer, version, and requested permissions before installing.",
        "faq": [
            {
                "question": f"What is {title}?",
                "answer": f"{title} is listed as a {genre}. Add more specific gameplay details after verifying the store listing or hands-on testing.",
            },
            {
                "question": f"Is {title} safe to install?",
                "answer": "Use trusted download sources, verify the package details, and avoid modified or unofficial files when safety cannot be confirmed.",
            },
        ],
        "quality_notes": [
            "Dry-run output: set OPENAI_API_KEY to generate a full rewrite.",
            "Verify gameplay modes, publisher, version, and changelog before publishing.",
            "Avoid copying APKPure or Google Play text verbatim.",
        ],
    }


def rewrite_game_content(payload: Dict[str, Any], dry_run: bool = False) -> Dict[str, Any]:
    if dry_run:
        return _fallback_rewrite(payload)

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return _fallback_rewrite(payload)

    model = os.environ.get("OPENAI_MODEL", "gpt-5.2")
    body = {
        "model": model,
        "input": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(payload)},
        ],
    }
    response = requests.post(
        OPENAI_RESPONSES_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=60,
    )
    response.raise_for_status()
    output_text = _extract_output_text(response.json()).strip()
    try:
        return json.loads(output_text)
    except json.JSONDecodeError:
        return {
            "title": payload.get("title") or payload.get("name") or "Game",
            "meta_title": "",
            "meta_description": "",
            "intro": output_text,
            "gameplay_overview": "",
            "key_features": [],
            "whats_new": "",
            "install_safety_note": "",
            "faq": [],
            "quality_notes": ["Model returned non-JSON output; inspect intro field before publishing."],
        }
