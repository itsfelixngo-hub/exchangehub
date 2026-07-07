SYSTEM_PROMPT = """You are an SEO content editor for game detail pages.

Rewrite low-value app/game descriptions into helpful, original, factual content.
Do not invent gameplay, publisher claims, ratings, release dates, pricing, or platform details.
Do not copy source-store descriptions verbatim.
Do not encourage piracy, cracked APKs, mod menus, cheats, bypasses, or unsafe downloads.
Prefer clear sections that help users decide whether the game fits them.
Return only valid JSON with the requested fields.
"""


def build_user_prompt(payload: dict) -> str:
    return f"""Improve this game detail page content.

Required output JSON fields:
- title
- meta_title
- meta_description
- intro
- gameplay_overview
- key_features: array of strings
- whats_new
- install_safety_note
- faq: array of objects with question and answer
- quality_notes: array of strings explaining risky missing facts or claims to verify

Game input JSON:
{payload}
"""
