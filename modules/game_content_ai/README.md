# Game Content AI Module

This module improves low-value game detail pages into more helpful, original SEO content.

Dev UI:

```text
http://127.0.0.1:5000/tools/game-content-ai
```

API:

```http
POST /api/game-content/rewrite
Content-Type: application/json
```

Example payload:

```json
{
  "title": "Example Game",
  "package_name": "com.example.game",
  "genre": "RPG",
  "version": "1.2.3",
  "source": "APKPure / Google Play",
  "description": "Current low-value description text",
  "dry_run": true
}
```

Set `OPENAI_API_KEY` to call OpenAI. Without it, the module returns a deterministic dry-run draft.
