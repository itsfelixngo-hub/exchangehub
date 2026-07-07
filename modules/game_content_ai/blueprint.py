from flask import Blueprint, jsonify, render_template_string, request

from .rewriter import rewrite_game_content


game_content_ai_bp = Blueprint("game_content_ai", __name__)


FORM_TEMPLATE = """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Game Content AI</title>
    <style>
      body { font-family: Arial, sans-serif; margin: 24px; color: #1f2933; }
      main { max-width: 980px; margin: 0 auto; }
      label { display: block; margin-top: 14px; font-weight: 700; }
      input, textarea { width: 100%; box-sizing: border-box; padding: 9px; margin-top: 4px; }
      textarea { min-height: 180px; }
      button { margin-top: 14px; padding: 9px 14px; cursor: pointer; }
      pre { white-space: pre-wrap; background: #f6f8fa; padding: 14px; border: 1px solid #d0d7de; }
    </style>
  </head>
  <body>
    <main>
      <h1>Game Content AI</h1>
      <p>Rewrite game detail content into more helpful, original, SEO-ready copy. Dry-run works without an API key.</p>
      <form id="form">
        <label>Title<input name="title" value="Example Game"></label>
        <label>Package name<input name="package_name" placeholder="com.example.game"></label>
        <label>Genre<input name="genre" placeholder="Racing, RPG, Puzzle..."></label>
        <label>Version<input name="version" placeholder="1.0.0"></label>
        <label>Source<input name="source" value="APKPure / Google Play"></label>
        <label>Current description<textarea name="description"></textarea></label>
        <label><input type="checkbox" name="dry_run" checked style="width:auto"> Dry run</label>
        <button type="submit">Rewrite</button>
      </form>
      <h2>Output</h2>
      <pre id="output">Submit the form to generate content.</pre>
    </main>
    <script>
      document.getElementById('form').addEventListener('submit', async (event) => {
        event.preventDefault();
        const form = new FormData(event.target);
        const payload = Object.fromEntries(form.entries());
        payload.dry_run = form.has('dry_run');
        const res = await fetch('/api/game-content/rewrite', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        document.getElementById('output').textContent = JSON.stringify(await res.json(), null, 2);
      });
    </script>
  </body>
</html>
"""


@game_content_ai_bp.get("/tools/game-content-ai")
def game_content_ai_form():
    return render_template_string(FORM_TEMPLATE)


@game_content_ai_bp.post("/api/game-content/rewrite")
def game_content_ai_rewrite():
    payload = request.get_json(silent=True) or {}
    dry_run = bool(payload.pop("dry_run", False))
    return jsonify(rewrite_game_content(payload, dry_run=dry_run))
