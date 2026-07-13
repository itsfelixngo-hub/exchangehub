from flask import Flask, request, jsonify, send_from_directory, render_template_string, Response, redirect, session
from werkzeug.middleware.proxy_fix import ProxyFix
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
import sqlite3
import time
import os
import json
import re
import secrets
import smtplib
import ssl
from html import escape

try:
    from .r2_storage import get_json, r2_enabled
except ImportError:
    from r2_storage import get_json, r2_enabled

DB_PATH = "rates.db"
MODULE_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(MODULE_DIR, "..", ".."))
# Directory where fetcher writes rates.json (can be set via env in docker-compose)
UPLOADS_DIR = os.environ.get("WP_UPLOADS", "wp-content/uploads")
RATES_DIR = os.path.join(UPLOADS_DIR, "rates")
RATE_CONFIG_JSON = os.environ.get("RATE_CONFIG_JSON", os.path.join(MODULE_DIR, "rate_pairs.json"))
R2_READ_CACHE_SECONDS = int(os.environ.get("R2_READ_CACHE_SECONDS", "60"))
PAGE_CACHE_SECONDS = int(os.environ.get("PAGE_CACHE_SECONDS", str(R2_READ_CACHE_SECONDS)))
_R2_PAIR_CACHE = {}
_R2_ALL_RATES_CACHE = {"ts": 0, "entries": None}
_HOME_MODEL_CACHE = {}
_HOME_PAGE_CACHE = {}
_PAIR_PAGE_CACHE = {}

app = Flask(__name__, static_folder=os.path.join(MODULE_DIR, "static"))
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or os.environ.get("SECRET_KEY") or secrets.token_hex(32)

CONTACT_EMAIL = os.environ.get("SITE_CONTACT_EMAIL", "contact@ratehubfx.com")
CONTACT_FORWARD_TO = os.environ.get("CONTACT_FORWARD_TO", "test.noreply909@gmail.com")
CONTACT_FROM_EMAIL = os.environ.get("CONTACT_FROM_EMAIL", CONTACT_EMAIL)
CONTACT_SMTP_HOST = os.environ.get("CONTACT_SMTP_HOST", "")
CONTACT_SMTP_PORT = int(os.environ.get("CONTACT_SMTP_PORT", "587"))
CONTACT_SMTP_USER = os.environ.get("CONTACT_SMTP_USER", "")
CONTACT_SMTP_PASSWORD = os.environ.get("CONTACT_SMTP_PASSWORD", "")
CONTACT_SMTP_USE_TLS = os.environ.get("CONTACT_SMTP_USE_TLS", "true").lower() not in {"0", "false", "no"}
CONTACT_SMTP_TLS_VERIFY = os.environ.get("CONTACT_SMTP_TLS_VERIFY", "true").lower() not in {"0", "false", "no"}
CONTACT_RATE_LIMIT_SECONDS = int(os.environ.get("CONTACT_RATE_LIMIT_SECONDS", "60"))
CONTACT_MIN_SUBMIT_SECONDS = int(os.environ.get("CONTACT_MIN_SUBMIT_SECONDS", "3"))
CONTACT_ROTATION_TOLERANCE = int(os.environ.get("CONTACT_ROTATION_TOLERANCE", "8"))
_CONTACT_RATE_LIMIT = {}

ROBOTS_DISALLOW_PATHS = [
    "/.env",
    "/.git",
    "/wp-login.php",
    "/wp-admin",
    "/xmlrpc.php",
    "/wp-content",
    "/wp-includes",
    "/phpmyadmin",
    "/adminer",
    "/vendor",
]

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
ROBOTS_INDEX_DIRECTIVES = "index,follow,max-snippet:-1,max-image-preview:large,max-video-preview:-1"
GOOGLE_TAG_HTML = """<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-TN7DJB48VK"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', 'G-TN7DJB48VK');
  window.exchangeTrackEvent = function(name, params) {
    if (typeof gtag === 'function') {
      gtag('event', name, params || {});
    }
  };
  document.addEventListener('DOMContentLoaded', function() {
    function areaFor(element) {
      if (element.closest('.site-header')) return 'header';
      if (element.closest('.site-footer')) return 'footer';
      if (element.closest('.quickbar')) return 'quick_converter';
      if (element.closest('.converter-panel')) return 'converter_panel';
      if (element.closest('.matrix-wrap')) return 'rate_matrix';
      if (element.closest('.mover-list')) return 'pair_movers';
      if (element.closest('.actions')) return 'top_actions';
      if (element.closest('.translate-menu')) return 'translate_menu';
      if (element.closest('.contact-form')) return 'contact_form';
      return 'page';
    }
    document.body.addEventListener('click', function(event) {
      const target = event.target.closest('a, button');
      if (!target) return;
      const href = target.getAttribute('href') || '';
      const text = (target.textContent || target.getAttribute('aria-label') || '').trim().slice(0, 80);
      const isPair = /^\/[a-z]{3}-[a-z]{3}\/?$/i.test(href);
      const isOutbound = /^https?:\/\//i.test(href) && !href.includes(location.hostname);
      const name = isPair ? 'pair_link_click' : isOutbound ? 'outbound_link_click' : 'site_click';
      window.exchangeTrackEvent(name, {
        link_text: text,
        link_url: href || location.pathname,
        link_area: areaFor(target),
        page_path: location.pathname
      });
    }, { passive: true });
    document.body.addEventListener('change', function(event) {
      const target = event.target;
      if (!target || !target.matches('select, input[type="range"]')) return;
      window.exchangeTrackEvent('control_change', {
        control_id: target.id || target.name || 'unknown',
        control_value: String(target.value || '').slice(0, 80),
        link_area: areaFor(target),
        page_path: location.pathname
      });
    }, { passive: true });
    if ('IntersectionObserver' in window) {
      const seenSections = new WeakSet();
      const observer = new IntersectionObserver(function(entries) {
        entries.forEach(function(entry) {
          if (!entry.isIntersecting || seenSections.has(entry.target)) return;
          seenSections.add(entry.target);
          const heading = entry.target.querySelector('h1, h2, h3');
          window.exchangeTrackEvent('section_view', {
            section_title: (heading ? heading.textContent : entry.target.id || 'section').trim().slice(0, 100),
            section_id: entry.target.id || '',
            page_path: location.pathname
          });
        });
      }, { threshold: 0.45 });
      document.querySelectorAll('main section, main header, .info-content').forEach(function(section) {
        observer.observe(section);
      });
    }
    const scrollMarks = [25, 50, 75, 90];
    const sentScrollMarks = new Set();
    window.addEventListener('scroll', function() {
      const doc = document.documentElement;
      const scrollable = Math.max(1, doc.scrollHeight - window.innerHeight);
      const percent = Math.round((window.scrollY / scrollable) * 100);
      scrollMarks.forEach(function(mark) {
        if (percent >= mark && !sentScrollMarks.has(mark)) {
          sentScrollMarks.add(mark);
          window.exchangeTrackEvent('scroll_depth', {
            percent_scrolled: mark,
            page_path: location.pathname
          });
        }
      });
    }, { passive: true });
  });
</script>"""


@app.after_request
def add_robots_header(response):
    if response.status_code == 200 and response.mimetype == "text/html":
        response.headers["X-Robots-Tag"] = ROBOTS_INDEX_DIRECTIVES
    return response


def get_client_ip():
    return request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()


def new_contact_challenge():
    rotation = (secrets.randbelow(23) + 1) * 15
    session["contact_rotation_start"] = rotation
    session["contact_rotation_answer"] = (360 - rotation) % 360
    session["contact_form_token"] = secrets.token_urlsafe(24)
    session["contact_form_started_at"] = time.time()
    return rotation, session["contact_form_token"]


def prepare_contact_form():
    return new_contact_challenge()


def angular_distance(left, right):
    return abs((left - right + 180) % 360 - 180)


def contact_rate_limited(ip):
    now = time.time()
    last_submit = _CONTACT_RATE_LIMIT.get(ip, 0)
    return now - last_submit < CONTACT_RATE_LIMIT_SECONDS


def mark_contact_submitted(ip):
    _CONTACT_RATE_LIMIT[ip] = time.time()


def validate_contact_submission(form):
    errors = []
    name = form.get("name", "").strip()
    email = form.get("email", "").strip()
    subject = form.get("subject", "").strip()
    message = form.get("message", "").strip()
    rotation_response = form.get("rotation_response", "").strip()
    token = form.get("form_token", "").strip()
    website = form.get("website", "").strip()

    if website:
        errors.append("Spam check failed.")
    if not secrets.compare_digest(token, session.get("contact_form_token", "")):
        errors.append("The form expired. Please try again.")
    if time.time() - float(session.get("contact_form_started_at", 0)) < CONTACT_MIN_SUBMIT_SECONDS:
        errors.append("Please take a moment before submitting the form.")
    try:
        rotation_value = int(float(rotation_response))
    except (TypeError, ValueError):
        rotation_value = None
    if rotation_value is None or angular_distance(rotation_value, int(session.get("contact_rotation_answer", -999))) > CONTACT_ROTATION_TOLERANCE:
        errors.append("The rotation check is incorrect.")
    if len(name) < 2 or len(name) > 80:
        errors.append("Name must be between 2 and 80 characters.")
    if not EMAIL_RE.match(email) or len(email) > 120:
        errors.append("Enter a valid email address.")
    if len(subject) < 3 or len(subject) > 140:
        errors.append("Subject must be between 3 and 140 characters.")
    if len(message) < 20 or len(message) > 4000:
        errors.append("Message must be between 20 and 4000 characters.")

    clean = {"name": name, "email": email, "subject": subject, "message": message}
    return errors, clean


def send_contact_email(data):
    if not CONTACT_SMTP_HOST:
        raise RuntimeError("CONTACT_SMTP_HOST is not configured")

    msg = EmailMessage()
    msg["Subject"] = f"ExchangeHub contact: {data['subject']}"
    msg["From"] = CONTACT_FROM_EMAIL
    msg["To"] = CONTACT_FORWARD_TO
    msg["Reply-To"] = data["email"]
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=CONTACT_FROM_EMAIL.split("@")[-1])
    msg.set_content(
        "\n".join(
            [
                "New ExchangeHub contact form submission",
                "",
                f"Name: {data['name']}",
                f"Email: {data['email']}",
                f"IP: {get_client_ip()}",
                f"Page: {request.url}",
                "",
                data["message"],
            ]
        )
    )

    with smtplib.SMTP(CONTACT_SMTP_HOST, CONTACT_SMTP_PORT, timeout=15) as smtp:
        if CONTACT_SMTP_USE_TLS:
            tls_context = ssl.create_default_context() if CONTACT_SMTP_TLS_VERIFY else ssl._create_unverified_context()
            smtp.starttls(context=tls_context)
        if CONTACT_SMTP_USER or CONTACT_SMTP_PASSWORD:
            smtp.login(CONTACT_SMTP_USER, CONTACT_SMTP_PASSWORD)
        smtp.send_message(msg)


BRAND_LOGO_HTML = """
<span class="brand-lockup" aria-label="ExchangeHub">
  <svg class="brand-mark" viewBox="0 0 40 40" role="img" aria-hidden="true" focusable="false">
    <rect x="2" y="2" width="36" height="36" rx="10" fill="#111827"/>
    <circle cx="20" cy="20" r="4.2" fill="#f0b90b"/>
    <circle cx="20" cy="8.5" r="3.2" fill="#f0b90b"/>
    <circle cx="31.5" cy="20" r="3.2" fill="#f0b90b"/>
    <circle cx="20" cy="31.5" r="3.2" fill="#f0b90b"/>
    <circle cx="8.5" cy="20" r="3.2" fill="#f0b90b"/>
    <path d="M14.2 15.2h9.4l-2.4-2.4 2-2 5.9 5.9-5.9 5.9-2-2 2.4-2.4h-9.4z" fill="#22c55e"/>
    <path d="M25.8 24.8h-9.4l2.4 2.4-2 2-5.9-5.9 5.9-5.9 2 2-2.4 2.4h9.4z" fill="#38bdf8"/>
  </svg>
  <span class="brand-name">ExchangeHub</span>
</span>
"""

try:
    from modules.game_content_ai import game_content_ai_bp

    app.register_blueprint(game_content_ai_bp)
except Exception:
    pass


def get_db_conn():
    conn = sqlite3.connect(DB_PATH)
    return conn


def ensure_db():
    if not os.path.exists(DB_PATH):
        conn = get_db_conn()
        conn.execute(
            "CREATE TABLE IF NOT EXISTS rates (id INTEGER PRIMARY KEY, ts INTEGER, base TEXT, target TEXT, rate REAL)"
        )
        conn.commit()
        conn.close()


def pair_key(base: str, target: str):
    return f"{base.lower()}_{target.lower()}"


def pair_url(base: str, target: str):
    return f"/{base.lower()}-{target.lower()}"


def pair_json_path(base: str, target: str):
    return os.path.join(RATES_DIR, f"{pair_key(base, target)}.json")


def r2_cache_fresh(ts: float) -> bool:
    return bool(ts and time.time() - ts < R2_READ_CACHE_SECONDS)


def page_cache_fresh(ts: float) -> bool:
    return bool(ts and time.time() - ts < PAGE_CACHE_SECONDS)


def load_pair_entries(base: str, target: str):
    if r2_enabled():
        cache_key = pair_key(base, target)
        cached = _R2_PAIR_CACHE.get(cache_key)
        if cached and r2_cache_fresh(cached["ts"]):
            return cached["entries"]

        try:
            entries = get_json(f"rates/{pair_key(base, target)}.json")
            if isinstance(entries, list):
                _R2_PAIR_CACHE[cache_key] = {"ts": time.time(), "entries": entries}
                return entries
        except Exception:
            pass

    path = pair_json_path(base, target)
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_json_rates():
    if r2_enabled():
        if _R2_ALL_RATES_CACHE["entries"] is not None and r2_cache_fresh(_R2_ALL_RATES_CACHE["ts"]):
            return _R2_ALL_RATES_CACHE["entries"]

        entries = []
        try:
            index = get_json("rates/index.json")
            for pair in (index or {}).get("pairs", []):
                filename = os.path.basename(str(pair.get("file", "")))
                if not filename:
                    continue
                data = get_json(f"rates/{filename}")
                if isinstance(data, list):
                    entries.extend(data)
            if entries:
                _R2_ALL_RATES_CACHE["ts"] = time.time()
                _R2_ALL_RATES_CACHE["entries"] = entries
                return entries
        except Exception:
            pass

    if not os.path.isdir(RATES_DIR):
        return []
    entries = []
    for name in os.listdir(RATES_DIR):
        if not name.endswith(".json") or name == "index.json":
            continue
        try:
            with open(os.path.join(RATES_DIR, name), "r", encoding="utf-8") as f:
                entries.extend(json.load(f))
        except Exception:
            pass
    return entries


def parse_pair_key(pair: str):
    parts = str(pair).replace("-", "_").upper().split("_")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(f"Invalid pair {pair!r}; expected BASE_TARGET, e.g. vnd_usd")
    return parts[0], parts[1]


def normalize_pairs(pairs):
    out = []
    for pair in pairs:
        parsed = parse_pair_key(pair) if isinstance(pair, str) else (str(pair[0]).upper(), str(pair[1]).upper())
        if parsed[0] != parsed[1] and parsed not in out:
            out.append(parsed)
    return out


def load_rate_config():
    with open(RATE_CONFIG_JSON, "r", encoding="utf-8") as f:
        config = json.load(f)
    if isinstance(config, list):
        return normalize_pairs(config)
    if "pairs" in config:
        return normalize_pairs(config.get("pairs", []))
    base = str(config.get("base", "USD")).upper()
    return [(base, str(target).upper()) for target in config.get("targets", []) if str(target).upper() != base]


def config_currencies():
    currencies = []
    for base, target in load_rate_config():
        if base not in currencies:
            currencies.append(base)
        if target not in currencies:
            currencies.append(target)
    if "USD" in currencies:
        currencies.remove("USD")
        currencies.insert(0, "USD")
    return currencies


def usd_rate_for(table: dict, currency: str):
    if currency == "USD":
        return 1.0
    return table.get(currency)


def add_entry_to_usd_table(table: dict, entry: dict):
    base = entry.get("base")
    target = entry.get("target")
    rate = entry.get("rate")
    if not rate:
        return
    if base == "USD":
        table[target] = float(rate)
    elif target == "USD":
        table[base] = 1.0 / float(rate)


def derive_rate_from_usd_table(base: str, target: str, table: dict):
    base_per_usd = usd_rate_for(table, base)
    target_per_usd = usd_rate_for(table, target)
    if not base_per_usd or not target_per_usd:
        return None
    return float(target_per_usd) / float(base_per_usd)


def derive_latest_from_entries(entries, base: str, target: str):
    by_ts = {}
    for entry in entries:
        add_entry_to_usd_table(by_ts.setdefault(entry.get("ts", 0), {}), entry)

    for ts in sorted(by_ts.keys(), reverse=True):
        rate = derive_rate_from_usd_table(base, target, by_ts[ts])
        if rate is not None:
            return {"ts": ts, "rate": rate, "base": base, "target": target}
    return None


def derive_history_from_entries(entries, base: str, target: str, since=None):
    by_ts = {}
    for entry in entries:
        ts = entry.get("ts", 0)
        if since is not None and ts < since:
            continue
        add_entry_to_usd_table(by_ts.setdefault(ts, {}), entry)

    data = []
    for ts in sorted(by_ts.keys()):
        rate = derive_rate_from_usd_table(base, target, by_ts[ts])
        if rate is not None:
            data.append({"ts": ts, "rate": rate})
    return data


def format_rate(value):
    value = float(value)
    abs_value = abs(value)
    if value == 0:
        return "0"
    if abs_value < 0.000001:
        return f"{value:.6E}"
    if abs_value < 1:
        return f"{value:.8f}".rstrip("0").rstrip(".")
    if abs_value < 1000:
        return f"{value:.6f}".rstrip("0").rstrip(".")
    return f"{value:,.2f}"


def format_amount(value):
    value = float(value)
    if abs(value) >= 1000:
        return f"{value:,.2f}"
    return format_rate(value)


CURRENCY_PROFILES = {
    "USD": {"name": "US dollar", "region": "United States", "role": "global reserve and settlement currency", "use": "international pricing, cards, transfers, and dollar-linked invoices"},
    "EUR": {"name": "euro", "region": "Euro Area", "role": "major European currency", "use": "European travel, trade, tuition, and cross-border payments"},
    "JPY": {"name": "Japanese yen", "region": "Japan", "role": "major Asian safe-haven currency", "use": "Japan travel, business expenses, tuition, and import pricing"},
    "GBP": {"name": "British pound", "region": "United Kingdom", "role": "major sterling currency", "use": "UK travel, education, invoices, and portfolio comparison"},
    "CNY": {"name": "Chinese yuan", "region": "China", "role": "major Asian trade currency", "use": "China trade, sourcing, ecommerce costs, and regional currency comparison"},
    "VND": {"name": "Vietnamese dong", "region": "Vietnam", "role": "local Vietnamese currency", "use": "Vietnam travel, salary conversion, remittance checks, and local price comparison"},
    "KRW": {"name": "South Korean won", "region": "South Korea", "role": "North Asian currency", "use": "Korea travel, electronics trade, tuition, and regional comparisons"},
    "THB": {"name": "Thai baht", "region": "Thailand", "role": "Southeast Asian currency", "use": "Thailand travel, tourism spending, and regional price checks"},
    "SGD": {"name": "Singapore dollar", "region": "Singapore", "role": "regional financial hub currency", "use": "Singapore travel, business settlement, and Southeast Asia comparisons"},
    "AUD": {"name": "Australian dollar", "region": "Australia", "role": "commodity-linked major currency", "use": "Australia travel, study, trade, and commodity-sensitive comparisons"},
    "CAD": {"name": "Canadian dollar", "region": "Canada", "role": "commodity-linked North American currency", "use": "Canada travel, invoices, study, and oil-sensitive currency checks"},
    "CHF": {"name": "Swiss franc", "region": "Switzerland", "role": "traditional safe-haven currency", "use": "Swiss travel, wealth references, and defensive currency comparison"},
    "HKD": {"name": "Hong Kong dollar", "region": "Hong Kong", "role": "USD-linked financial-market currency", "use": "Hong Kong travel, business costs, and USD-linked rate checks"},
    "INR": {"name": "Indian rupee", "region": "India", "role": "large emerging-market currency", "use": "India travel, outsourcing costs, remittances, and trade comparison"},
    "IDR": {"name": "Indonesian rupiah", "region": "Indonesia", "role": "Southeast Asian currency with large nominal values", "use": "Indonesia travel, ecommerce, tourism, and local price conversion"},
    "MYR": {"name": "Malaysian ringgit", "region": "Malaysia", "role": "Southeast Asian currency", "use": "Malaysia travel, trade, education, and regional price comparison"},
    "PHP": {"name": "Philippine peso", "region": "Philippines", "role": "Southeast Asian remittance currency", "use": "Philippines travel, remittances, salaries, and local price checks"},
    "TWD": {"name": "Taiwan dollar", "region": "Taiwan", "role": "North Asian technology-sector currency", "use": "Taiwan travel, electronics supply-chain costs, and regional comparisons"},
    "NZD": {"name": "New Zealand dollar", "region": "New Zealand", "role": "commodity-linked Pacific currency", "use": "New Zealand travel, study, agriculture-linked pricing, and portfolio comparison"},
}


def currency_profile(code):
    return CURRENCY_PROFILES.get(code, {"name": code, "region": code, "role": "currency", "use": "currency conversion and comparison"})


def pair_amounts(base: str):
    high_nominal = {"VND", "IDR", "KRW"}
    medium_nominal = {"JPY", "PHP", "TWD", "THB", "INR"}
    if base in high_nominal:
        return [1000, 5000, 10000, 50000, 100000, 500000, 1000000, 5000000, 10000000, 50000000]
    if base in medium_nominal:
        return [100, 500, 1000, 5000, 10000, 25000, 50000, 100000, 500000, 1000000]
    return [1, 5, 10, 25, 50, 100, 500, 1000, 5000, 10000]


def trend_phrase(stats):
    if not stats:
        return "does not have enough stored history yet to describe a clear trend"
    if stats["direction"] == "up":
        return "has moved higher across the stored data window"
    if stats["direction"] == "down":
        return "has moved lower across the stored data window"
    return "has stayed inside a narrow range across the stored data window"


def rate_scale_note(rate, base, target):
    if rate is None:
        return "As more update points are collected, this page will become more useful for comparing direction, range, and short-term changes."
    if abs(rate) < 0.01:
        return f"Because 1 {base} is worth a small decimal amount of {target}, the reverse rate and percentage change are often easier to read than the raw forward quote."
    if abs(rate) >= 1000:
        return f"Because 1 {base} converts into a large nominal amount of {target}, small percentage moves can still appear as several units on the chart."
    return f"The {base}/{target} quote is readable on a normal scale, so the chart, high-low range, and average rate can be compared directly."


def build_pair_content(model, rate, reverse_rate):
    base = model["base"]
    target = model["target"]
    stats = model["stats"]
    base_profile = currency_profile(base)
    target_profile = currency_profile(target)
    latest_label = format_rate(rate) if rate is not None else "not available"
    reverse_label = format_rate(reverse_rate) if reverse_rate is not None else "not available"
    range_pct = 0
    if stats and stats["average"]:
        range_pct = (stats["high"] - stats["low"]) / stats["average"] * 100

    if target == "VND":
        intent = f"This page is useful for reading how {base_profile['name']} values translate into Vietnamese dong amounts for Vietnam travel, transfers, invoices, and local price comparison."
    elif base == "VND":
        intent = f"This page helps read Vietnamese dong values in {target_profile['name']}, which is useful when local VND prices need to be compared with foreign budgets or savings."
    elif base == "USD":
        intent = f"Because USD is a {base_profile['role']}, this pair is often used as a benchmark for checking how {target_profile['name']} is moving against dollar-based pricing."
    elif target == "USD":
        intent = f"Quoting {base} against USD makes the move easier to compare with global dollar strength, overseas costs, and USD-denominated references."
    else:
        intent = f"This cross-rate connects {base_profile['region']} and {target_profile['region']} without forcing the reader to manually convert through USD."

    summary = (
        f"{base}/{target} {trend_phrase(stats)}. "
        + (f"The observed range is about {range_pct:.4f}% between the stored high and low, across {stats['points']} stored update points." if stats else "The stored sample is still building.")
    )
    context_cards = [
        {
            "title": f"Why {base}/{target} matters",
            "body": f"{base} is the {base_profile['name']}, a {base_profile['role']}. {target} is the {target_profile['name']}. {intent}",
        },
        {
            "title": "How to read the quote",
            "body": f"The quote means 1 {base} equals {latest_label} {target}. A rising chart means {base} buys more {target}; a falling chart means it buys less. {rate_scale_note(rate, base, target)}",
        },
        {
            "title": "Reverse-rate context",
            "body": f"The reverse view is 1 {target} = {reverse_label} {base}. This is especially useful when the forward pair is very large or very small, because the inverse quote may match how users mentally compare prices.",
        },
        {
            "title": "Practical use cases",
            "body": f"Readers commonly use this pair for {base_profile['use']} against {target_profile['use']}. The table gives practical amounts, while the chart and stats show whether the current quote is near the recent high, low, or average.",
        },
    ]

    faqs = [
        {
            "question": f"What is the {base} to {target} exchange rate today?",
            "answer": f"The latest stored rate is 1 {base} = {latest_label} {target}." if rate is not None else "The latest stored rate is not available yet.",
        },
        {
            "question": f"Is {base} stronger or weaker against {target}?",
            "answer": (
                f"Across the current stored window, {base} is "
                f"{'stronger' if stats and stats['direction'] == 'up' else 'weaker' if stats and stats['direction'] == 'down' else 'mostly stable'} "
                f"against {target}, based on a {stats['change_pct']:.4f}% move and a {range_pct:.4f}% high-low range."
            ) if stats else "There is not enough stored history yet to describe the trend.",
        },
        {
            "question": f"When is the {base}/{target} rate useful?",
            "answer": intent,
        },
        {
            "question": f"Why compare {target} to {base} as the reverse rate?",
            "answer": f"The reverse rate, currently 1 {target} = {reverse_label} {base}, can be easier to understand when the forward quote is a very large number or a very small decimal.",
        },
        {
            "question": "Can I use this rate for money transfers?",
            "answer": "This page is for informational comparison only. Banks, brokers, card networks, and transfer providers may apply their own spreads, fees, settlement timing, and rounding.",
        },
    ]
    return {
        "base_name": base_profile["name"],
        "target_name": target_profile["name"],
        "summary": summary,
        "context_cards": context_cards,
        "faqs": faqs,
        "range_pct": range_pct,
    }


def pair_history(base: str, target: str):
    base = base.upper()
    target = target.upper()
    if base == target:
        return [{"ts": int(time.time()), "base": base, "target": target, "rate": 1.0}]

    direct = load_pair_entries(base, target)
    if direct:
        return direct
    return derive_history_from_entries(load_json_rates(), base, target)


def build_pair_model(base: str, target: str):
    base = base.upper()
    target = target.upper()
    history = pair_history(base, target)
    latest = history[-1] if history else None
    rates = [float(entry["rate"]) for entry in history if entry.get("rate") is not None]
    stats = None
    if rates:
        first = rates[0]
        previous = rates[-2] if len(rates) > 1 else rates[0]
        latest_rate = rates[-1]
        change = latest_rate - first
        change_pct = (change / first * 100) if first else 0
        previous_change = latest_rate - previous
        previous_change_pct = (previous_change / previous * 100) if previous else 0
        direction = "up" if change_pct > 0.01 else "down" if change_pct < -0.01 else "flat"
        stats = {
            "points": len(rates),
            "high": max(rates),
            "low": min(rates),
            "average": sum(rates) / len(rates),
            "updated": latest["ts"] if latest else None,
            "first": first,
            "change": change,
            "change_pct": change_pct,
            "previous_change": previous_change,
            "previous_change_pct": previous_change_pct,
            "direction": direction,
        }
    return {
        "base": base,
        "target": target,
        "history": history,
        "latest": latest,
        "stats": stats,
        "amounts": pair_amounts(base),
        "reverse_rate": (1 / rates[-1]) if rates and rates[-1] else None,
    }


def render_pair_page(model):
    base = model["base"]
    target = model["target"]
    latest = model["latest"]
    rate = float(latest["rate"]) if latest else None
    reverse_rate = model["reverse_rate"]
    content = build_pair_content(model, rate, reverse_rate)
    updated = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(int(latest["ts"]))) if latest else ""
    title = f"{base} to {target} Exchange Rate Today"
    description = (
        f"{base} to {target} exchange rate today with converter, chart, statistics, trend notes, and practical {base}/{target} context."
        + (f" Latest: 1 {base} = {format_rate(rate)} {target}." if rate is not None else "")
    )
    canonical_url = absolute_url(pair_url(base, target))
    logo_url = absolute_url("/static/exchangehub-logo.svg")
    menu = build_menu_model(base, target)
    nav_links = [
        {
            "@type": "SiteNavigationElement",
            "name": link["label"],
            "url": absolute_url(link["href"]),
        }
        for group in menu["groups"]
        for link in group["links"]
    ][:36]
    schema = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Organization",
                "@id": f"{site_base_url()}/#organization",
                "name": "ExchangeHub",
                "url": site_base_url(),
                "logo": {"@type": "ImageObject", "url": logo_url},
            },
            {
                "@type": "WebSite",
                "@id": f"{site_base_url()}/#website",
                "name": "ExchangeHub",
                "url": site_base_url(),
                "publisher": {"@id": f"{site_base_url()}/#organization"},
                "inLanguage": "en",
            },
            {
                "@type": "WebPage",
                "@id": f"{canonical_url}#webpage",
                "url": canonical_url,
                "name": title,
                "description": description,
                "isPartOf": {"@id": f"{site_base_url()}/#website"},
                "about": [
                    {"@type": "Thing", "name": f"{base}/{target} exchange rate"},
                    {"@type": "Thing", "name": f"{content['base_name']} to {content['target_name']}"},
                ],
                "dateModified": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(latest["ts"]))) if latest else None,
                "breadcrumb": {"@id": f"{canonical_url}#breadcrumb"},
                "publisher": {"@id": f"{site_base_url()}/#organization"},
                "inLanguage": "en",
            },
            {
                "@type": "BreadcrumbList",
                "@id": f"{canonical_url}#breadcrumb",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Exchange Rates", "item": site_base_url()},
                    {"@type": "ListItem", "position": 2, "name": f"{base} pairs", "item": canonical_url},
                    {"@type": "ListItem", "position": 3, "name": f"{base} to {target}"},
                ],
            },
            *nav_links,
            {
                "@type": "FAQPage",
                "@id": f"{canonical_url}#faq",
                "mainEntity": [
                    {
                        "@type": "Question",
                        "name": item["question"],
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": item["answer"],
                        },
                    }
                    for item in content["faqs"]
                ],
            },
        ],
    }
    rows = []
    for amount in model["amounts"]:
        converted = "-" if rate is None else f"{format_amount(amount * rate)} {target}"
        rows.append((f"{amount:,} {base}", converted))
    reverse_rows = []
    for amount in model["amounts"]:
        converted = "-" if reverse_rate is None else f"{format_amount(amount * reverse_rate)} {base}"
        reverse_rows.append((f"{amount:,} {target}", converted))
    history_json = json.dumps(model["history"])
    schema_json = json.dumps(schema)

    return render_template_string(
        PAIR_PAGE_TEMPLATE,
        title=title,
        description=description,
        canonical_url=canonical_url,
        base=base,
        target=target,
        menu=menu,
        footer_html=render_footer_html(menu),
        rate=None if rate is None else format_rate(rate),
        updated=updated,
        rows=rows,
        reverse_rows=reverse_rows,
        pair_movers=build_pair_movers(base_filter=base),
        stats=model["stats"],
        content=content,
        reverse_rate=None if reverse_rate is None else format_rate(reverse_rate),
        format_rate=format_rate,
        history_json=history_json,
        schema_json=schema_json,
        brand_html=BRAND_LOGO_HTML,
        google_tag_html=GOOGLE_TAG_HTML,
    )


def render_cached_pair_page(base: str, target: str):
    base = base.upper()
    target = target.upper()
    cache_key = (site_base_url(), base, target)
    cached = _PAIR_PAGE_CACHE.get(cache_key)
    if cached and page_cache_fresh(cached["ts"]):
        return cached["html"]

    html = render_pair_page(build_pair_model(base, target))
    _PAIR_PAGE_CACHE[cache_key] = {"ts": time.time(), "html": html}
    return html


MAJOR_COLUMNS = ["USD", "EUR", "JPY", "GBP", "CNY", "VND"]
HOME_ROWS = ["USD", "EUR", "JPY", "GBP", "CNY", "KRW", "SGD", "THB", "VND", "AUD", "CAD", "CHF", "HKD", "INR", "IDR", "MYR", "PHP", "TWD", "NZD"]
HOME_CHART_BASES = ["USD", "EUR", "JPY", "GBP", "CNY", "VND"]
CONVERTER_TARGETS = ["VND", "USD", "EUR", "JPY", "GBP", "CNY", "KRW", "THB", "SGD", "AUD", "CAD", "CHF", "HKD", "INR", "IDR", "MYR", "PHP", "TWD", "NZD"]
MENU_GROUPS = {
    "USD": ["VND", "EUR", "JPY", "GBP", "CNY", "KRW", "THB", "SGD"],
    "EUR": ["USD", "VND", "GBP", "JPY", "CHF", "CNY"],
    "JPY": ["USD", "VND", "EUR", "KRW", "CNY", "THB"],
    "GBP": ["USD", "EUR", "VND", "JPY", "AUD", "CAD"],
    "CNY": ["USD", "VND", "JPY", "EUR", "KRW", "THB"],
    "VND": ["USD", "EUR", "JPY", "KRW", "THB", "CNY"],
}


def build_latest_usd_table():
    latest_by_currency = {"USD": 1.0}
    latest_ts_by_currency = {"USD": 0}
    latest_ts = None
    for entry in load_json_rates():
        ts = int(entry.get("ts", 0))
        table = {}
        add_entry_to_usd_table(table, entry)
        for currency, rate in table.items():
            if ts >= latest_ts_by_currency.get(currency, 0):
                latest_by_currency[currency] = rate
                latest_ts_by_currency[currency] = ts
        latest_ts = max(latest_ts or 0, ts)
    return latest_by_currency, latest_ts


def build_home_matrix():
    table, latest_ts = build_latest_usd_table()
    rows = []
    for base in HOME_ROWS:
        cells = []
        for target in MAJOR_COLUMNS:
            rate = derive_rate_from_usd_table(base, target, table)
            href = pair_url(base, target)
            cells.append({"target": target, "value": None if rate is None else format_rate(rate), "href": href})
        rows.append({"base": base, "cells": cells})
    return rows, latest_ts


def build_pair_movers(limit=6, base_filter=None):
    base_filter = base_filter.upper() if base_filter else None
    seen = set()
    movers = []
    for base, targets in MENU_GROUPS.items():
        if base_filter and base != base_filter:
            continue
        for target in targets:
            if base == target or (base, target) in seen:
                continue
            seen.add((base, target))
            history = pair_history(base, target)
            rates = [float(entry["rate"]) for entry in history if entry.get("rate") is not None]
            if not rates:
                continue
            first = rates[0]
            latest = rates[-1]
            change_pct = ((latest - first) / first * 100) if first else 0
            direction = "up" if change_pct > 0.01 else "down" if change_pct < -0.01 else "flat"
            movers.append({
                "label": f"{base}/{target}",
                "href": pair_url(base, target),
                "rate": format_rate(latest),
                "change_pct": change_pct,
                "change_label": f"{change_pct:+.4f}%",
                "direction": direction,
            })
    gainers = sorted([item for item in movers if item["direction"] == "up"], key=lambda x: x["change_pct"], reverse=True)[:limit]
    losers = sorted([item for item in movers if item["direction"] == "down"], key=lambda x: x["change_pct"])[:limit]
    flat = sorted([item for item in movers if item["direction"] == "flat"], key=lambda x: abs(x["change_pct"]))[:limit]
    return {"up": gainers, "down": losers, "flat": flat}


def build_home_pair_movers(limit=6):
    return build_pair_movers(limit=limit)


def normalized_history(base, quote):
    history = pair_history(base, quote)
    points = []
    first = None
    for entry in history:
        rate = float(entry["rate"])
        if first is None:
            first = rate
        if first:
            points.append({"ts": entry["ts"], "value": rate / first * 100})
    return points


def build_home_chart_series(base, quote):
    base = base.upper()
    quote = quote.upper()
    if base == quote or base not in config_currencies() or quote not in config_currencies():
        return None
    return {"label": f"{base} to {quote}", "data": normalized_history(base, quote)}


def chart_description_for_quote(quote):
    return (
        f"<p>This chart compares major currencies against <strong>{quote}</strong> using a base-100 index. "
        f"Every line starts at <strong>100</strong> at the first available point, so the chart measures relative percentage movement instead of raw exchange-rate size.</p>"
        f"<p>Example: if <strong>EUR to {quote}</strong> moves from 100 to 102, EUR has strengthened by about 2% against {quote}. "
        f"If <strong>VND to {quote}</strong> moves from 100 to 98, VND has weakened by about 2% against {quote}. "
        f"A line staying close to 100 means the currency has been mostly flat versus {quote} in the selected data window.</p>"
        f"<p>This normalization is useful because raw rates use very different scales, for example 1 USD can equal tens of thousands of VND but less than 1 EUR. "
        f"Indexing every line to 100 lets you compare which currency is moving faster or slower on the same chart.</p>"
    )


def build_home_model(quote="USD", include_series=True):
    quote = quote.upper()
    if quote not in config_currencies():
        quote = "USD"
    matrix, latest_ts = build_home_matrix()
    latest_table, _ = build_latest_usd_table()
    series = []
    if include_series:
        series = [
            {"label": f"{base} to {quote}", "data": normalized_history(base, quote)}
            for base in HOME_CHART_BASES
            if base != quote
        ]
    return {
        "columns": MAJOR_COLUMNS,
        "quote": quote,
        "quote_options": MAJOR_COLUMNS,
        "chart_bases": HOME_CHART_BASES,
        "converter_bases": MAJOR_COLUMNS,
        "converter_targets": CONVERTER_TARGETS,
        "latest_usd_table": latest_table,
        "rows": matrix,
        "pair_movers": build_home_pair_movers(),
        "series": series,
        "chart_description": chart_description_for_quote(quote),
        "updated": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(latest_ts)) if latest_ts else "",
    }


def cached_home_model(quote="USD", include_series=True):
    key = (str(quote or "USD").upper(), bool(include_series))
    cached = _HOME_MODEL_CACHE.get(key)
    if cached and page_cache_fresh(cached["ts"]):
        return cached["model"]

    model = build_home_model(key[0], include_series=include_series)
    _HOME_MODEL_CACHE[key] = {"ts": time.time(), "model": model}
    return model


def build_menu_model(active_base=None, active_target=None):
    active_base = active_base.upper() if active_base else None
    groups = []
    seen = set()
    for base, targets in MENU_GROUPS.items():
        links = []
        for target in targets:
            if base == target:
                continue
            seen.add((base, target))
            links.append({
                "label": f"{base}/{target}",
                "href": pair_url(base, target),
            })
        groups.append({"title": f"{base} pairs", "links": links})
    footer_links = [
        {
            "label": f"{base} to {target}",
            "href": pair_url(base, target),
        }
        for base, target in list(seen)[:30]
    ]
    header_groups = []
    for base, targets in MENU_GROUPS.items():
        header_groups.append({
            "base": base,
            "label": f"{base} pairs",
            "links": [
                {
                    "label": f"{base}/{target}",
                    "href": pair_url(base, target),
                }
                for target in targets
                if target != base
            ],
        })
    active_header_links = [
        {
            "label": f"{active_base}/{target}",
            "href": pair_url(active_base, target),
            "active": target == active_target,
        }
        for target in MENU_GROUPS.get(active_base, [])
        if target != active_base
    ] if active_base else []
    return {
        "groups": groups,
        "footer_links": footer_links,
        "header_groups": header_groups,
        "active_header_base": active_base,
        "active_header_target": active_target,
        "active_header_links": active_header_links,
    }


def build_page_schema(title, description, path, menu=None, breadcrumb_name=None):
    canonical_url = absolute_url(path)
    logo_url = absolute_url("/static/exchangehub-logo.svg")
    nav_links = []
    if menu:
        nav_links = [
            {
                "@type": "SiteNavigationElement",
                "name": link["label"],
                "url": absolute_url(link["href"]),
            }
            for group in menu["groups"]
            for link in group["links"]
        ][:36]
    schema = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Organization",
                "@id": f"{site_base_url()}/#organization",
                "name": "ExchangeHub",
                "url": site_base_url(),
                "logo": {"@type": "ImageObject", "url": logo_url},
            },
            {
                "@type": "WebSite",
                "@id": f"{site_base_url()}/#website",
                "name": "ExchangeHub",
                "url": site_base_url(),
                "publisher": {"@id": f"{site_base_url()}/#organization"},
                "inLanguage": "en",
            },
            {
                "@type": "WebPage",
                "@id": f"{canonical_url}#webpage",
                "url": canonical_url,
                "name": title,
                "description": description,
                "isPartOf": {"@id": f"{site_base_url()}/#website"},
                "publisher": {"@id": f"{site_base_url()}/#organization"},
                "breadcrumb": {"@id": f"{canonical_url}#breadcrumb"},
                "inLanguage": "en",
            },
            {
                "@type": "BreadcrumbList",
                "@id": f"{canonical_url}#breadcrumb",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Exchange Rates", "item": site_base_url()},
                    {"@type": "ListItem", "position": 2, "name": breadcrumb_name or title},
                ],
            },
            *nav_links,
        ],
    }
    return json.dumps(schema)


def render_footer_html(menu):
    links = menu["footer_links"]
    popular = links[:12]
    cross = links[12:24]
    tools = [
        {"label": "Exchange rates dashboard", "href": "/"},
        {"label": "Pair chart tool", "href": "/chart"},
        {"label": "USD to VND", "href": pair_url("USD", "VND")},
        {"label": "VND to USD", "href": pair_url("VND", "USD")},
    ]
    policies = [
        {"label": "About", "href": "/about/"},
        {"label": "Contact", "href": "/contact/"},
        {"label": "Privacy Policy", "href": "/privacy-policy/"},
        {"label": "Terms", "href": "/terms/"},
        {"label": "Disclaimer", "href": "/disclaimer/"},
    ]
    return render_template_string(
        """
        <footer class="site-footer">
          <div class="footer-inner">
            <div class="footer-grid">
              <div class="footer-brand">
                <a class="footer-logo" href="/">{{ brand_html|safe }}</a>
                <p>Currency converters, pair charts, indexed dashboards, and exchange-rate explainers built for quick comparison and market context.</p>
                <p class="footer-disclaimer">Rates are informational mid-market references. Banks, brokers, card networks, and transfer providers may apply spreads, fees, and settlement rules.</p>
              </div>
              <div class="footer-col">
                <h2>Popular pairs</h2>
                <div class="footer-links footer-pair-links">
                  {% for link in popular %}
                    <a href="{{ link.href }}">{{ link.label }}</a>
                  {% endfor %}
                </div>
              </div>
              <div class="footer-col">
                <h2>Cross rates</h2>
                <div class="footer-links footer-pair-links">
                  {% for link in cross %}
                    <a href="{{ link.href }}">{{ link.label }}</a>
                  {% endfor %}
                </div>
              </div>
              <div class="footer-col">
                <h2>Tools & policies</h2>
                <div class="footer-links footer-tool-links">
                  {% for link in tools %}
                    <a href="{{ link.href }}">{{ link.label }}</a>
                  {% endfor %}
                  {% for link in policies %}
                    <a href="{{ link.href }}">{{ link.label }}</a>
                  {% endfor %}
                </div>
              </div>
            </div>
            <div class="footer-bottom">
              <span>Built for exchange-rate comparison and reference.</span>
              <span>Not financial advice.</span>
            </div>
          </div>
        </footer>
        """,
        popular=popular,
        cross=cross,
        tools=tools,
        policies=policies,
        brand_html=BRAND_LOGO_HTML,
    )


INFO_PAGES = {
    "about": {
        "title": "About ExchangeHub",
        "description": "Learn how ExchangeHub builds currency converters, exchange-rate charts, indexed dashboards, and educational exchange-rate explainers.",
        "heading": "About ExchangeHub",
        "sections": [
            {"heading": "What this site does", "body": [
                "ExchangeHub is a currency reference site built around practical tools: exchange-rate converters, pair pages, comparison tables, raw rate charts, and indexed dashboards.",
                "The goal is to make exchange-rate movement easier to read. A pair page shows the actual rate for one currency pair, while the dashboard uses a base-100 index so many currencies can be compared on the same scale.",
            ]},
            {"heading": "How we add value", "body": [
                "Raw exchange rates can be hard to compare because each pair has a different scale. VND pairs may use very large numbers while EUR or GBP pairs may be below 2. ExchangeHub explains both the raw rate and the relative movement behind it.",
                "Each supported pair can include latest conversion tables, high-low-average statistics, reverse rates, trend context, and plain-language explanations for non-specialist readers.",
            ]},
            {"heading": "Data and accuracy", "body": [
                "Rates are collected on a configured schedule and stored locally before being shown on the site. Pages include update timestamps so readers can understand when the displayed data was last refreshed.",
                "Exchange rates are provided for informational reference only. Actual rates from banks, brokers, card networks, exchanges, and remittance providers may include spreads, fees, timing differences, and rounding rules.",
            ]},
        ],
    },
    "contact": {
        "title": "Contact ExchangeHub",
        "description": "Contact ExchangeHub for feedback, correction requests, partnerships, and exchange-rate content questions.",
        "heading": "Contact",
        "sections": [
            {"heading": "Feedback and corrections", "body": [
                "If you find a broken page, stale data, confusing explanation, or exchange-rate display issue, please contact the site owner so it can be reviewed.",
                f"Send feedback, correction requests, and partnership questions to {CONTACT_EMAIL}.",
            ]},
            {"heading": "Response scope", "body": [
                "ExchangeHub can review site issues, data display problems, and general content questions. The site does not provide personal financial, banking, tax, legal, or investment advice.",
            ]},
        ],
    },
    "privacy-policy": {
        "title": "Privacy Policy",
        "description": "Privacy Policy for ExchangeHub, including analytics, advertising, cookies, and server log information.",
        "heading": "Privacy Policy",
        "sections": [
            {"heading": "Information we may collect", "body": [
                "ExchangeHub may collect standard server log information such as IP address, browser type, referring page, device information, request time, and pages visited. This information helps monitor performance, security, and usage patterns.",
                "If analytics or advertising products are enabled, those providers may use cookies or similar technologies to measure traffic, prevent fraud, personalize or limit ads, and report aggregate performance.",
            ]},
            {"heading": "Cookies and advertising", "body": [
                "Advertising partners, including Google if enabled, may use cookies to serve ads based on a user's prior visits to this or other websites.",
                "Users can manage cookie preferences in their browser settings. If Google ads are used, users can also review Google's advertising controls and privacy settings.",
            ]},
            {"heading": "How data is used", "body": [
                "Collected information is used to operate the site, improve page performance, detect abuse, understand which tools are useful, and comply with legal or platform requirements.",
                "ExchangeHub does not ask users to create accounts for basic currency conversion pages. Do not enter private banking, card, wallet, or personal financial information into any public exchange-rate tool.",
            ]},
            {"heading": "Contact", "body": [
                f"For privacy requests, contact {CONTACT_EMAIL}.",
            ]},
        ],
    },
    "terms": {
        "title": "Terms of Use",
        "description": "Terms of Use for ExchangeHub exchange-rate tools, charts, and informational content.",
        "heading": "Terms of Use",
        "sections": [
            {"heading": "Informational use only", "body": [
                "ExchangeHub provides exchange-rate tools, charts, and educational explanations for informational and comparison purposes only. The site does not provide financial, investment, tax, legal, banking, or remittance advice.",
                "You are responsible for verifying rates, fees, timing, and terms with your bank, broker, exchange, card provider, or money-transfer provider before making a transaction.",
            ]},
            {"heading": "Data availability", "body": [
                "Exchange-rate data may be delayed, unavailable, incomplete, or different from the rate offered by a specific provider. The site may change data sources, update schedules, supported currencies, or page features at any time.",
            ]},
            {"heading": "Acceptable use", "body": [
                "Do not overload, scrape aggressively, interfere with, reverse engineer, or misuse the service. Automated access should respect reasonable request rates and any published robots or API restrictions.",
            ]},
        ],
    },
    "disclaimer": {
        "title": "Exchange Rate Disclaimer",
        "description": "Important disclaimer about exchange-rate data, charts, converters, and financial decisions.",
        "heading": "Exchange Rate Disclaimer",
        "sections": [
            {"heading": "Rates are not transaction quotes", "body": [
                "The rates shown on ExchangeHub are reference rates for comparison. They are not guaranteed transaction rates and should not be treated as a binding quote.",
                "Banks, remittance companies, card networks, brokers, and exchanges may use different bid/ask rates, spreads, fees, minimums, maximums, or settlement timing.",
            ]},
            {"heading": "Charts explain movement, not outcomes", "body": [
                "Charts and statistics help explain historical movement in the available data window. They do not predict future exchange rates and should not be used as the only basis for financial decisions.",
            ]},
            {"heading": "Verify before acting", "body": [
                "Before sending money, converting currency, booking travel, pricing invoices, or making business decisions, compare final quotes from regulated providers and consider all fees and terms.",
            ]},
        ],
    },
}


INFO_PAGE_TEMPLATE = """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{{ page.title }}</title>
    <meta name="description" content="{{ page.description }}" />
    <meta name="robots" content="{{ robots_directives }}" />
    <link rel="canonical" href="{{ canonical_url }}" />
    <script type="application/ld+json">{{ schema_json|safe }}</script>
    {{ google_tag_html|safe }}
    <style>
      body { font-family: Arial, sans-serif; margin:0; color:#1f2933; background:#fff; }
      :root { --page-gutter: clamp(12px, 1.6vw, 26px); --shell-width: 100%; }
      main { width:var(--shell-width); box-sizing:border-box; margin:0 auto; padding:30px var(--page-gutter) 50px; }
      .info-content { max-width:980px; }
      h1 { margin:0 0 10px; font-size:34px; }
      h2 { margin:28px 0 10px; font-size:22px; }
      p { line-height:1.65; color:#475467; }
      .lede { font-size:18px; color:#667085; }
      .contact-form { margin-top:28px; max-width:720px; border:1px solid #d8dee6; border-radius:8px; padding:20px; background:#f8fafc; }
      .contact-form h2 { margin-top:0; }
      .form-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:14px; }
      .form-field { display:flex; flex-direction:column; gap:6px; }
      .form-field.full { grid-column:1 / -1; }
      .form-field label { font-weight:700; color:#1f2933; font-size:14px; }
      .form-field input, .form-field textarea { box-sizing:border-box; width:100%; border:1px solid #cfd8e3; border-radius:6px; padding:10px 11px; font:inherit; color:#1f2933; background:#fff; }
      .form-field textarea { min-height:150px; resize:vertical; }
      .form-field input:focus, .form-field textarea:focus { outline:2px solid rgba(56,189,248,.28); border-color:#38bdf8; }
      .form-actions { margin-top:16px; display:flex; align-items:center; gap:12px; flex-wrap:wrap; }
      .contact-submit { border:1px solid #111827; border-radius:6px; background:#111827; color:#fff; font-weight:700; padding:10px 14px; cursor:pointer; }
      .contact-submit:hover { background:#000; }
      .form-note { color:#667085; font-size:13px; margin:0; }
      .form-status { border-radius:6px; padding:10px 12px; margin:0 0 14px; line-height:1.45; }
      .form-status.success { background:#ecfdf3; border:1px solid #abefc6; color:#067647; }
      .form-status.error { background:#fff1f3; border:1px solid #fecdd6; color:#b42318; }
      .bot-field { position:absolute; left:-10000px; width:1px; height:1px; overflow:hidden; }
      .rotation-captcha { grid-column:1 / -1; border:1px solid #d8dee6; border-radius:8px; background:#fff; padding:14px; display:grid; grid-template-columns:136px minmax(0,1fr); gap:16px; align-items:center; }
      .rotation-stage { position:relative; width:136px; height:136px; border-radius:50%; background:#f8fafc; display:grid; place-items:center; border:1px solid #d8dee6; overflow:hidden; box-shadow:inset 0 0 0 6px #eef4f8; }
      .rotation-reference { position:absolute; inset:0; width:100%; height:100%; }
      .rotation-piece { position:relative; z-index:1; width:78px; height:78px; border-radius:50%; transition:transform .08s linear; transform-origin:50% 50%; filter:drop-shadow(0 5px 10px rgba(15,23,42,.18)); }
      .rotation-controls { display:flex; flex-direction:column; gap:8px; min-width:0; }
      .rotation-controls label { font-weight:700; color:#1f2933; font-size:14px; }
      .rotation-controls input[type="range"] { width:100%; accent-color:#111827; }
      .rotation-hint { color:#667085; font-size:13px; margin:0; }
      .site-header { border-bottom:1px solid #e5e7eb; background:#fff; position:sticky; top:0; z-index:10; }
      .site-nav { width:var(--shell-width); box-sizing:border-box; margin:0 auto; padding:12px var(--page-gutter); display:flex; align-items:center; justify-content:space-between; gap:16px; flex-wrap:wrap; }
      .brand { font-weight:800; color:#1f2933; text-decoration:none; }
      .brand-lockup { display:inline-flex; align-items:center; gap:9px; white-space:nowrap; }
      .brand-mark { width:32px; height:32px; display:block; flex:0 0 32px; }
      .brand-name { letter-spacing:0; }
      .header-pairs { display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-left:auto; }
      .header-pairs a, .header-pair-group > button, .header-pairs-label { color:#475467; text-decoration:none; border:1px solid #e5e7eb; border-radius:999px; padding:6px 9px; font-size:13px; line-height:1; background:#fff; }
      .header-pairs a:hover, .header-pair-group > button:hover { color:#1f2933; border-color:#d0d7de; background:#f8fafc; }
      .header-pairs a.is-active { color:#111827; border-color:#f0b90b; background:#fff7d6; font-weight:700; box-shadow:inset 0 0 0 1px rgba(240,185,11,.28); }
      .header-pairs-label { color:#1f2933; font-weight:700; }
      .header-pair-group { position:relative; }
      .header-pair-group::after { content:""; display:none; position:absolute; left:0; top:100%; width:100%; height:10px; }
      .header-pair-group:hover::after, .header-pair-group:focus-within::after { display:block; }
      .header-pair-group > button { cursor:pointer; display:inline-flex; align-items:center; gap:6px; transition:background-color .16s ease-in-out, border-color .16s ease-in-out, color .16s ease-in-out; }
      .header-pair-group > button::after { content:""; width:6px; height:6px; border-right:1.8px solid currentColor; border-bottom:1.8px solid currentColor; transform:translateY(-2px) rotate(45deg); opacity:.72; transition:transform .18s ease-in-out, opacity .18s ease-in-out; }
      .header-pair-group:hover > button::after, .header-pair-group:focus-within > button::after, .header-pair-group.is-open > button::after { transform:translateY(1px) rotate(225deg); opacity:1; }
      .header-pair-submenu { display:none; position:absolute; left:0; top:calc(100% + 8px); z-index:1001; min-width:138px; max-height:min(320px, 58vh); overflow:auto; background:#fff; border:1px solid #d0d7de; border-radius:8px; box-shadow:0 12px 28px rgba(15,23,42,.12); padding:8px; }
      .header-pair-group:hover .header-pair-submenu, .header-pair-group:focus-within .header-pair-submenu, .header-pair-group.is-open .header-pair-submenu { display:flex; flex-direction:column; gap:6px; }
      .header-pair-submenu a { border-radius:6px; border:0; padding:7px 8px; white-space:nowrap; }
      .mega { position:relative; }
      .mega::after { content:""; display:none; position:absolute; right:0; top:100%; width:min(920px, calc(100vw - 32px)); height:10px; }
      .mega:hover::after, .mega:focus-within::after, .mega.is-open::after { display:block; }
      .mega > button { border:1px solid #d0d7de; background:#fff; border-radius:8px; padding:8px 12px; cursor:pointer; display:inline-flex; align-items:center; gap:8px; transition:background-color .16s ease-in-out, border-color .16s ease-in-out, color .16s ease-in-out; }
      .mega > button::after { content:""; width:7px; height:7px; border-right:1.8px solid currentColor; border-bottom:1.8px solid currentColor; transform:translateY(-2px) rotate(45deg); opacity:.72; transition:transform .18s ease-in-out, opacity .18s ease-in-out; }
      .mega:hover > button, .mega:focus-within > button, .mega.is-open > button { background:#f8fafc; border-color:#bcc9d6; }
      .mega:hover > button::after, .mega:focus-within > button::after, .mega.is-open > button::after { transform:translateY(1px) rotate(225deg); opacity:1; }
      .mega-panel { display:none; position:absolute; right:0; top:calc(100% + 8px); z-index:1000; width:min(920px, calc(100vw - 32px)); max-height:min(520px, 72vh); overflow:auto; background:#fff; border:1px solid #d0d7de; border-radius:8px; box-shadow:0 16px 40px rgba(15,23,42,.12); padding:18px; grid-template-columns:repeat(3,minmax(0,1fr)); gap:16px; }
      .mega:hover .mega-panel, .mega:focus-within .mega-panel, .mega.is-open .mega-panel { display:grid; }
      .mega-group h3 { margin:0 0 8px; font-size:14px; color:#475467; }
     .mega-group a { display:block; color:#1f2933; text-decoration:none; padding:4px 0; }
     .mega-group a:hover { text-decoration:underline; }
      .translate-widget { position:relative; min-width:40px; }
      .translate-toggle { border:1px solid #d0d7de; border-radius:999px; background:#fff; width:42px; height:34px; display:inline-flex; align-items:center; justify-content:center; gap:3px; cursor:pointer; font-size:17px; line-height:1; box-shadow:0 1px 2px rgba(15,23,42,.04); transition:background-color .16s ease-in-out, border-color .16s ease-in-out, transform .16s ease-in-out; }
      .translate-toggle::after { content:""; width:5px; height:5px; border-right:1.6px solid #475467; border-bottom:1.6px solid #475467; transform:translateY(-1px) rotate(45deg); transition:transform .18s ease-in-out; }
      .translate-widget.is-open .translate-toggle::after { transform:translateY(1px) rotate(225deg); }
      .translate-toggle:hover { background:#f8fafc; border-color:#bcc9d6; transform:translateY(-1px); }
      .translate-menu { display:none; position:absolute; right:0; top:calc(100% + 8px); z-index:1100; width:180px; max-height:min(320px, 58vh); overflow:auto; padding:8px; border:1px solid #d0d7de; border-radius:10px; background:#fff; box-shadow:0 16px 40px rgba(15,23,42,.14); }
      .translate-widget.is-open .translate-menu { display:grid; gap:4px; }
      .translate-option { border:0; background:transparent; border-radius:8px; padding:7px 8px; display:flex; align-items:center; gap:8px; color:#1f2933; cursor:pointer; text-align:left; font-size:13px; }
      .translate-option:hover { background:#f8fafc; }
      .translate-flag { width:22px; text-align:center; font-size:17px; line-height:1; }
      .translate-native { position:absolute; width:1px; height:1px; overflow:hidden; opacity:0; pointer-events:none; }
      body > .skiptranslate, iframe.skiptranslate { display:none !important; }
      body { top:0 !important; }
      .site-footer { border-top:1px solid #d8dee6; background:linear-gradient(180deg,#f8fafc 0%,#eef4f8 100%); margin-top:32px; }
      .footer-inner { width:var(--shell-width); box-sizing:border-box; margin:0 auto; padding:30px var(--page-gutter) 18px; }
      .footer-grid { display:grid; grid-template-columns:minmax(260px,1.25fr) repeat(3,minmax(180px,1fr)); gap:24px; align-items:start; }
      .footer-logo { display:inline-flex; align-items:center; color:#1f2933; font-weight:800; font-size:20px; text-decoration:none; margin-bottom:10px; }
      .footer-logo .brand-mark { width:34px; height:34px; flex-basis:34px; }
      .footer-brand p { color:#475467; line-height:1.55; margin:0 0 10px; }
      .footer-disclaimer { font-size:13px; }
      .footer-col h2 { margin:0 0 12px; font-size:13px; color:#1f2933; text-transform:uppercase; letter-spacing:.04em; }
      .footer-links { display:flex; flex-direction:column; gap:8px; }
      .footer-pair-links { display:grid; grid-template-columns:repeat(auto-fit,minmax(112px,1fr)); gap:7px; }
      .footer-pair-links a { display:block; border:1px solid #dfe7ef; border-radius:999px; background:rgba(255,255,255,.72); color:#344054; text-decoration:none; font-size:13px; line-height:1; padding:8px 10px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; transition:background-color .16s ease-in-out, border-color .16s ease-in-out, transform .16s ease-in-out; }
      .footer-pair-links a:hover { color:#111827; border-color:#bcc9d6; background:#fff; transform:translateY(-1px); }
      .footer-tool-links a { position:relative; color:#475467; text-decoration:none; font-size:14px; padding-left:15px; line-height:1.35; }
      .footer-tool-links a::before { content:""; position:absolute; left:0; top:.55em; width:5px; height:5px; border-radius:50%; background:#38bdf8; }
      .footer-tool-links a:hover { color:#1f2933; text-decoration:underline; }
      .footer-bottom { border-top:1px solid #e5e7eb; margin-top:24px; padding-top:14px; color:#667085; display:flex; justify-content:space-between; gap:16px; flex-wrap:wrap; font-size:13px; }
      @media (hover:none) {
        .header-pair-group:hover .header-pair-submenu, .header-pair-group:focus-within .header-pair-submenu, .mega:hover .mega-panel, .mega:focus-within .mega-panel { display:none; }
        .header-pair-group.is-open .header-pair-submenu { display:flex; flex-direction:column; gap:6px; }
        .mega.is-open .mega-panel { display:grid; }
      }
      @media (max-width:760px){ h1{font-size:28px}.form-grid,.rotation-captcha{grid-template-columns:1fr}.header-pairs{display:none}.mega-panel,.footer-grid{grid-template-columns:1fr;right:0;max-height:70vh;overflow:auto} }
    </style>
  </head>
  <body>
    <header class="site-header">
      <nav class="site-nav">
        <a class="brand" href="/">{{ brand_html|safe }}</a>
        <div class="header-pairs">
          {% if menu.active_header_links %}
            <span class="header-pairs-label">{{ menu.active_header_base }} pairs</span>
            {% for link in menu.active_header_links %}
              <a class="{% if link.active %}is-active{% endif %}" href="{{ link.href }}"{% if link.active %} aria-current="page"{% endif %}>{{ link.label }}</a>
            {% endfor %}
          {% else %}
            {% for group in menu.header_groups %}
              <div class="header-pair-group">
                <button type="button">{{ group.base }}</button>
                <div class="header-pair-submenu">
                  {% for link in group.links %}
                    <a href="{{ link.href }}">{{ link.label }}</a>
                  {% endfor %}
                </div>
              </div>
            {% endfor %}
          {% endif %}
        </div>
        <div class="mega">
          <button type="button">Currency pairs</button>
          <div class="mega-panel">
            {% for group in menu.groups %}
              <div class="mega-group">
                <h3>{{ group.title }}</h3>
                {% for link in group.links %}
                  <a href="{{ link.href }}">{{ link.label }}</a>
                {% endfor %}
              </div>
            {% endfor %}
          </div>
        </div>
        <div class="translate-widget" aria-label="Translate page">
          <button class="translate-toggle" type="button" aria-label="Translate page" aria-expanded="false">🌐</button>
          <div class="translate-menu" role="menu">
            <button class="translate-option" type="button" data-lang="en"><span class="translate-flag">🇺🇸</span><span>English</span></button>
            <button class="translate-option" type="button" data-lang="vi"><span class="translate-flag">🇻🇳</span><span>Tiếng Việt</span></button>
            <button class="translate-option" type="button" data-lang="th"><span class="translate-flag">🇹🇭</span><span>ไทย</span></button>
            <button class="translate-option" type="button" data-lang="ja"><span class="translate-flag">🇯🇵</span><span>日本語</span></button>
            <button class="translate-option" type="button" data-lang="ko"><span class="translate-flag">🇰🇷</span><span>한국어</span></button>
            <button class="translate-option" type="button" data-lang="zh-CN"><span class="translate-flag">🇨🇳</span><span>中文</span></button>
          </div>
          <div id="google_translate_element" class="translate-native"></div>
        </div>
      </nav>
    </header>
    <main>
      <div class="info-content">
        <h1>{{ page.heading }}</h1>
        <p class="lede">{{ page.description }}</p>
        {% for section in page.sections %}
          <section>
            <h2>{{ section.heading }}</h2>
            {% for paragraph in section.body %}
              <p>{{ paragraph }}</p>
            {% endfor %}
          </section>
        {% endfor %}
        {{ extra_html|default("", true)|safe }}
      </div>
    </main>
    {{ footer_html|safe }}
    <script>
      function closeHeaderMenus() {
        document.querySelectorAll('.mega.is-open, .header-pair-group.is-open').forEach(item => {
          item.classList.remove('is-open');
          const button = item.querySelector('button');
          if(button) button.setAttribute('aria-expanded', 'false');
        });
      }
      function initHeaderMenus() {
        document.querySelectorAll('.mega > button, .header-pair-group > button').forEach(button => {
          if(button.dataset.menuReady === '1') return;
          button.dataset.menuReady = '1';
          button.setAttribute('aria-expanded', 'false');
          button.addEventListener('click', event => {
            event.preventDefault();
            event.stopPropagation();
            const menu = button.parentElement;
            const open = !menu.classList.contains('is-open');
            closeHeaderMenus();
            if(!open) {
              button.blur();
              return;
            }
            menu.classList.toggle('is-open', open);
            button.setAttribute('aria-expanded', open ? 'true' : 'false');
          });
        });
        document.querySelectorAll('.mega-panel, .header-pair-submenu').forEach(panel => {
          panel.addEventListener('click', event => event.stopPropagation());
        });
        document.addEventListener('click', closeHeaderMenus);
        document.addEventListener('keydown', event => {
          if(event.key === 'Escape') closeHeaderMenus();
        });
      }
      function setTranslateCookie(value) {
        const maxAge = value ? '; max-age=31536000' : '; expires=Thu, 01 Jan 1970 00:00:00 GMT';
        document.cookie = `googtrans=${value || ''}; path=/${maxAge}`;
        if (location.hostname.includes('.')) {
          document.cookie = `googtrans=${value || ''}; path=/; domain=.${location.hostname}${maxAge}`;
        }
      }
      function applyTranslation(lang) {
        const combo = document.querySelector('.goog-te-combo');
        if (lang === 'en') {
          setTranslateCookie('');
          location.reload();
          return;
        }
        setTranslateCookie(`/en/${lang}`);
        if (combo) {
          combo.value = lang;
          combo.dispatchEvent(new Event('change'));
        } else {
          location.reload();
        }
      }
      function initTranslateMenu() {
        document.querySelectorAll('.translate-widget').forEach(widget => {
          if (widget.dataset.translateReady === '1') return;
          widget.dataset.translateReady = '1';
          const toggle = widget.querySelector('.translate-toggle');
          toggle.addEventListener('click', event => {
            event.stopPropagation();
            const open = !widget.classList.contains('is-open');
            document.querySelectorAll('.translate-widget.is-open').forEach(item => item.classList.remove('is-open'));
            widget.classList.toggle('is-open', open);
            toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
          });
          widget.querySelectorAll('[data-lang]').forEach(button => {
            button.addEventListener('click', () => applyTranslation(button.dataset.lang));
          });
        });
        document.addEventListener('click', () => {
          document.querySelectorAll('.translate-widget.is-open').forEach(widget => {
            widget.classList.remove('is-open');
            const toggle = widget.querySelector('.translate-toggle');
            if (toggle) toggle.setAttribute('aria-expanded', 'false');
          });
        });
      }
      function googleTranslateElementInit() {
        new google.translate.TranslateElement({ pageLanguage: 'en', autoDisplay: false, layout: google.translate.TranslateElement.InlineLayout.HORIZONTAL }, 'google_translate_element');
        initTranslateMenu();
      }
      document.addEventListener('DOMContentLoaded', initHeaderMenus);
      document.addEventListener('DOMContentLoaded', initTranslateMenu);
    </script>
    <script src="https://translate.google.com/translate_a/element.js?cb=googleTranslateElementInit"></script>
  </body>
</html>
"""


CONTACT_FORM_TEMPLATE = """
<form class="contact-form" method="post" action="/contact/" novalidate>
  <h2>Send a message</h2>
  {% if success %}
    <p class="form-status success">Thanks. Your message has been sent.</p>
    <script>
      window.exchangeTrackEvent && window.exchangeTrackEvent('contact_submit_success', {
        form_name: 'contact',
        page_path: location.pathname
      });
    </script>
  {% endif %}
  {% if errors %}
    <div class="form-status error">
      {% for error in errors %}
        <div>{{ error }}</div>
      {% endfor %}
    </div>
  {% endif %}
  <input type="hidden" name="form_token" value="{{ form_token }}" />
  <div class="bot-field" aria-hidden="true">
    <label for="website">Website</label>
    <input id="website" name="website" type="text" tabindex="-1" autocomplete="off" />
  </div>
  <div class="form-grid">
    <div class="form-field">
      <label for="contact-name">Name</label>
      <input id="contact-name" name="name" type="text" autocomplete="name" maxlength="80" value="{{ values.name }}" required />
    </div>
    <div class="form-field">
      <label for="contact-email">Email</label>
      <input id="contact-email" name="email" type="email" autocomplete="email" maxlength="120" value="{{ values.email }}" required />
    </div>
    <div class="form-field full">
      <label for="contact-subject">Subject</label>
      <input id="contact-subject" name="subject" type="text" maxlength="140" value="{{ values.subject }}" required />
    </div>
    <div class="form-field full">
      <label for="contact-message">Message</label>
      <textarea id="contact-message" name="message" maxlength="4000" required>{{ values.message }}</textarea>
    </div>
    <div class="rotation-captcha" data-rotation-start="{{ rotation_start }}">
      <div class="rotation-stage" aria-hidden="true">
        <svg class="rotation-reference" viewBox="0 0 140 140" role="img" focusable="false">
          <defs>
            <linearGradient id="captcha-sky" x1="0" x2="1" y1="0" y2="1">
              <stop offset="0" stop-color="#38bdf8"/>
              <stop offset="1" stop-color="#22c55e"/>
            </linearGradient>
          </defs>
          <circle cx="70" cy="70" r="64" fill="#111827"/>
          <circle cx="70" cy="70" r="43" fill="#f8fafc"/>
          <path d="M70 10a60 60 0 0 1 52 30" fill="none" stroke="#f59e0b" stroke-width="10" stroke-linecap="round"/>
          <path d="M130 70a60 60 0 0 1-30 52" fill="none" stroke="#38bdf8" stroke-width="10" stroke-linecap="round"/>
          <path d="M70 130a60 60 0 0 1-52-30" fill="none" stroke="#22c55e" stroke-width="10" stroke-linecap="round"/>
          <path d="M10 70a60 60 0 0 1 30-52" fill="none" stroke="#facc15" stroke-width="10" stroke-linecap="round"/>
          <path d="M70 21v28M119 70H91M70 119V91M21 70h28" stroke="#fff" stroke-width="5" stroke-linecap="round"/>
          <circle cx="70" cy="70" r="44" fill="none" stroke="#d8dee6" stroke-width="2"/>
        </svg>
        <svg class="rotation-piece" viewBox="0 0 100 100" role="img" focusable="false">
          <circle cx="50" cy="50" r="49" fill="#111827"/>
          <path d="M50 2a48 48 0 0 1 42 24" fill="none" stroke="#f59e0b" stroke-width="12" stroke-linecap="round"/>
          <path d="M98 50a48 48 0 0 1-24 42" fill="none" stroke="#38bdf8" stroke-width="12" stroke-linecap="round"/>
          <path d="M50 98A48 48 0 0 1 8 74" fill="none" stroke="#22c55e" stroke-width="12" stroke-linecap="round"/>
          <path d="M2 50A48 48 0 0 1 26 8" fill="none" stroke="#facc15" stroke-width="12" stroke-linecap="round"/>
          <path d="M50 0v28M100 50H72M50 100V72M0 50h28" stroke="#fff" stroke-width="6" stroke-linecap="round"/>
          <circle cx="50" cy="50" r="20" fill="url(#captcha-sky)"/>
          <circle cx="50" cy="50" r="8" fill="#fff"/>
        </svg>
      </div>
      <div class="rotation-controls">
        <label for="rotation-response">Rotate image 1 to match image 2</label>
        <input id="rotation-response" class="rotation-slider" type="range" min="0" max="359" step="1" value="0" />
        <input class="rotation-response" name="rotation_response" type="hidden" value="0" />
        <p class="rotation-hint">Slide until the inner piece lines up with the outer picture.</p>
      </div>
    </div>
  </div>
  <div class="form-actions">
    <button class="contact-submit" type="submit">Send message</button>
    <p class="form-note">Protected by server-side spam checks.</p>
  </div>
  <script>
    document.querySelectorAll('.rotation-captcha').forEach(captcha => {
      const start = Number(captcha.dataset.rotationStart || 0);
      const piece = captcha.querySelector('.rotation-piece');
      const slider = captcha.querySelector('.rotation-slider');
      const response = captcha.querySelector('.rotation-response');
      function updateRotation() {
        const value = Number(slider.value || 0);
        piece.style.transform = `rotate(${start + value}deg)`;
        response.value = String(value);
      }
      slider.addEventListener('input', updateRotation);
      updateRotation();
    });
  </script>
</form>
"""


def render_contact_form(values=None, errors=None, success=False):
    rotation_start, form_token = prepare_contact_form()
    return render_template_string(
        CONTACT_FORM_TEMPLATE,
        values=values or {"name": "", "email": "", "subject": "", "message": ""},
        errors=errors or [],
        success=success,
        rotation_start=rotation_start,
        form_token=form_token,
    )


def render_info_page(slug, extra_html=""):
    page = INFO_PAGES.get(slug)
    if not page:
        return "Not found", 404
    menu = build_menu_model()
    path = "/" + slug + "/"
    return render_template_string(
        INFO_PAGE_TEMPLATE,
        page=page,
        menu=menu,
        footer_html=render_footer_html(menu),
        brand_html=BRAND_LOGO_HTML,
        canonical_url=absolute_url(path),
        schema_json=build_page_schema(page["title"], page["description"], path, menu, page["heading"]),
        extra_html=extra_html,
        robots_directives=ROBOTS_INDEX_DIRECTIVES,
        google_tag_html=GOOGLE_TAG_HTML,
    )


def render_home_page():
    cache_key = site_base_url()
    cached = _HOME_PAGE_CACHE.get(cache_key)
    if cached and page_cache_fresh(cached["ts"]):
        return cached["html"]

    model = cached_home_model(include_series=False)
    menu = build_menu_model()
    description = "Compare popular currencies against USD, EUR, JPY, GBP, CNY, and VND with live conversion tables and normalized exchange-rate charts."
    html = render_template_string(
        HOME_TEMPLATE,
        model=model,
        menu=menu,
        footer_html=render_footer_html(menu),
        format_rate=format_rate,
        brand_html=BRAND_LOGO_HTML,
        canonical_url=absolute_url("/"),
        schema_json=build_page_schema("Exchange Rates Dashboard", description, "/", menu, "Exchange Rates Dashboard"),
        robots_directives=ROBOTS_INDEX_DIRECTIVES,
        google_tag_html=GOOGLE_TAG_HTML,
    )
    _HOME_PAGE_CACHE[cache_key] = {"ts": time.time(), "html": html}
    return html


@app.route("/")
def index():
    return render_home_page()


@app.route("/about/")
def about_page():
    return render_info_page("about")


@app.route("/contact/", methods=["GET", "POST"])
def contact_page():
    values = {"name": "", "email": "", "subject": "", "message": ""}
    errors = []
    success = False

    if request.method == "POST":
        errors, values = validate_contact_submission(request.form)
        ip = get_client_ip()
        if not errors and contact_rate_limited(ip):
            errors.append("Please wait before sending another message.")
        if not errors:
            try:
                send_contact_email(values)
                mark_contact_submitted(ip)
                values = {"name": "", "email": "", "subject": "", "message": ""}
                success = True
            except Exception:
                app.logger.exception("Contact form mail delivery failed")
                errors.append("Mail delivery is not configured yet. Please try again later.")

    return render_info_page("contact", extra_html=render_contact_form(values, errors, success))


@app.route("/privacy-policy/")
def privacy_policy_page():
    return render_info_page("privacy-policy")


@app.route("/terms/")
def terms_page():
    return render_info_page("terms")


@app.route("/disclaimer/")
def disclaimer_page():
    return render_info_page("disclaimer")


def site_base_url():
    return request.url_root.rstrip("/")


def absolute_url(path):
    if str(path).startswith(("http://", "https://")):
        return path
    return site_base_url() + (path if str(path).startswith("/") else f"/{path}")


def redirect_permanent(path):
    return redirect(path, code=301)


@app.route("/about")
def about_page_legacy_redirect():
    return redirect_permanent("/about/")


@app.route("/contact", methods=["GET"])
def contact_page_legacy_redirect():
    return redirect_permanent("/contact/")


@app.route("/privacy-policy")
def privacy_policy_page_legacy_redirect():
    return redirect_permanent("/privacy-policy/")


@app.route("/terms")
def terms_page_legacy_redirect():
    return redirect_permanent("/terms/")


@app.route("/disclaimer")
def disclaimer_page_legacy_redirect():
    return redirect_permanent("/disclaimer/")


@app.route("/robots.txt")
def robots_txt():
    disallow_rules = "\n".join(f"Disallow: {path}" for path in ROBOTS_DISALLOW_PATHS)
    body = f"User-agent: *\nAllow: /\n{disallow_rules}\nSitemap: {site_base_url()}/sitemap.xml\n"
    return Response(body, mimetype="text/plain")


@app.route("/healthz")
def healthz():
    return jsonify({"ok": True, "service": "exchangehub"})


@app.route("/sitemap.xml")
def sitemap_xml():
    urls = [
        "/",
        "/chart",
        "/about/",
        "/contact/",
        "/privacy-policy/",
        "/terms/",
        "/disclaimer/",
    ]
    try:
        urls.extend(pair_url(base, target) for base, target in load_rate_config())
    except Exception:
        pass
    for base, targets in MENU_GROUPS.items():
        urls.extend(pair_url(base, target) for target in targets if base != target)
    seen = []
    for url in urls:
        if url not in seen:
            seen.append(url)
    now = time.strftime("%Y-%m-%d", time.gmtime())
    items = "\n".join(
        f"  <url><loc>{escape(site_base_url() + path)}</loc><lastmod>{now}</lastmod></url>"
        for path in seen
    )
    xml = f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{items}\n</urlset>\n'
    return Response(xml, mimetype="application/xml")


@app.route("/chart")
def chart_tool():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/chart/")
def chart_tool_slash():
    return redirect_permanent("/chart")


@app.route("/api/home")
def api_home():
    return jsonify(cached_home_model(request.args.get("quote", "USD")))


@app.route("/api/home-chart")
def api_home_chart():
    quote = request.args.get("quote", "USD").upper()
    base = request.args.get("base", "").upper()
    if quote not in config_currencies():
        quote = "USD"
    if base not in HOME_CHART_BASES or base == quote:
        return jsonify({"error": "Unsupported chart pair"}), 404
    series = build_home_chart_series(base, quote)
    if series is None:
        return jsonify({"error": "Unsupported chart pair"}), 404
    return jsonify({
        "quote": quote,
        "base": base,
        "series": series,
        "chart_description": chart_description_for_quote(quote),
    })


@app.route("/api/currencies")
def api_currencies():
    try:
        pairs = load_rate_config()
        currencies = config_currencies()
    except Exception:
        pairs = []
        currencies = ["USD"]
    return jsonify({
        "pairs": [f"{base}_{target}".lower() for base, target in pairs],
        "currencies": currencies,
    })


@app.route("/api/latest")
def api_latest():
    base = request.args.get("base", "VND").upper()
    target = request.args.get("target", "USD").upper()
    if base == target:
        return jsonify({"ts": int(time.time()), "rate": 1.0, "base": base, "target": target})

    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT ts, rate FROM rates WHERE base=? AND target=? ORDER BY ts DESC LIMIT 1", (base, target)
    )
    row = cur.fetchone()
    conn.close()
    if row:
        ts, rate = row
        return jsonify({"ts": ts, "rate": rate, "base": base, "target": target})

    # Fallback to JSON file if present
    try:
        data = load_pair_entries(base, target)
        matches = [e for e in data if e.get("base") == base and e.get("target") == target]
        if matches:
            latest = max(matches, key=lambda x: x.get("ts", 0))
            return jsonify({"ts": latest["ts"], "rate": latest["rate"], "base": base, "target": target})
        data = load_json_rates()
        derived = derive_latest_from_entries(data, base, target)
        if derived:
            return jsonify(derived)
    except Exception:
        pass

    return jsonify({"error": "no data"}), 404


@app.route("/api/history")
def api_history():
    base = request.args.get("base", "VND").upper()
    target = request.args.get("target", "USD").upper()
    hours_param = request.args.get("hours", "all").strip().lower()
    show_all = hours_param in ("", "all", "0")
    hours = None if show_all else int(hours_param)
    if base == target:
        return jsonify({"base": base, "target": target, "data": [{"ts": int(time.time()), "rate": 1.0}]})

    conn = get_db_conn()
    cur = conn.cursor()
    if show_all:
        cur.execute(
            "SELECT ts, rate FROM rates WHERE base=? AND target=? ORDER BY ts ASC",
            (base, target),
        )
    else:
        since = int(time.time()) - hours * 3600
        cur.execute(
            "SELECT ts, rate FROM rates WHERE base=? AND target=? AND ts>=? ORDER BY ts ASC",
            (base, target, since),
        )
    rows = cur.fetchall()
    conn.close()
    data = [{"ts": r[0], "rate": r[1]} for r in rows]
    if data:
        return jsonify({"base": base, "target": target, "data": data})

    # Fallback to JSON
    try:
        all_entries = load_pair_entries(base, target)
        filtered = [
            e for e in all_entries
            if e.get("base") == base
            and e.get("target") == target
            and (show_all or e.get("ts", 0) >= since)
        ]
        filtered_sorted = sorted(filtered, key=lambda x: x.get("ts", 0))
        data = [{"ts": e["ts"], "rate": e["rate"]} for e in filtered_sorted]
        if not data:
            all_entries = load_json_rates()
            data = derive_history_from_entries(all_entries, base, target, None if show_all else since)
        return jsonify({"base": base, "target": target, "data": data})
    except Exception:
        pass

    return jsonify({"base": base, "target": target, "data": []})


@app.route("/api/convert")
def api_convert():
    amount = float(request.args.get("amount", "1"))
    base = request.args.get("base", "VND").upper()
    target = request.args.get("target", "USD").upper()
    if base == target:
        return jsonify({"base": base, "target": target, "rate": 1.0, "amount": amount, "converted": amount})

    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT rate FROM rates WHERE base=? AND target=? ORDER BY ts DESC LIMIT 1", (base, target)
    )
    row = cur.fetchone()
    conn.close()
    if row:
        rate = row[0]
        return jsonify({"base": base, "target": target, "rate": rate, "amount": amount, "converted": amount * rate})

    # Fallback to JSON latest
    try:
        data = load_pair_entries(base, target)
        matches = [e for e in data if e.get("base") == base and e.get("target") == target]
        if matches:
            latest = max(matches, key=lambda x: x.get("ts", 0))
            rate = latest["rate"]
            return jsonify({"base": base, "target": target, "rate": rate, "amount": amount, "converted": amount * rate})
        data = load_json_rates()
        derived = derive_latest_from_entries(data, base, target)
        if derived:
            rate = derived["rate"]
            return jsonify({"base": base, "target": target, "rate": rate, "amount": amount, "converted": amount * rate})
    except Exception:
        pass

    return jsonify({"error": "no rate available"}), 404


HOME_TEMPLATE = """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Exchange Rates Dashboard</title>
    <meta name="description" content="Compare popular currencies against USD, EUR, JPY, GBP, CNY, and VND with live conversion tables and normalized exchange-rate charts." />
    <meta name="robots" content="{{ robots_directives }}" />
    <link rel="canonical" href="{{ canonical_url }}" />
    <script type="application/ld+json">{{ schema_json|safe }}</script>
    {{ google_tag_html|safe }}
    <style>
      :root { --page-gutter: clamp(12px, 1.6vw, 26px); --shell-width: 100%; }
      body { font-family: Arial, sans-serif; margin: 0; color: #1f2933; background: #fff; }
      main { width:var(--shell-width); box-sizing:border-box; margin:0 auto; padding:18px var(--page-gutter) 48px; }
      h1 { margin: 0 0 8px; font-size: 30px; }
      h2 { margin: 22px 0 10px; font-size: 20px; }
      .muted { color: #667085; }
      .topbar { display:flex; justify-content:space-between; gap:16px; align-items:flex-start; margin-bottom: 12px; }
      .topbar h1 { margin-bottom:6px; }
      .topbar .muted { margin:0; font-size:14px; line-height:1.45; }
      .actions { display:flex; gap:8px; align-items:center; flex-wrap:wrap; justify-content:flex-end; }
      .actions a { display:inline-flex; align-items:center; justify-content:center; min-height:34px; box-sizing:border-box; padding:7px 11px; border:1px solid #d0d7de; border-radius:8px; color:#1f2933; text-decoration:none; background:#fff; font-size:14px; line-height:1; white-space:nowrap; transition:background-color .16s ease-in-out, border-color .16s ease-in-out, transform .16s ease-in-out; }
      .actions a:hover { background:#f8fafc; border-color:#bcc9d6; transform:translateY(-1px); }
      .chart-wrap { position:relative; border: 1px solid #e5e7eb; padding: clamp(10px, 1vw, 16px); border-radius: 8px; }
      .chart-wrap canvas { width:100% !important; height:100% !important; }
      #home-chart { min-height:360px; }
      .chart-status { position:absolute; inset:clamp(10px, 1vw, 16px); display:flex; align-items:center; justify-content:center; color:#667085; font-size:14px; text-align:center; background:rgba(255,255,255,.86); }
      .chart-wrap.is-ready .chart-status { display:none; }
      .chart-desc { margin:12px 0 0; border:1px solid #e5e7eb; border-radius:8px; background:#f8fafc; color:#475467; font-size:14px; line-height:1.55; padding:14px; }
      .chart-desc p { margin:0 0 10px; }
      .chart-desc p:last-child { margin-bottom:0; }
      .section-head { display:flex; justify-content:space-between; gap:16px; align-items:center; flex-wrap:wrap; }
      .topbar + section h2 { margin-top:6px; }
      .topbar + section .section-head { margin-top:0; }
      .section-head h2 { margin-bottom:6px; }
      .section-head p { margin:0; font-size:14px; line-height:1.45; }
      .section-head label { color:#475467; font-size:14px; }
      .section-head label:has(#home-quote) { display:inline-flex; align-items:center; gap:8px; white-space:nowrap; }
      .section-head select { margin-left:6px; }
      .section-head select, .converter-controls input, .converter-controls select {
        box-sizing:border-box;
        height:38px;
        border:1px solid #cfd8e3;
        border-radius:8px;
        background:#fff;
        color:#1f2933;
        font-size:14px;
        line-height:1.2;
        padding:8px 42px 8px 10px;
        outline:none;
        transition:border-color .16s ease-in-out, box-shadow .16s ease-in-out, background-color .16s ease-in-out;
      }
      .section-head select, .converter-controls select {
        appearance:none;
        -webkit-appearance:none;
        background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='14' height='14' viewBox='0 0 20 20' fill='none'%3E%3Cpath d='M5.5 7.5L10 12l4.5-4.5' stroke='%23475467' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
        background-repeat:no-repeat;
        background-position:right 13px center;
        background-size:14px 14px;
      }
      .converter-controls input { padding-right:10px; }
      .section-head select:focus, .converter-controls input:focus, .converter-controls select:focus {
        border-color:#38bdf8;
        box-shadow:0 0 0 3px rgba(56,189,248,.18);
      }
      .section-head select:hover, .converter-controls input:hover, .converter-controls select:hover { border-color:#bcc9d6; background:#fcfdff; }
      .converter-inline { border:1px solid #d0d7de; border-radius:8px; padding:14px; background:#fff; box-shadow:0 18px 48px rgba(15,23,42,.12); }
      .converter-panel { position:fixed; left:50%; bottom:0; transform:translate(-50%,0); width:calc(100vw - 24px); max-height:calc(100vh - 68px); overflow:visible; border:1px solid #d0d7de; border-bottom:0; border-radius:8px 8px 0 0; padding:12px; background:#fff; box-shadow:0 18px 48px rgba(15,23,42,.18); z-index:20; transition:transform .24s ease-in-out, opacity .24s ease-in-out; }
      .converter-panel.is-hidden { transform:translate(-50%, calc(100% + 16px)); opacity:0; pointer-events:none; }
      .converter-panel-head { display:flex; justify-content:space-between; gap:16px; align-items:flex-start; }
      .converter-panel .converter-panel-head { display:grid; grid-template-columns:minmax(220px,1fr) auto auto; gap:12px; align-items:start; }
      .converter-title-row { display:flex; align-items:baseline; gap:10px; flex-wrap:wrap; }
      .converter-updated { color:#667085; font-size:12px; white-space:nowrap; }
      .converter-panel h2, .converter-inline h2 { margin:6px 0 10px; }
      .converter-panel .muted, .converter-inline .muted { margin:0 0 12px; }
      .converter-panel .muted { display:none; }
      .converter-close { position:relative; border:1px solid #d0d7de; background:#fff; border-radius:999px; width:34px; height:34px; cursor:pointer; transition:background-color .18s ease-in-out, border-color .18s ease-in-out, transform .18s ease-in-out, box-shadow .18s ease-in-out; box-shadow:0 1px 2px rgba(15,23,42,.04); }
      .converter-close::before { content:""; position:absolute; left:50%; top:50%; width:8px; height:8px; border-right:2px solid #1f2933; border-bottom:2px solid #1f2933; transform:translate(-50%,-65%) rotate(45deg); transition:transform .18s ease-in-out; }
      .converter-close:hover { background:#f8fafc; border-color:#bcc9d6; transform:translateY(2px); box-shadow:0 4px 10px rgba(15,23,42,.08); }
      .converter-close:hover::before { transform:translate(-50%,-45%) rotate(45deg); }
      .converter-open { position:fixed; right:16px; bottom:18px; z-index:20; border:1px solid #d0d7de; border-radius:999px; background:#1f2933; color:#fff; padding:10px 14px; cursor:pointer; box-shadow:0 12px 28px rgba(15,23,42,.18); display:none; }
      .converter-open.is-visible { display:block; }
      .converter-controls { display:grid; grid-template-columns:1.2fr 1fr 1fr; gap:10px; align-items:end; margin-bottom:12px; }
      .converter-panel .converter-controls { grid-template-columns:150px 160px; max-width:none; margin:0 0 10px; padding-top:8px; }
      .converter-controls label { display:block; font-size:12px; font-weight:700; color:#475467; letter-spacing:.01em; }
      .converter-controls input, .converter-controls select { display:block; margin-top:5px; width:100%; min-width:0; }
      .converter-panel .converter-controls input, .converter-panel .converter-controls select { height:34px; padding-top:6px; padding-bottom:6px; }
      select.converter-select-native {
        position:absolute;
        width:1px;
        height:1px;
        margin:0;
        padding:0;
        border:0;
        opacity:0;
        pointer-events:none;
      }
      .converter-select { position:relative; margin-top:5px; width:100%; min-width:0; }
      .section-head .converter-select { display:inline-block; width:88px; margin:0; vertical-align:middle; }
      .section-head .converter-select-button { height:36px; padding:7px 11px; }
      .section-head .converter-select-menu { min-width:108px; right:0; left:auto; }
      .converter-select-button {
        width:100%;
        height:38px;
        border:1px solid #cfd8e3;
        border-radius:8px;
        background:#fff;
        color:#1f2933;
        display:flex;
        align-items:center;
        justify-content:space-between;
        gap:10px;
        padding:8px 12px;
        cursor:pointer;
        font:inherit;
        font-size:14px;
        line-height:1.2;
        text-align:left;
        transition:border-color .16s ease-in-out, box-shadow .16s ease-in-out, background-color .16s ease-in-out;
      }
      .converter-panel .converter-select-button { height:34px; padding:6px 10px; }
      .converter-select-button::after {
        content:"";
        width:7px;
        height:7px;
        border-right:2px solid #475467;
        border-bottom:2px solid #475467;
        transform:translateY(-2px) rotate(45deg);
        transition:transform .18s ease-in-out;
        flex:0 0 auto;
      }
      .converter-select.is-open .converter-select-button::after { transform:translateY(2px) rotate(225deg); }
      .converter-select-button:hover { border-color:#bcc9d6; background:#fcfdff; }
      .converter-select-button:focus { outline:none; border-color:#38bdf8; box-shadow:0 0 0 3px rgba(56,189,248,.18); }
      .converter-select-menu {
        display:none;
        position:absolute;
        left:0;
        top:calc(100% + 8px);
        z-index:60;
        width:100%;
        min-width:150px;
        max-height:min(260px, 48vh);
        overflow:auto;
        padding:6px;
        border:1px solid #d0d7de;
        border-radius:8px;
        background:#fff;
        box-shadow:0 16px 40px rgba(15,23,42,.12);
        box-sizing:border-box;
      }
      .converter-panel .converter-select-menu { z-index:80; top:auto; bottom:calc(100% + 8px); max-height:min(220px, 38vh); }
      .converter-select.is-open .converter-select-menu { display:grid; gap:4px; }
      .converter-select-option {
        border:0;
        border-radius:6px;
        background:transparent;
        color:#1f2933;
        padding:7px 8px;
        cursor:pointer;
        text-align:left;
        font-size:13px;
      }
      .converter-select-option:hover, .converter-select-option:focus, .converter-select-option.is-selected { background:#f8fafc; outline:none; }
      .converter-select-option.is-selected { font-weight:700; }
      .converter-results { display:block; }
      .converter-panel .converter-results { display:grid; grid-template-columns:repeat(auto-fit,minmax(118px,1fr)); gap:6px; }
      .converter-result { display:block; border:1px solid #e5e7eb; border-radius:6px; padding:6px 8px; text-decoration:none; }
      .converter-result span { display:block; color:#667085; font-size:11px; line-height:1.2; }
      .converter-result strong { display:block; margin-top:2px; color:#1f2933; font-size:16px; line-height:1.15; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
      .matrix-wrap { overflow-x:auto; border:1px solid #e5e7eb; border-radius:8px; }
      table { width:100%; border-collapse: collapse; min-width: 760px; }
      th, td { padding: 10px; border-bottom: 1px solid #e5e7eb; text-align: right; white-space: nowrap; }
      th:first-child, td:first-child { text-align:left; position: sticky; left:0; background:#fff; }
      th { background: #f8fafc; font-size: 13px; color: #475467; }
      td a { color:#1f2933; text-decoration:none; }
      td a:hover { text-decoration:underline; }
      .currency { font-weight:700; }
      .note-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; margin-top: 22px; }
      .note { border:1px solid #e5e7eb; border-radius:8px; padding:14px; }
      .note h3 { margin:0 0 6px; font-size:16px; }
      .mover-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; }
      .mover-list { border:1px solid #e5e7eb; border-radius:8px; overflow:hidden; background:#fff; }
      .mover-list h3 { margin:0; padding:10px 12px; font-size:15px; background:#f8fafc; border-bottom:1px solid #e5e7eb; }
      .mover-item { display:grid; grid-template-columns:minmax(76px,1fr) auto; gap:10px; align-items:center; padding:9px 12px; color:#1f2933; text-decoration:none; border-bottom:1px solid #eef2f7; }
      .mover-item:last-child { border-bottom:0; }
      .mover-item:hover { background:#f8fafc; }
      .mover-pair { font-weight:700; }
      .mover-rate { display:block; margin-top:2px; color:#667085; font-size:12px; font-weight:400; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
      .mover-change { font-weight:700; white-space:nowrap; }
      .mover-change.up { color:#16a34a; }
      .mover-change.down { color:#dc2626; }
      .mover-change.flat { color:#667085; }
      .explain-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:18px; margin-top:24px; }
      .explain-block { border-top:1px solid #e5e7eb; padding-top:16px; }
      .explain-block h3 { margin:0 0 8px; font-size:18px; }
      .site-header { border-bottom:1px solid #e5e7eb; background:#fff; position:sticky; top:0; z-index:10; }
      .site-nav { width:var(--shell-width); box-sizing:border-box; margin:0 auto; padding:12px var(--page-gutter); display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; }
      .brand { font-weight:800; color:#1f2933; text-decoration:none; }
      .brand-lockup { display:inline-flex; align-items:center; gap:9px; white-space:nowrap; }
      .brand-mark { width:32px; height:32px; display:block; flex:0 0 32px; }
      .brand-name { letter-spacing:0; }
      .header-pairs { display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-left:auto; }
      .header-pairs a, .header-pair-group > button, .header-pairs-label { color:#475467; text-decoration:none; border:1px solid #e5e7eb; border-radius:999px; padding:6px 9px; font-size:13px; line-height:1; background:#fff; }
      .header-pairs a:hover, .header-pair-group > button:hover { color:#1f2933; border-color:#d0d7de; background:#f8fafc; }
      .header-pairs a.is-active { color:#111827; border-color:#f0b90b; background:#fff7d6; font-weight:700; box-shadow:inset 0 0 0 1px rgba(240,185,11,.28); }
      .header-pairs-label { color:#1f2933; font-weight:700; }
      .header-pair-group { position:relative; }
      .header-pair-group::after { content:""; display:none; position:absolute; left:0; top:100%; width:100%; height:10px; }
      .header-pair-group:hover::after, .header-pair-group:focus-within::after { display:block; }
      .header-pair-group > button { cursor:pointer; display:inline-flex; align-items:center; gap:6px; transition:background-color .16s ease-in-out, border-color .16s ease-in-out, color .16s ease-in-out; }
      .header-pair-group > button::after { content:""; width:6px; height:6px; border-right:1.8px solid currentColor; border-bottom:1.8px solid currentColor; transform:translateY(-2px) rotate(45deg); opacity:.72; transition:transform .18s ease-in-out, opacity .18s ease-in-out; }
      .header-pair-group:hover > button::after, .header-pair-group:focus-within > button::after, .header-pair-group.is-open > button::after { transform:translateY(1px) rotate(225deg); opacity:1; }
      .header-pair-submenu { display:none; position:absolute; left:0; top:calc(100% + 8px); z-index:1001; min-width:138px; max-height:min(320px, 58vh); overflow:auto; background:#fff; border:1px solid #d0d7de; border-radius:8px; box-shadow:0 12px 28px rgba(15,23,42,.12); padding:8px; }
      .header-pair-group:hover .header-pair-submenu, .header-pair-group:focus-within .header-pair-submenu, .header-pair-group.is-open .header-pair-submenu { display:flex; flex-direction:column; gap:6px; }
      .header-pair-submenu a { border-radius:6px; border:0; padding:7px 8px; white-space:nowrap; }
      .quickbar { border-bottom:1px solid #e5e7eb; background:#f8fafc; }
      .quickbar-inner { width:var(--shell-width); box-sizing:border-box; margin:0 auto; padding:8px var(--page-gutter) 6px; }
      #quick-converter-panel {
        display:grid;
        grid-template-columns:minmax(0,3fr) minmax(280px,.85fr);
        gap:10px;
        align-items:end;
        padding:10px 14px 8px;
      }
      #quick-converter-panel .converter-panel-head { display:none; }
      #quick-converter-panel .converter-controls {
        display:grid;
        grid-template-columns:1.2fr 1fr 1fr;
        gap:10px;
        align-items:end;
        margin:0;
      }
      #quick-converter-panel .converter-controls label { min-width:0; }
      #quick-converter-panel .converter-controls label { line-height:1.15; }
      #quick-converter-panel .converter-controls input,
      #quick-converter-panel .converter-select-button { height:38px; }
      #quick-converter-panel #quick-converter-results {
        align-self:end;
        min-width:0;
      }
      #quick-converter-panel .converter-result {
        min-height:38px;
        box-sizing:border-box;
        display:flex;
        flex-direction:column;
        justify-content:center;
        padding:5px 8px;
        margin:0;
      }
      .mega { position:relative; }
      .mega::after { content:""; display:none; position:absolute; right:0; top:100%; width:min(920px, calc(100vw - 32px)); height:10px; }
      .mega:hover::after, .mega:focus-within::after, .mega.is-open::after { display:block; }
      .mega > button { min-height:34px; border:1px solid #d0d7de; background:#fff; border-radius:8px; padding:8px 12px; cursor:pointer; display:inline-flex; align-items:center; gap:8px; transition:background-color .16s ease-in-out, border-color .16s ease-in-out, color .16s ease-in-out; }
      .mega > button::after { content:""; width:7px; height:7px; border-right:1.8px solid currentColor; border-bottom:1.8px solid currentColor; transform:translateY(-2px) rotate(45deg); opacity:.72; transition:transform .18s ease-in-out, opacity .18s ease-in-out; }
      .mega:hover > button, .mega:focus-within > button, .mega.is-open > button { background:#f8fafc; border-color:#bcc9d6; }
      .mega:hover > button::after, .mega:focus-within > button::after, .mega.is-open > button::after { transform:translateY(1px) rotate(225deg); opacity:1; }
      .mega-panel { display:none; position:absolute; right:0; top:calc(100% + 8px); z-index:1000; width:min(920px, calc(100vw - 32px)); max-height:min(520px, 72vh); overflow:auto; background:#fff; border:1px solid #d0d7de; border-radius:8px; box-shadow:0 16px 40px rgba(15,23,42,.12); padding:18px; grid-template-columns:repeat(3,minmax(0,1fr)); gap:16px; }
      .mega:hover .mega-panel, .mega:focus-within .mega-panel, .mega.is-open .mega-panel { display:grid; }
      .mega-group h3 { margin:0 0 8px; font-size:14px; color:#475467; }
      .mega-group a { display:block; color:#1f2933; text-decoration:none; padding:4px 0; }
      .mega-group a:hover { text-decoration:underline; }
      .translate-widget { position:relative; min-width:44px; flex:0 0 auto; }
      .translate-toggle { border:1px solid #d0d7de; border-radius:8px; background:#fff; min-width:44px; height:34px; padding:0 9px; display:inline-flex; align-items:center; justify-content:center; gap:5px; cursor:pointer; font-size:16px; line-height:1; box-shadow:0 1px 2px rgba(15,23,42,.04); transition:background-color .16s ease-in-out, border-color .16s ease-in-out, transform .16s ease-in-out; }
      .translate-toggle::after { content:""; width:5px; height:5px; border-right:1.6px solid #475467; border-bottom:1.6px solid #475467; transform:translateY(-1px) rotate(45deg); transition:transform .18s ease-in-out; }
      .translate-widget.is-open .translate-toggle::after { transform:translateY(1px) rotate(225deg); }
      .translate-toggle:hover { background:#f8fafc; border-color:#bcc9d6; transform:translateY(-1px); }
      .translate-menu { display:none; position:absolute; right:0; top:calc(100% + 8px); z-index:1100; width:180px; max-height:min(320px, 58vh); overflow:auto; padding:8px; border:1px solid #d0d7de; border-radius:10px; background:#fff; box-shadow:0 16px 40px rgba(15,23,42,.14); }
      .translate-widget.is-open .translate-menu { display:grid; gap:4px; }
      .translate-option { border:0; background:transparent; border-radius:8px; padding:7px 8px; display:flex; align-items:center; gap:8px; color:#1f2933; cursor:pointer; text-align:left; font-size:13px; }
      .translate-option:hover { background:#f8fafc; }
      .translate-flag { width:22px; text-align:center; font-size:17px; line-height:1; }
      .translate-native { position:absolute; width:1px; height:1px; overflow:hidden; opacity:0; pointer-events:none; }
      body > .skiptranslate, iframe.skiptranslate { display:none !important; }
      body { top:0 !important; }
      .site-footer { border-top:1px solid #d8dee6; background:linear-gradient(180deg,#f8fafc 0%,#eef4f8 100%); margin-top:32px; }
      .footer-inner { width:var(--shell-width); box-sizing:border-box; margin:0 auto; padding:30px var(--page-gutter) 18px; }
      .footer-grid { display:grid; grid-template-columns:minmax(260px,1.25fr) repeat(3,minmax(180px,1fr)); gap:24px; align-items:start; }
      .footer-logo { display:inline-flex; align-items:center; color:#1f2933; font-weight:800; font-size:20px; text-decoration:none; margin-bottom:10px; }
      .footer-logo .brand-mark { width:34px; height:34px; flex-basis:34px; }
      .footer-brand p { color:#475467; line-height:1.55; margin:0 0 10px; }
      .footer-disclaimer { font-size:13px; }
      .footer-col h2 { margin:0 0 12px; font-size:13px; color:#1f2933; text-transform:uppercase; letter-spacing:.04em; }
      .footer-links { display:flex; flex-direction:column; gap:8px; }
      .footer-pair-links { display:grid; grid-template-columns:repeat(auto-fit,minmax(112px,1fr)); gap:7px; }
      .footer-pair-links a { display:block; border:1px solid #dfe7ef; border-radius:999px; background:rgba(255,255,255,.72); color:#344054; text-decoration:none; font-size:13px; line-height:1; padding:8px 10px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; transition:background-color .16s ease-in-out, border-color .16s ease-in-out, transform .16s ease-in-out; }
      .footer-pair-links a:hover { color:#111827; border-color:#bcc9d6; background:#fff; transform:translateY(-1px); }
      .footer-tool-links a { position:relative; color:#475467; text-decoration:none; font-size:14px; padding-left:15px; line-height:1.35; }
      .footer-tool-links a::before { content:""; position:absolute; left:0; top:.55em; width:5px; height:5px; border-radius:50%; background:#38bdf8; }
      .footer-tool-links a:hover { color:#1f2933; text-decoration:underline; }
      .footer-bottom { border-top:1px solid #e5e7eb; margin-top:24px; padding-top:14px; color:#667085; display:flex; justify-content:space-between; gap:16px; flex-wrap:wrap; font-size:13px; }
      @media (hover:none) {
        .header-pair-group:hover .header-pair-submenu, .header-pair-group:focus-within .header-pair-submenu, .mega:hover .mega-panel, .mega:focus-within .mega-panel { display:none; }
        .header-pair-group.is-open .header-pair-submenu { display:flex; flex-direction:column; gap:6px; }
        .mega.is-open .mega-panel { display:grid; }
      }
      @media (max-width:1180px){
        .site-nav { gap:10px; }
        .header-pairs { order:3; flex:1 1 100%; margin-left:0; flex-wrap:wrap; overflow:visible; padding-bottom:2px; }
        .header-pairs a, .header-pair-group > button, .header-pairs-label { flex:0 0 auto; }
        .mega::after { left:0; right:auto; width:min(560px, calc(100vw - 32px)); }
        .mega-panel { left:0; right:auto; width:min(560px, calc(100vw - 32px)); grid-template-columns:repeat(2,minmax(0,1fr)); }
        #quick-converter-panel { grid-template-columns:1fr; }
        #quick-converter-panel .converter-controls { margin-bottom:10px; }
        #quick-converter-panel #quick-converter-results { width:100%; }
        .footer-grid { grid-template-columns:1.2fr 1fr 1fr; }
      }
      @media (max-width:980px){
        h1{font-size:28px}
        h2{font-size:19px}
        .topbar{display:block}
        .actions{justify-content:flex-start;margin-top:10px}
        .section-head{align-items:flex-start}
        .section-head > div{min-width:0; flex:1 1 100%}
        .note-grid,.mover-grid,.explain-grid{grid-template-columns:1fr}
        #quick-converter-panel .converter-controls{grid-template-columns:1fr 1fr 1fr}
        .converter-panel .converter-panel-head{grid-template-columns:1fr auto}
        .converter-panel .converter-controls{grid-column:1 / -1; grid-template-columns:1fr 1fr; width:100%; padding-top:0}
        .footer-grid{grid-template-columns:1fr 1fr}
      }
      @media (max-width:760px){
        main{padding:16px var(--page-gutter) 42px}
        h1{font-size:26px}
        .actions a{margin:0}
        .header-pairs{display:none}
        .mega-panel{grid-template-columns:1fr;left:auto;right:0;max-height:70vh;overflow:auto}
        .quickbar-inner{padding:8px var(--page-gutter)}
        #quick-converter-panel{display:block;padding:12px}
        #quick-converter-panel .converter-controls{display:grid;grid-template-columns:1fr;margin-bottom:10px}
        .converter-panel{bottom:0;width:calc(100vw - 16px);max-height:min(420px,calc(100vh - 24px));overflow:auto;padding:12px}
        .converter-panel-head{align-items:center}
        .converter-panel .converter-panel-head{grid-template-columns:1fr auto}
        .converter-panel h2,.converter-inline h2{margin-top:0}
        .converter-controls,.converter-panel .converter-controls{grid-template-columns:1fr;max-width:none}
        .converter-panel .converter-results{grid-template-columns:repeat(2,minmax(0,1fr))}
        .footer-grid{grid-template-columns:1fr}
      }
      @media (max-width:520px){
        :root{--page-gutter:12px}
        h1{font-size:24px}
        h2{font-size:18px}
        .brand-name{font-size:16px}
        .brand-mark{width:28px;height:28px;flex-basis:28px}
        .site-nav{padding:8px var(--page-gutter)}
        .mega > button{padding:7px 10px;font-size:13px}
        .translate-toggle{height:32px;min-width:40px}
        .chart-wrap{padding:8px}
        #home-chart{min-height:300px}
        .section-head label:has(#home-quote){width:100%;justify-content:space-between}
        .section-head .converter-select{width:96px}
        .converter-panel .converter-results{grid-template-columns:1fr}
        .converter-result strong{font-size:15px}
        table{min-width:640px}
      }
      @media (max-width:380px){
        .actions{gap:6px}
        .actions a{font-size:13px;padding:7px 9px}
        .mega > button{max-width:138px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
      }
    </style>
  </head>
  <body>
    <header class="site-header">
      <nav class="site-nav">
        <a class="brand" href="/">{{ brand_html|safe }}</a>
        <div class="header-pairs">
          {% if menu.active_header_links %}
            <span class="header-pairs-label">{{ menu.active_header_base }} pairs</span>
            {% for link in menu.active_header_links %}
              <a class="{% if link.active %}is-active{% endif %}" href="{{ link.href }}"{% if link.active %} aria-current="page"{% endif %}>{{ link.label }}</a>
            {% endfor %}
          {% else %}
            {% for group in menu.header_groups %}
              <div class="header-pair-group">
                <button type="button">{{ group.base }}</button>
                <div class="header-pair-submenu">
                  {% for link in group.links %}
                    <a href="{{ link.href }}">{{ link.label }}</a>
                  {% endfor %}
                </div>
              </div>
            {% endfor %}
          {% endif %}
        </div>
        <div class="mega">
          <button type="button">Currency pairs</button>
          <div class="mega-panel">
            {% for group in menu.groups %}
              <div class="mega-group">
                <h3>{{ group.title }}</h3>
                {% for link in group.links %}
                  <a href="{{ link.href }}">{{ link.label }}</a>
                {% endfor %}
              </div>
            {% endfor %}
          </div>
        </div>
        <div class="translate-widget" aria-label="Translate page">
          <button class="translate-toggle" type="button" aria-label="Translate page" aria-expanded="false">🌐</button>
          <div class="translate-menu" role="menu">
            <button class="translate-option" type="button" data-lang="en"><span class="translate-flag">🇺🇸</span><span>English</span></button>
            <button class="translate-option" type="button" data-lang="vi"><span class="translate-flag">🇻🇳</span><span>Tiếng Việt</span></button>
            <button class="translate-option" type="button" data-lang="th"><span class="translate-flag">🇹🇭</span><span>ไทย</span></button>
            <button class="translate-option" type="button" data-lang="ja"><span class="translate-flag">🇯🇵</span><span>日本語</span></button>
            <button class="translate-option" type="button" data-lang="ko"><span class="translate-flag">🇰🇷</span><span>한국어</span></button>
            <button class="translate-option" type="button" data-lang="zh-CN"><span class="translate-flag">🇨🇳</span><span>中文</span></button>
          </div>
          <div id="google_translate_element" class="translate-native"></div>
        </div>
      </nav>
    </header>
    <div class="quickbar">
      <div class="quickbar-inner">
        <section id="quick-converter-panel" class="converter-inline">
          <div class="converter-panel-head">
            <div>
              <div class="converter-title-row">
                <h2>Currency converter</h2>
                <span class="converter-updated">Updated {{ model.updated or 'when data is available' }}</span>
              </div>
              <p class="muted">Convert a major currency into popular currencies using the latest stored rates.</p>
            </div>
          </div>
          <div class="converter-controls">
            <label>Amount
              <input id="quick-converter-amount" type="number" value="1" min="0" step="any">
            </label>
            <label>From
              <select id="quick-converter-base">
                {% for option in model.converter_bases %}
                  <option value="{{ option }}" {% if option == 'USD' %}selected{% endif %}>{{ option }}</option>
                {% endfor %}
              </select>
            </label>
            <label>To
              <select id="quick-converter-target">
                {% for option in model.converter_targets %}
                  <option value="{{ option }}" {% if option == 'VND' %}selected{% endif %}>{{ option }}</option>
                {% endfor %}
              </select>
            </label>
          </div>
          <div id="quick-converter-results" class="converter-results"></div>
        </section>
      </div>
    </div>
    <main>
      <div class="topbar">
        <header>
          <h1>Exchange Rates Dashboard</h1>
          <p class="muted">Compare popular currencies across major quote currencies and VND. Updated {{ model.updated or 'when data is available' }}.</p>
        </header>
        <nav class="actions">
          <a href="/chart">Pair chart tool</a>
          <a href="/usd-vnd">USD/VND page</a>
        </nav>
      </div>

      <section>
        <div class="section-head">
          <div>
            <h2>Major currencies vs <span id="home-quote-label">{{ model.quote }}</span>, normalized</h2>
            <p class="muted">Each line starts at 100, so the chart compares relative movement instead of raw exchange-rate size.</p>
          </div>
          <label>Quote
            <select id="home-quote">
              {% for option in model.quote_options %}
                <option value="{{ option }}" {% if option == model.quote %}selected{% endif %}>{{ option }}</option>
              {% endfor %}
            </select>
          </label>
        </div>
        <div class="chart-wrap">
          <canvas id="home-chart" height="360"></canvas>
          <div id="home-chart-status" class="chart-status">Loading chart...</div>
        </div>
        <div id="home-chart-desc" class="chart-desc">{{ model.chart_description|safe }}</div>
      </section>

      <section>
        <h2>Currency pair movement</h2>
        <p class="muted">Quick labels for pairs with available history, grouped by their current move across the stored data window.</p>
        <div class="mover-grid">
          <div class="mover-list">
            <h3>Up pairs</h3>
            {% for item in model.pair_movers.up %}
              <a class="mover-item" href="{{ item.href }}">
                <span><span class="mover-pair">{{ item.label }}</span><span class="mover-rate">{{ item.rate }}</span></span>
                <span class="mover-change up">{{ item.change_label }}</span>
              </a>
            {% else %}
              <span class="mover-item"><span>No rising pairs yet</span><span class="mover-change flat">-</span></span>
            {% endfor %}
          </div>
          <div class="mover-list">
            <h3>Down pairs</h3>
            {% for item in model.pair_movers.down %}
              <a class="mover-item" href="{{ item.href }}">
                <span><span class="mover-pair">{{ item.label }}</span><span class="mover-rate">{{ item.rate }}</span></span>
                <span class="mover-change down">{{ item.change_label }}</span>
              </a>
            {% else %}
              <span class="mover-item"><span>No falling pairs yet</span><span class="mover-change flat">-</span></span>
            {% endfor %}
          </div>
          <div class="mover-list">
            <h3>Mostly flat</h3>
            {% for item in model.pair_movers.flat %}
              <a class="mover-item" href="{{ item.href }}">
                <span><span class="mover-pair">{{ item.label }}</span><span class="mover-rate">{{ item.rate }}</span></span>
                <span class="mover-change flat">{{ item.change_label }}</span>
              </a>
            {% else %}
              <span class="mover-item"><span>No flat pairs yet</span><span class="mover-change flat">-</span></span>
            {% endfor %}
          </div>
        </div>
      </section>

      <section id="converter-panel" class="converter-panel">
        <div class="converter-panel-head">
          <div>
            <div class="converter-title-row">
              <h2>Currency converter</h2>
              <span class="converter-updated">Updated {{ model.updated or 'when data is available' }}</span>
            </div>
            <p class="muted">Convert a major currency into popular currencies using the latest stored rates.</p>
          </div>
          <div class="converter-controls">
            <label>Amount
              <input id="converter-amount" type="number" value="1" min="0" step="any">
            </label>
            <label>From
              <select id="converter-base">
                {% for option in model.converter_bases %}
                  <option value="{{ option }}" {% if option == 'USD' %}selected{% endif %}>{{ option }}</option>
                {% endfor %}
              </select>
            </label>
          </div>
          <button id="converter-close" class="converter-close" type="button" aria-label="Close converter"></button>
        </div>
        <div id="converter-results" class="converter-results"></div>
      </section>
      <button id="converter-open" class="converter-open" type="button">Open converter</button>

      <section>
        <h2>Popular currency comparison table</h2>
        <p class="muted">Each cell shows the value of 1 row currency in the column currency.</p>
        <div class="matrix-wrap">
          <table>
            <thead>
              <tr>
                <th>Currency</th>
                {% for column in model.columns %}
                  <th>{{ column }}</th>
                {% endfor %}
              </tr>
            </thead>
            <tbody>
              {% for row in model.rows %}
                <tr>
                  <td class="currency">{{ row.base }}</td>
                  {% for cell in row.cells %}
                    <td>{% if cell.value %}<a href="{{ cell.href }}">{{ cell.value }}</a>{% else %}-{% endif %}</td>
                  {% endfor %}
                </tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </section>

      <section class="note-grid">
        <div class="note">
          <h3>For quick conversion</h3>
          <p class="muted">Use the table to jump from common currencies to dedicated pair pages with charts and conversion amounts.</p>
        </div>
        <div class="note">
          <h3>For trend checks</h3>
          <p class="muted">Use the normalized chart to compare relative movement against your selected quote currency without large rates dominating the scale.</p>
        </div>
        <div class="note">
          <h3>For dedicated pair pages</h3>
          <p class="muted">Every linked pair can open a dedicated page with a converter, chart, statistics, FAQ, and structured data.</p>
        </div>
      </section>

      <section>
        <h2>How this exchange-rate dashboard should be read</h2>
        <div class="explain-grid">
          <div class="explain-block">
            <h3>Indexed performance, not raw price</h3>
            <p class="muted">The main dashboard uses an indexed chart, a common finance technique also used for stocks, ETFs, commodities, and currency baskets. By rebasing each line to 100, the chart shows percentage movement rather than raw exchange-rate size.</p>
            <p class="muted">This matters because raw exchange rates are not comparable on one axis. A VND rate may be in the tens of thousands, while EUR or GBP may be below 2. Indexing makes the relative move visible without letting the largest number dominate the chart.</p>
          </div>
          <div class="explain-block">
            <h3>Relative strength against the quote</h3>
            <p class="muted">The selected quote currency is the benchmark. If the dashboard is set to USD, a line above 100 means that currency has gained against USD since the first point in the data window. A line below 100 means it has lost ground against USD.</p>
            <p class="muted">This view is useful for spotting broad currency pressure. For example, if several Asian currencies fall below 100 against USD at the same time, the chart may be showing USD strength rather than an isolated move in one currency.</p>
          </div>
          <div class="explain-block">
            <h3>Pair pages show the actual rate</h3>
            <p class="muted">Dedicated pair pages such as USD to VND or EUR to USD use raw exchange rates, because a single pair does not need normalization. Those pages are better for conversion, high-low-average checks, and understanding exactly how many units of the target currency one base currency buys.</p>
          </div>
          <div class="explain-block">
            <h3>Informational mid-market data</h3>
            <p class="muted">Rates on this site are designed for comparison and reference. Banks, card networks, remittance providers, brokers, and exchanges can apply their own spreads, fees, bid/ask prices, settlement timing, and rounding rules. Always compare provider quotes before sending money or making financial decisions.</p>
          </div>
        </div>
      </section>
    </main>
    {{ footer_html|safe }}
    <script>
      const latestUsdTable = {{ model.latest_usd_table|tojson }};
      const converterTargets = {{ model.converter_targets|tojson }};
      const chartBases = {{ model.chart_bases|tojson }};
      const palette = ['#0b7cff', '#16a34a', '#e8590c', '#7c6bb0', '#0891b2', '#dc2626'];
      const lineStyles = [
        { borderDash: [], borderCapStyle: 'butt' },
        { borderDash: [], borderCapStyle: 'butt' },
        { borderDash: [6, 4], borderCapStyle: 'round' },
        { borderDash: [], borderCapStyle: 'butt' },
        { borderDash: [2, 4], borderCapStyle: 'round' },
        { borderDash: [], borderCapStyle: 'butt' }
      ];
      function formatRate(value){
        const n = Number(value);
        if(!Number.isFinite(n)) return '-';
        if(n === 0) return '0';
        const abs = Math.abs(n);
        if(abs < 0.000001) return n.toExponential(6);
        if(abs < 1) return n.toFixed(8).replace(/0+$/, '').replace(/\.$/, '');
        if(abs < 1000) return n.toFixed(6).replace(/0+$/, '').replace(/\.$/, '');
        return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
      }
      function formatCompactRate(value){
        const n = Number(value);
        if(!Number.isFinite(n)) return '-';
        if(n === 0) return '0';
        const abs = Math.abs(n);
        if(abs < 0.000001) return n.toExponential(2);
        if(abs < 1) return n.toPrecision(5).replace(/0+$/, '').replace(/\.$/, '');
        if(abs < 1000) return n.toLocaleString(undefined, { maximumSignificantDigits: 6 });
        return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
      }
      function rateFromUsdTable(base, target){
        const basePerUsd = base === 'USD' ? 1 : latestUsdTable[base];
        const targetPerUsd = target === 'USD' ? 1 : latestUsdTable[target];
        if(!basePerUsd || !targetPerUsd) return null;
        return targetPerUsd / basePerUsd;
      }
      function closeEnhancedSelects(){
        document.querySelectorAll('.converter-select.is-open').forEach((wrap) => {
          wrap.classList.remove('is-open');
          const button = wrap.querySelector('.converter-select-button');
          if(button) button.setAttribute('aria-expanded', 'false');
        });
      }
      function syncEnhancedSelect(select){
        if(!select) return;
        const wrap = select.nextElementSibling;
        if(!wrap || !wrap.classList.contains('converter-select')) return;
        const label = select.options[select.selectedIndex]?.textContent || select.value;
        const text = wrap.querySelector('.converter-select-button span');
        if(text) text.textContent = label;
        wrap.querySelectorAll('.converter-select-option').forEach((option) => {
          const selected = option.dataset.value === select.value;
          option.classList.toggle('is-selected', selected);
          option.setAttribute('aria-selected', selected ? 'true' : 'false');
        });
      }
      function enhanceSelect(select){
        if(!select || select.dataset.enhanced === '1') return;
        select.dataset.enhanced = '1';
        select.classList.add('converter-select-native');
        const wrap = document.createElement('div');
        wrap.className = 'converter-select';
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'converter-select-button';
        button.setAttribute('aria-haspopup', 'listbox');
        button.setAttribute('aria-expanded', 'false');
        button.innerHTML = '<span></span>';
        const menu = document.createElement('div');
        menu.className = 'converter-select-menu';
        menu.setAttribute('role', 'listbox');
        Array.from(select.options).forEach((nativeOption) => {
          const option = document.createElement('button');
          option.type = 'button';
          option.className = 'converter-select-option';
          option.dataset.value = nativeOption.value;
          option.setAttribute('role', 'option');
          option.textContent = nativeOption.textContent;
          option.addEventListener('click', (event) => {
            event.stopPropagation();
            select.value = nativeOption.value;
            syncEnhancedSelect(select);
            select.dispatchEvent(new Event('change', { bubbles: true }));
            closeEnhancedSelects();
          });
          menu.appendChild(option);
        });
        button.addEventListener('click', (event) => {
          event.stopPropagation();
          const shouldOpen = !wrap.classList.contains('is-open');
          closeEnhancedSelects();
          wrap.classList.toggle('is-open', shouldOpen);
          button.setAttribute('aria-expanded', shouldOpen ? 'true' : 'false');
        });
        select.addEventListener('change', () => syncEnhancedSelect(select));
        wrap.appendChild(button);
        wrap.appendChild(menu);
        select.insertAdjacentElement('afterend', wrap);
        syncEnhancedSelect(select);
      }
      function initEnhancedConverterSelects(){
        ['home-quote', 'quick-converter-base', 'quick-converter-target', 'converter-base'].forEach((id) => {
          enhanceSelect(document.getElementById(id));
        });
        document.addEventListener('click', closeEnhancedSelects);
        document.addEventListener('keydown', (event) => {
          if(event.key === 'Escape') closeEnhancedSelects();
        });
      }
      function renderConverter(prefix = 'converter'){
        const amount = Number(document.getElementById(`${prefix}-amount`).value || 0);
        const base = document.getElementById(`${prefix}-base`).value;
        const targetSelect = document.getElementById(`${prefix}-target`);
        if(targetSelect.value === base) {
          targetSelect.value = converterTargets.find(target => target !== base) || targetSelect.value;
          syncEnhancedSelect(targetSelect);
        }
        const target = targetSelect.value;
        const rate = rateFromUsdTable(base, target);
        const converted = rate == null ? '-' : `${formatRate(amount * rate)} ${target}`;
        const href = `/${base.toLowerCase()}-${target.toLowerCase()}`;
        const html = `<a class="converter-result" href="${href}"><span>${amount || 0} ${base} to ${target}</span><strong>${converted}</strong></a>`;
        document.getElementById(`${prefix}-results`).innerHTML = html;
      }
      function renderAllConverter(){
        const amount = Number(document.getElementById('converter-amount').value || 0);
        const base = document.getElementById('converter-base').value;
        const html = converterTargets.filter(target => target !== base).map(target => {
          const rate = rateFromUsdTable(base, target);
          const converted = rate == null ? '-' : `${formatCompactRate(amount * rate)} ${target}`;
          const href = `/${base.toLowerCase()}-${target.toLowerCase()}`;
          return `<a class="converter-result" href="${href}"><span>${amount || 0} ${base} to ${target}</span><strong>${converted}</strong></a>`;
        }).join('');
        document.getElementById('converter-results').innerHTML = html;
      }
      function buildHomeChartData(nextSeries) {
        const allTimestamps = Array.from(new Set(nextSeries.flatMap(item => item.data.map(point => point.ts)))).sort((a, b) => a - b);
        const labels = allTimestamps.map(ts => new Date(ts * 1000).toLocaleString());
        const datasets = nextSeries.map((item, index) => {
          const byTs = new Map(item.data.map(point => [point.ts, point.value]));
          const color = palette[index % palette.length];
          const lineStyle = lineStyles[index % lineStyles.length];
          return {
            label: item.label,
            data: allTimestamps.map(ts => byTs.get(ts) ?? null),
            borderColor: color,
            backgroundColor: color,
            borderDash: lineStyle.borderDash,
            borderCapStyle: lineStyle.borderCapStyle,
            pointRadius: 0,
            pointHoverRadius: 3,
            borderWidth: 1.8,
            tension: 0.18,
            spanGaps: true
          };
        });
        return { labels, datasets };
      }
      const chartWrap = document.querySelector('.chart-wrap');
      const chartStatus = document.getElementById('home-chart-status');
      let homeChart = null;
      const chartOptions = {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        elements: { line: { borderJoinStyle: 'round' } },
        plugins: {
          legend: {
            position: 'top',
            align: 'start',
            labels: { usePointStyle: true, pointStyle: 'line', boxWidth: 28, boxHeight: 6, color: '#475467', padding: 14 }
          },
          tooltip: {
            callbacks: {
              label: context => `${context.dataset.label}: ${Number(context.parsed.y).toFixed(2)}`
            }
          }
        },
        scales: {
          x: { grid: { display: false }, border: { display: false }, ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 6, color: '#667085' } },
          y: { position: 'right', grid: { color: 'rgba(148, 163, 184, 0.16)', drawTicks: false }, border: { display: false }, ticks: { maxTicksLimit: 5, padding: 8, color: '#667085', callback: value => Number(value).toFixed(0) } }
        }
      };
      function setChartStatus(message){
        if(chartStatus) chartStatus.textContent = message;
      }
      function chartLoadDelay(index){
        if(index === 0) return 0;
        return 5000 + Math.floor(Math.random() * 5001);
      }
      function waitForChartDelay(ms, token){
        return new Promise((resolve) => {
          window.setTimeout(() => {
            resolve(token === chartLoadToken);
          }, ms);
        });
      }
      let chartLibraryPromise = null;
      function ensureChartLibrary(){
        if(typeof Chart !== 'undefined') return Promise.resolve();
        if(chartLibraryPromise) return chartLibraryPromise;
        chartLibraryPromise = new Promise((resolve, reject) => {
          const script = document.createElement('script');
          script.src = 'https://cdn.jsdelivr.net/npm/chart.js';
          script.async = true;
          script.onload = resolve;
          script.onerror = () => reject(new Error('Chart.js failed to load'));
          document.head.appendChild(script);
        });
        return chartLibraryPromise;
      }
      let chartLoadToken = 0;
      async function loadHomeChart(quote){
        const token = ++chartLoadToken;
        const nextSeries = [];
        const bases = chartBases.filter(item => item !== quote);
        chartWrap.classList.remove('is-ready');
        setChartStatus('Loading chart 1 of ' + bases.length + '...');
        try {
          await ensureChartLibrary();
          if(token !== chartLoadToken) return;
          document.getElementById('home-quote-label').textContent = quote;
          for(let index = 0; index < bases.length; index += 1) {
            const base = bases[index];
            const shouldContinue = await waitForChartDelay(chartLoadDelay(index), token);
            if(!shouldContinue) return;
            setChartStatus('Loading chart ' + (index + 1) + ' of ' + bases.length + '...');
            const res = await fetch(`/api/home-chart?quote=${encodeURIComponent(quote)}&base=${encodeURIComponent(base)}`, { cache: 'no-store' });
            if(token !== chartLoadToken) return;
            if(!res.ok) continue;
            const data = await res.json();
            nextSeries.push(data.series);
            window.exchangeTrackEvent && window.exchangeTrackEvent('home_chart_series_loaded', {
              quote_currency: quote,
              base_currency: base,
              series_position: index + 1,
              page_path: location.pathname
            });
            document.getElementById('home-chart-desc').innerHTML = data.chart_description;
            const nextData = buildHomeChartData(nextSeries);
            if(!homeChart) {
              homeChart = new Chart(document.getElementById('home-chart').getContext('2d'), {
                type: 'line',
                data: nextData,
                options: chartOptions
              });
            } else {
              homeChart.data.labels = nextData.labels;
              homeChart.data.datasets = nextData.datasets;
              homeChart.update();
            }
            chartWrap.classList.add('is-ready');
          }
          if(!nextSeries.length) throw new Error('No chart series loaded');
        } catch (error) {
          console.error('Failed to load home chart', error);
          setChartStatus('Chart data unavailable. The table below is still available.');
        }
      }
      document.getElementById('home-quote').addEventListener('change', (event) => {
        loadHomeChart(event.target.value);
      });
      function scheduleHomeChartLoad(){
        const quote = document.getElementById('home-quote').value;
        const start = () => loadHomeChart(quote);
        if('requestIdleCallback' in window) {
          window.requestIdleCallback(start, { timeout: 3000 });
        } else {
          window.setTimeout(start, 1200);
        }
      }
      document.getElementById('converter-amount').addEventListener('input', renderAllConverter);
      document.getElementById('converter-base').addEventListener('change', renderAllConverter);
      document.getElementById('quick-converter-amount').addEventListener('input', () => renderConverter('quick-converter'));
      document.getElementById('quick-converter-base').addEventListener('change', () => renderConverter('quick-converter'));
      document.getElementById('quick-converter-target').addEventListener('change', () => renderConverter('quick-converter'));
      const converterPanel = document.getElementById('converter-panel');
      const converterOpen = document.getElementById('converter-open');
      function setConverterVisible(visible){
        converterPanel.classList.toggle('is-hidden', !visible);
        converterOpen.classList.toggle('is-visible', !visible);
        localStorage.setItem('exchangeConverterClosed', visible ? '0' : '1');
      }
      document.getElementById('converter-close').addEventListener('click', () => setConverterVisible(false));
      converterOpen.addEventListener('click', () => setConverterVisible(true));
      if(localStorage.getItem('exchangeConverterClosed') === '1') {
        setConverterVisible(false);
      }
      initEnhancedConverterSelects();
      scheduleHomeChartLoad();
      renderAllConverter();
      renderConverter('quick-converter');
    </script>
    <script>
      function closeHeaderMenus() {
        document.querySelectorAll('.mega.is-open, .header-pair-group.is-open').forEach(item => {
          item.classList.remove('is-open');
          const button = item.querySelector('button');
          if(button) button.setAttribute('aria-expanded', 'false');
        });
      }
      function initHeaderMenus() {
        document.querySelectorAll('.mega > button, .header-pair-group > button').forEach(button => {
          if(button.dataset.menuReady === '1') return;
          button.dataset.menuReady = '1';
          button.setAttribute('aria-expanded', 'false');
          button.addEventListener('click', event => {
            event.preventDefault();
            event.stopPropagation();
            const menu = button.parentElement;
            const open = !menu.classList.contains('is-open');
            closeHeaderMenus();
            if(!open) {
              button.blur();
              return;
            }
            menu.classList.toggle('is-open', open);
            button.setAttribute('aria-expanded', open ? 'true' : 'false');
          });
        });
        document.querySelectorAll('.mega-panel, .header-pair-submenu').forEach(panel => {
          panel.addEventListener('click', event => event.stopPropagation());
        });
        document.addEventListener('click', closeHeaderMenus);
        document.addEventListener('keydown', event => {
          if(event.key === 'Escape') closeHeaderMenus();
        });
      }
      function setTranslateCookie(value) {
        const maxAge = value ? '; max-age=31536000' : '; expires=Thu, 01 Jan 1970 00:00:00 GMT';
        document.cookie = `googtrans=${value || ''}; path=/${maxAge}`;
        if (location.hostname.includes('.')) {
          document.cookie = `googtrans=${value || ''}; path=/; domain=.${location.hostname}${maxAge}`;
        }
      }
      function applyTranslation(lang) {
        const combo = document.querySelector('.goog-te-combo');
        if (lang === 'en') {
          setTranslateCookie('');
          location.reload();
          return;
        }
        setTranslateCookie(`/en/${lang}`);
        if (combo) {
          combo.value = lang;
          combo.dispatchEvent(new Event('change'));
        } else {
          location.reload();
        }
      }
      function initTranslateMenu() {
        document.querySelectorAll('.translate-widget').forEach(widget => {
          if (widget.dataset.translateReady === '1') return;
          widget.dataset.translateReady = '1';
          const toggle = widget.querySelector('.translate-toggle');
          toggle.addEventListener('click', event => {
            event.stopPropagation();
            const open = !widget.classList.contains('is-open');
            document.querySelectorAll('.translate-widget.is-open').forEach(item => item.classList.remove('is-open'));
            widget.classList.toggle('is-open', open);
            toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
          });
          widget.querySelectorAll('[data-lang]').forEach(button => {
            button.addEventListener('click', () => applyTranslation(button.dataset.lang));
          });
        });
        document.addEventListener('click', () => {
          document.querySelectorAll('.translate-widget.is-open').forEach(widget => {
            widget.classList.remove('is-open');
            const toggle = widget.querySelector('.translate-toggle');
            if (toggle) toggle.setAttribute('aria-expanded', 'false');
          });
        });
      }
      function googleTranslateElementInit() {
        new google.translate.TranslateElement({ pageLanguage: 'en', autoDisplay: false, layout: google.translate.TranslateElement.InlineLayout.HORIZONTAL }, 'google_translate_element');
        initTranslateMenu();
      }
      document.addEventListener('DOMContentLoaded', initHeaderMenus);
      document.addEventListener('DOMContentLoaded', initTranslateMenu);
    </script>
    <script src="https://translate.google.com/translate_a/element.js?cb=googleTranslateElementInit"></script>
  </body>
</html>
"""


PAIR_PAGE_TEMPLATE = """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{{ title }}</title>
    <meta name="description" content="{{ description }}" />
    <meta name="robots" content="index,follow,max-snippet:-1,max-image-preview:large,max-video-preview:-1" />
    <link rel="canonical" href="{{ canonical_url }}" />
    <meta property="og:type" content="website" />
    <meta property="og:site_name" content="ExchangeHub" />
    <meta property="og:title" content="{{ title }}" />
    <meta property="og:description" content="{{ description }}" />
    <meta property="og:url" content="{{ canonical_url }}" />
    <meta property="og:image" content="{{ canonical_url.rsplit('/', 1)[0] }}/static/exchangehub-logo.svg" />
    <meta name="twitter:card" content="summary" />
    <meta name="twitter:title" content="{{ title }}" />
    <meta name="twitter:description" content="{{ description }}" />
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script type="application/ld+json">{{ schema_json|safe }}</script>
    {{ google_tag_html|safe }}
    <style>
      :root { --page-gutter: clamp(12px, 1.6vw, 26px); --shell-width: 100%; }
      body { font-family: Arial, sans-serif; margin: 0; color: #1f2933; }
      main { width:var(--shell-width); box-sizing:border-box; margin:0 auto; padding:24px var(--page-gutter) 48px; }
      h1 { margin: 0 0 8px; font-size: 34px; }
      h2 { margin: 28px 0 12px; font-size: 22px; }
      .lede { font-size: 22px; margin: 0 0 6px; }
      .muted { color: #667085; margin-top: 0; }
      .pair-intro { margin:18px 0 0; border:1px solid #e5e7eb; border-radius:8px; background:#f8fafc; padding:14px; color:#475467; line-height:1.55; }
      .converter-title-row { display:flex; align-items:baseline; gap:10px; flex-wrap:wrap; }
      .converter-updated { color:#667085; font-size:12px; white-space:nowrap; }
      .converter-table-wrap { overflow-x:auto; border:1px solid #e5e7eb; border-radius:8px; }
      table { width: 100%; border-collapse: collapse; }
      th, td { padding: 10px; border-bottom: 1px solid #e5e7eb; text-align: left; }
      th { background: #f8fafc; }
      .chart-wrap { height:min(42vh, 420px); min-height:280px; border:1px solid #e5e7eb; border-radius:8px; padding:clamp(10px, 1vw, 16px); }
      .stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
      .stat { border: 1px solid #e5e7eb; padding: 12px; border-radius: 6px; }
      .stat span { display: block; color: #667085; font-size: 13px; }
      .stat strong { display: block; margin-top: 4px; font-size: 18px; }
      .mover-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; }
      .mover-list { border:1px solid #e5e7eb; border-radius:8px; overflow:hidden; background:#fff; }
      .mover-list h3 { margin:0; padding:10px 12px; font-size:15px; background:#f8fafc; border-bottom:1px solid #e5e7eb; }
      .mover-item { display:grid; grid-template-columns:minmax(76px,1fr) auto; gap:10px; align-items:center; padding:9px 12px; color:#1f2933; text-decoration:none; border-bottom:1px solid #eef2f7; }
      .mover-item:last-child { border-bottom:0; }
      .mover-item:hover { background:#f8fafc; }
      .mover-pair { font-weight:700; }
      .mover-rate { display:block; margin-top:2px; color:#667085; font-size:12px; font-weight:400; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
      .mover-change { font-weight:700; white-space:nowrap; }
      .mover-change.up { color:#16a34a; }
      .mover-change.down { color:#dc2626; }
      .mover-change.flat { color:#667085; }
      .insight-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:18px; }
      .insight { border-top:1px solid #e5e7eb; padding-top:16px; }
      .insight h3 { margin:0 0 8px; font-size:18px; }
      .context-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:14px; }
      .context-card { border:1px solid #e5e7eb; border-radius:8px; padding:14px; background:#fff; }
      .context-card h3 { margin:0 0 8px; font-size:17px; }
      .context-card p { margin:0; color:#475467; line-height:1.55; }
      .faq h3 { margin-bottom: 4px; }
      .site-header { border-bottom:1px solid #e5e7eb; background:#fff; position:sticky; top:0; z-index:10; }
      .site-nav { width:var(--shell-width); box-sizing:border-box; margin:0 auto; padding:12px var(--page-gutter); display:flex; align-items:center; justify-content:space-between; gap:16px; }
      .brand { font-weight:800; color:#1f2933; text-decoration:none; }
      .brand-lockup { display:inline-flex; align-items:center; gap:9px; white-space:nowrap; }
      .brand-mark { width:32px; height:32px; display:block; flex:0 0 32px; }
      .brand-name { letter-spacing:0; }
      .header-pairs { display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-left:auto; }
      .header-pairs a, .header-pair-group > button, .header-pairs-label { color:#475467; text-decoration:none; border:1px solid #e5e7eb; border-radius:999px; padding:6px 9px; font-size:13px; line-height:1; background:#fff; }
      .header-pairs a:hover, .header-pair-group > button:hover { color:#1f2933; border-color:#d0d7de; background:#f8fafc; }
      .header-pairs a.is-active { color:#111827; border-color:#f0b90b; background:#fff7d6; font-weight:700; box-shadow:inset 0 0 0 1px rgba(240,185,11,.28); }
      .header-pairs-label { color:#1f2933; font-weight:700; }
      .header-pair-group { position:relative; }
      .header-pair-group::after { content:""; display:none; position:absolute; left:0; top:100%; width:100%; height:10px; }
      .header-pair-group:hover::after, .header-pair-group:focus-within::after { display:block; }
      .header-pair-group > button { cursor:pointer; display:inline-flex; align-items:center; gap:6px; transition:background-color .16s ease-in-out, border-color .16s ease-in-out, color .16s ease-in-out; }
      .header-pair-group > button::after { content:""; width:6px; height:6px; border-right:1.8px solid currentColor; border-bottom:1.8px solid currentColor; transform:translateY(-2px) rotate(45deg); opacity:.72; transition:transform .18s ease-in-out, opacity .18s ease-in-out; }
      .header-pair-group:hover > button::after, .header-pair-group:focus-within > button::after, .header-pair-group.is-open > button::after { transform:translateY(1px) rotate(225deg); opacity:1; }
      .header-pair-submenu { display:none; position:absolute; left:0; top:calc(100% + 8px); z-index:1001; min-width:138px; max-height:min(320px, 58vh); overflow:auto; background:#fff; border:1px solid #d0d7de; border-radius:8px; box-shadow:0 12px 28px rgba(15,23,42,.12); padding:8px; }
      .header-pair-group:hover .header-pair-submenu, .header-pair-group:focus-within .header-pair-submenu, .header-pair-group.is-open .header-pair-submenu { display:flex; flex-direction:column; gap:6px; }
      .header-pair-submenu a { border-radius:6px; border:0; padding:7px 8px; white-space:nowrap; }
      .mega { position:relative; }
      .mega::after { content:""; display:none; position:absolute; right:0; top:100%; width:min(920px, calc(100vw - 32px)); height:10px; }
      .mega:hover::after, .mega:focus-within::after, .mega.is-open::after { display:block; }
      .mega > button { border:1px solid #d0d7de; background:#fff; border-radius:8px; padding:8px 12px; cursor:pointer; display:inline-flex; align-items:center; gap:8px; transition:background-color .16s ease-in-out, border-color .16s ease-in-out, color .16s ease-in-out; }
      .mega > button::after { content:""; width:7px; height:7px; border-right:1.8px solid currentColor; border-bottom:1.8px solid currentColor; transform:translateY(-2px) rotate(45deg); opacity:.72; transition:transform .18s ease-in-out, opacity .18s ease-in-out; }
      .mega:hover > button, .mega:focus-within > button, .mega.is-open > button { background:#f8fafc; border-color:#bcc9d6; }
      .mega:hover > button::after, .mega:focus-within > button::after, .mega.is-open > button::after { transform:translateY(1px) rotate(225deg); opacity:1; }
      .mega-panel { display:none; position:absolute; right:0; top:calc(100% + 8px); z-index:1000; width:min(920px, calc(100vw - 32px)); max-height:min(520px, 72vh); overflow:auto; background:#fff; border:1px solid #d0d7de; border-radius:8px; box-shadow:0 16px 40px rgba(15,23,42,.12); padding:18px; grid-template-columns:repeat(3,minmax(0,1fr)); gap:16px; }
      .mega:hover .mega-panel, .mega:focus-within .mega-panel, .mega.is-open .mega-panel { display:grid; }
      .mega-group h3 { margin:0 0 8px; font-size:14px; color:#475467; }
      .mega-group a { display:block; color:#1f2933; text-decoration:none; padding:4px 0; }
      .mega-group a:hover { text-decoration:underline; }
      .translate-widget { position:relative; min-width:40px; }
      .translate-toggle { border:1px solid #d0d7de; border-radius:999px; background:#fff; width:42px; height:34px; display:inline-flex; align-items:center; justify-content:center; gap:3px; cursor:pointer; font-size:17px; line-height:1; box-shadow:0 1px 2px rgba(15,23,42,.04); transition:background-color .16s ease-in-out, border-color .16s ease-in-out, transform .16s ease-in-out; }
      .translate-toggle::after { content:""; width:5px; height:5px; border-right:1.6px solid #475467; border-bottom:1.6px solid #475467; transform:translateY(-1px) rotate(45deg); transition:transform .18s ease-in-out; }
      .translate-widget.is-open .translate-toggle::after { transform:translateY(1px) rotate(225deg); }
      .translate-toggle:hover { background:#f8fafc; border-color:#bcc9d6; transform:translateY(-1px); }
      .translate-menu { display:none; position:absolute; right:0; top:calc(100% + 8px); z-index:1100; width:180px; max-height:min(320px, 58vh); overflow:auto; padding:8px; border:1px solid #d0d7de; border-radius:10px; background:#fff; box-shadow:0 16px 40px rgba(15,23,42,.14); }
      .translate-widget.is-open .translate-menu { display:grid; gap:4px; }
      .translate-option { border:0; background:transparent; border-radius:8px; padding:7px 8px; display:flex; align-items:center; gap:8px; color:#1f2933; cursor:pointer; text-align:left; font-size:13px; }
      .translate-option:hover { background:#f8fafc; }
      .translate-flag { width:22px; text-align:center; font-size:17px; line-height:1; }
      .translate-native { position:absolute; width:1px; height:1px; overflow:hidden; opacity:0; pointer-events:none; }
      body > .skiptranslate, iframe.skiptranslate { display:none !important; }
      body { top:0 !important; }
      .site-footer { border-top:1px solid #d8dee6; background:linear-gradient(180deg,#f8fafc 0%,#eef4f8 100%); margin-top:32px; }
      .footer-inner { width:var(--shell-width); box-sizing:border-box; margin:0 auto; padding:30px var(--page-gutter) 18px; }
      .footer-grid { display:grid; grid-template-columns:minmax(260px,1.25fr) repeat(3,minmax(180px,1fr)); gap:24px; align-items:start; }
      .footer-logo { display:inline-flex; align-items:center; color:#1f2933; font-weight:800; font-size:20px; text-decoration:none; margin-bottom:10px; }
      .footer-logo .brand-mark { width:34px; height:34px; flex-basis:34px; }
      .footer-brand p { color:#475467; line-height:1.55; margin:0 0 10px; }
      .footer-disclaimer { font-size:13px; }
      .footer-col h2 { margin:0 0 12px; font-size:13px; color:#1f2933; text-transform:uppercase; letter-spacing:.04em; }
      .footer-links { display:flex; flex-direction:column; gap:8px; }
      .footer-pair-links { display:grid; grid-template-columns:repeat(auto-fit,minmax(112px,1fr)); gap:7px; }
      .footer-pair-links a { display:block; border:1px solid #dfe7ef; border-radius:999px; background:rgba(255,255,255,.72); color:#344054; text-decoration:none; font-size:13px; line-height:1; padding:8px 10px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; transition:background-color .16s ease-in-out, border-color .16s ease-in-out, transform .16s ease-in-out; }
      .footer-pair-links a:hover { color:#111827; border-color:#bcc9d6; background:#fff; transform:translateY(-1px); }
      .footer-tool-links a { position:relative; color:#475467; text-decoration:none; font-size:14px; padding-left:15px; line-height:1.35; }
      .footer-tool-links a::before { content:""; position:absolute; left:0; top:.55em; width:5px; height:5px; border-radius:50%; background:#38bdf8; }
      .footer-tool-links a:hover { color:#1f2933; text-decoration:underline; }
      .footer-bottom { border-top:1px solid #e5e7eb; margin-top:24px; padding-top:14px; color:#667085; display:flex; justify-content:space-between; gap:16px; flex-wrap:wrap; font-size:13px; }
      @media (hover:none) {
        .header-pair-group:hover .header-pair-submenu, .header-pair-group:focus-within .header-pair-submenu, .mega:hover .mega-panel, .mega:focus-within .mega-panel { display:none; }
        .header-pair-group.is-open .header-pair-submenu { display:flex; flex-direction:column; gap:6px; }
        .mega.is-open .mega-panel { display:grid; }
      }
      @media (max-width: 1180px) {
        .header-pairs { order:3; flex:1 1 100%; margin-left:0; flex-wrap:wrap; overflow:visible; padding-bottom:2px; }
        .header-pairs a, .header-pair-group > button, .header-pairs-label { flex:0 0 auto; }
        .mega::after { left:0; right:auto; width:min(560px, calc(100vw - 32px)); }
        .mega-panel { left:0; right:auto; width:min(560px, calc(100vw - 32px)); grid-template-columns:repeat(2,minmax(0,1fr)); }
        .footer-grid { grid-template-columns:1.2fr 1fr 1fr; }
      }
      @media (max-width: 980px) {
        main { padding-top:18px; }
        h1 { font-size:30px; }
        h2 { font-size:20px; margin-top:24px; }
        .lede { font-size:20px; }
        .stats { grid-template-columns:repeat(2,minmax(0,1fr)); }
        .mover-grid, .insight-grid, .context-grid { grid-template-columns:1fr; }
        .footer-grid { grid-template-columns:1fr 1fr; }
      }
      @media (max-width: 760px) {
        main { padding:16px var(--page-gutter) 42px; }
        h1 { font-size:26px; }
        h2 { font-size:19px; }
        .lede { font-size:18px; }
        .header-pairs{display:none}
        .chart-wrap{height:320px;min-height:280px}
        .mega-panel{grid-template-columns:1fr;left:auto;right:0;max-height:70vh;overflow:auto}
        .stats, .footer-grid { grid-template-columns:1fr; }
        .pair-intro, .context-card { padding:12px; }
      }
      @media (max-width: 520px) {
        :root{--page-gutter:12px}
        h1 { font-size:24px; }
        .brand-name{font-size:16px}
        .brand-mark{width:28px;height:28px;flex-basis:28px}
        .site-nav{padding:8px var(--page-gutter); gap:10px}
        .mega > button{padding:7px 10px;font-size:13px}
        .translate-toggle{height:32px;min-width:40px}
        .chart-wrap{height:300px;min-height:260px;padding:8px}
        th, td { padding:8px; }
      }
    </style>
  </head>
  <body>
    <header class="site-header">
      <nav class="site-nav">
        <a class="brand" href="/">{{ brand_html|safe }}</a>
        <div class="header-pairs">
          {% if menu.active_header_links %}
            <span class="header-pairs-label">{{ menu.active_header_base }} pairs</span>
            {% for link in menu.active_header_links %}
              <a class="{% if link.active %}is-active{% endif %}" href="{{ link.href }}"{% if link.active %} aria-current="page"{% endif %}>{{ link.label }}</a>
            {% endfor %}
          {% else %}
            {% for group in menu.header_groups %}
              <div class="header-pair-group">
                <button type="button">{{ group.base }}</button>
                <div class="header-pair-submenu">
                  {% for link in group.links %}
                    <a href="{{ link.href }}">{{ link.label }}</a>
                  {% endfor %}
                </div>
              </div>
            {% endfor %}
          {% endif %}
        </div>
        <div class="mega">
          <button type="button">Currency pairs</button>
          <div class="mega-panel">
            {% for group in menu.groups %}
              <div class="mega-group">
                <h3>{{ group.title }}</h3>
                {% for link in group.links %}
                  <a href="{{ link.href }}">{{ link.label }}</a>
                {% endfor %}
              </div>
            {% endfor %}
          </div>
        </div>
        <div class="translate-widget" aria-label="Translate page">
          <button class="translate-toggle" type="button" aria-label="Translate page" aria-expanded="false">🌐</button>
          <div class="translate-menu" role="menu">
            <button class="translate-option" type="button" data-lang="en"><span class="translate-flag">🇺🇸</span><span>English</span></button>
            <button class="translate-option" type="button" data-lang="vi"><span class="translate-flag">🇻🇳</span><span>Tiếng Việt</span></button>
            <button class="translate-option" type="button" data-lang="th"><span class="translate-flag">🇹🇭</span><span>ไทย</span></button>
            <button class="translate-option" type="button" data-lang="ja"><span class="translate-flag">🇯🇵</span><span>日本語</span></button>
            <button class="translate-option" type="button" data-lang="ko"><span class="translate-flag">🇰🇷</span><span>한국어</span></button>
            <button class="translate-option" type="button" data-lang="zh-CN"><span class="translate-flag">🇨🇳</span><span>中文</span></button>
          </div>
          <div id="google_translate_element" class="translate-native"></div>
        </div>
      </nav>
    </header>
    <main>
      <header>
        <h1>{{ base }} to {{ target }} Exchange Rate</h1>
        {% if rate %}
          <p class="lede">1 {{ base }} = <strong>{{ rate }} {{ target }}</strong></p>
          <p class="muted">Updated {{ updated }}. Mid-market rate for informational use only.</p>
        {% else %}
          <p class="lede">Exchange rate data is not available yet.</p>
        {% endif %}
        <div class="pair-intro">
          <strong>{{ base }}/{{ target }} context:</strong>
          {{ content.summary }}
        </div>
      </header>

      <section>
        <h2>{{ base }} to {{ target }} chart</h2>
        <div class="chart-wrap"><canvas id="pair-chart"></canvas></div>
      </section>

      <section>
        <div class="converter-title-row">
          <h2>{{ base }} to {{ target }} converter</h2>
          {% if updated %}
            <span class="converter-updated">Updated {{ updated }}</span>
          {% endif %}
        </div>
        <div class="converter-table-wrap">
          <table>
            <thead><tr><th>{{ base }}</th><th>{{ target }}</th></tr></thead>
            <tbody>
              {% for left, right in rows %}
                <tr><td>{{ left }}</td><td>{{ right }}</td></tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <h2>{{ base }} pair movement</h2>
        <p class="muted">Pairs that use {{ base }} as the base currency, grouped by their move across the stored data window.</p>
        <div class="mover-grid">
          <div class="mover-list">
            <h3>Up {{ base }} pairs</h3>
            {% for item in pair_movers.up %}
              <a class="mover-item" href="{{ item.href }}">
                <span><span class="mover-pair">{{ item.label }}</span><span class="mover-rate">{{ item.rate }}</span></span>
                <span class="mover-change up">{{ item.change_label }}</span>
              </a>
            {% else %}
              <span class="mover-item"><span>No rising {{ base }} pairs yet</span><span class="mover-change flat">-</span></span>
            {% endfor %}
          </div>
          <div class="mover-list">
            <h3>Down {{ base }} pairs</h3>
            {% for item in pair_movers.down %}
              <a class="mover-item" href="{{ item.href }}">
                <span><span class="mover-pair">{{ item.label }}</span><span class="mover-rate">{{ item.rate }}</span></span>
                <span class="mover-change down">{{ item.change_label }}</span>
              </a>
            {% else %}
              <span class="mover-item"><span>No falling {{ base }} pairs yet</span><span class="mover-change flat">-</span></span>
            {% endfor %}
          </div>
          <div class="mover-list">
            <h3>Mostly flat</h3>
            {% for item in pair_movers.flat %}
              <a class="mover-item" href="{{ item.href }}">
                <span><span class="mover-pair">{{ item.label }}</span><span class="mover-rate">{{ item.rate }}</span></span>
                <span class="mover-change flat">{{ item.change_label }}</span>
              </a>
            {% else %}
              <span class="mover-item"><span>No flat {{ base }} pairs yet</span><span class="mover-change flat">-</span></span>
            {% endfor %}
          </div>
        </div>
      </section>

      {% if stats %}
        <section>
          <h2>{{ base }} to {{ target }} market summary</h2>
          <p>
            Over the available data window, {{ base }} to {{ target }} is
            {% if stats.direction == 'up' %}higher{% elif stats.direction == 'down' %}lower{% else %}mostly unchanged{% endif %}
            by {{ format_rate(stats.change) }} {{ target }} per 1 {{ base }}
            ({{ "%.4f"|format(stats.change_pct) }}%).
            The latest move from the previous point is {{ format_rate(stats.previous_change) }} {{ target }}
            ({{ "%.4f"|format(stats.previous_change_pct) }}%).
            The stored high-low range is about {{ "%.4f"|format(content.range_pct) }}%, which helps separate normal noise from a more meaningful move.
          </p>
          {% if reverse_rate %}
            <p>The reverse rate is 1 {{ target }} = {{ reverse_rate }} {{ base }}.</p>
          {% endif %}
        </section>

        <section>
          <h2>{{ base }} to {{ target }} statistics</h2>
          <div class="stats">
            <div class="stat"><span>High</span><strong>{{ format_rate(stats.high) }}</strong></div>
            <div class="stat"><span>Low</span><strong>{{ format_rate(stats.low) }}</strong></div>
            <div class="stat"><span>Average</span><strong>{{ format_rate(stats.average) }}</strong></div>
            <div class="stat"><span>Data points</span><strong>{{ stats.points }}</strong></div>
          </div>
        </section>
      {% endif %}

      <section>
        <h2>{{ target }} to {{ base }} quick conversion</h2>
        <table>
          <thead><tr><th>{{ target }}</th><th>{{ base }}</th></tr></thead>
          <tbody>
            {% for left, right in reverse_rows %}
              <tr><td>{{ left }}</td><td>{{ right }}</td></tr>
            {% endfor %}
          </tbody>
        </table>
      </section>

      <section>
        <h2>How to read this {{ base }} to {{ target }} page</h2>
        <div class="context-grid">
          {% for card in content.context_cards %}
            <div class="context-card">
              <h3>{{ card.title }}</h3>
              <p>{{ card.body }}</p>
            </div>
          {% endfor %}
        </div>
      </section>

      <section>
        <h2>{{ base }} to {{ target }} analysis guide</h2>
        <div class="insight-grid">
          <div class="insight">
            <h3>{{ base }} base-currency perspective</h3>
            <p>When {{ base }}/{{ target }} rises, holders of {{ base }} can exchange each unit for more {{ target }}. When it falls, the same {{ base }} amount converts into fewer {{ target }} units.</p>
          </div>
          <div class="insight">
            <h3>{{ target }} quote-currency perspective</h3>
            <p>The reverse table translates {{ target }} back into {{ base }}. This helps users who think in {{ target }} amounts first, especially when checking budgets, salaries, travel cash, or invoice values.</p>
          </div>
          <div class="insight">
            <h3>Why high, low, and average matter</h3>
            <p>The latest rate is only one point. The high and low show the {{ base }}/{{ target }} movement range, while the average gives a simple reference level for judging whether the current quote is stretched or near the middle.</p>
          </div>
          <div class="insight">
            <h3>Mid-market rate vs provider quote</h3>
            <p>This page is built for reference and comparison. Real {{ base }} to {{ target }} transfer or card rates may include a spread, conversion fee, settlement delay, or provider-specific rounding.</p>
          </div>
        </div>
      </section>

      <section class="faq">
        <h2>{{ base }} to {{ target }} FAQ</h2>
        {% for item in content.faqs %}
          <h3>{{ item.question }}</h3>
          <p>{{ item.answer }}</p>
        {% endfor %}
      </section>
    </main>
    {{ footer_html|safe }}
    <script>
      const historyData = {{ history_json|safe }};
      const labels = historyData.map(point => new Date(point.ts * 1000).toLocaleString());
      const values = historyData.map(point => point.rate);
      function formatRate(value){
        const n = Number(value);
        if(!Number.isFinite(n)) return value;
        if(n === 0) return '0';
        const abs = Math.abs(n);
        if(abs < 0.000001) return n.toExponential(6);
        if(abs < 1) return n.toFixed(8).replace(/0+$/, '').replace(/\\.$/, '');
        if(abs < 1000) return n.toFixed(6).replace(/0+$/, '').replace(/\\.$/, '');
        return n.toLocaleString(undefined, { maximumFractionDigits: 6 });
      }
      function significantPointLabelIndexes(values, maxLabels = 4){
        const changes = [];
        for(let index = 1; index < values.length; index += 1) {
          const current = Number(values[index]);
          const previous = Number(values[index - 1]);
          if(!Number.isFinite(current) || !Number.isFinite(previous) || previous === 0) continue;
          changes.push({ index, change: Math.abs((current - previous) / previous) });
        }
        changes.sort((a, b) => b.change - a.change);
        const strongest = changes[0]?.change || 0;
        const minChange = Math.max(0.0005, strongest * 0.35);
        const selected = [];
        for(const item of changes) {
          if(item.change < minChange) break;
          if(selected.some(index => Math.abs(index - item.index) <= 1)) continue;
          selected.push(item.index);
          if(selected.length >= maxLabels) break;
        }
        return new Set(selected);
      }
      function trendColor(values){
        const nums = values.map(Number).filter(Number.isFinite);
        if(nums.length < 2) return '#2563eb';
        const first = nums[0];
        const last = nums[nums.length - 1];
        if(first === 0) return '#2563eb';
        const change = (last - first) / first;
        if(change > 0.0001) return '#16a34a';
        if(change < -0.0001) return '#dc2626';
        return '#2563eb';
      }
      const latestValueBadge = {
        id: 'latestValueBadge',
        afterDatasetsDraw(chart) {
          const { ctx, chartArea } = chart;
          const dataset = chart.data.datasets[0];
          if(!dataset || !dataset.data.length) return;
          const value = Number(dataset.data[dataset.data.length - 1]);
          if(!Number.isFinite(value)) return;
          const y = chart.scales.y.getPixelForValue(value);
          const color = dataset.borderColor || '#2563eb';
          const label = formatRate(value);
          ctx.save();
          ctx.setLineDash([4, 4]);
          ctx.strokeStyle = 'rgba(37, 99, 235, 0.38)';
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(chartArea.left, y);
          ctx.lineTo(chartArea.right, y);
          ctx.stroke();
          ctx.setLineDash([]);
          ctx.font = 'bold 12px Arial, sans-serif';
          const paddingX = 8;
          const width = ctx.measureText(label).width + paddingX * 2;
          const height = 24;
          const x = Math.min(Math.max(chartArea.right - width - 8, chartArea.left), chartArea.right - width);
          const boxY = Math.max(chartArea.top, Math.min(y - height / 2, chartArea.bottom - height));
          ctx.fillStyle = color;
          ctx.fillRect(x, boxY, width, height);
          ctx.fillStyle = '#fff';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillText(label, x + width / 2, boxY + height / 2);
          ctx.restore();
        }
      };
      function chartAreaGradient(context){
        const chart = context.chart;
        const area = chart.chartArea;
        if(!area) return 'rgba(37, 99, 235, 0.16)';
        const gradient = chart.ctx.createLinearGradient(0, area.top, 0, area.bottom);
        gradient.addColorStop(0, 'rgba(37, 99, 235, 0.28)');
        gradient.addColorStop(0.7, 'rgba(37, 99, 235, 0.10)');
        gradient.addColorStop(1, 'rgba(37, 99, 235, 0.03)');
        return gradient;
      }
      new Chart(document.getElementById('pair-chart').getContext('2d'), {
        type: 'line',
        plugins: [latestValueBadge],
        data: {
          labels,
          datasets: [{ label: '{{ base }} to {{ target }}', data: values, borderColor: '#0b7cff', backgroundColor: chartAreaGradient, fill: true, tension: 0.18, pointRadius: 0, pointHoverRadius: 3, borderWidth: 1.8 }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: { mode: 'index', intersect: false },
          plugins: {
            legend: { display: false },
            tooltip: { callbacks: { label: context => `${context.dataset.label}: ${formatRate(context.parsed.y)}` } }
          },
          scales: {
            x: { grid: { display: false }, border: { display: false }, ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 6, color: '#667085' } },
            y: { position: 'right', beginAtZero: false, grid: { color: 'rgba(148, 163, 184, 0.16)', drawTicks: false }, border: { display: false }, ticks: { maxTicksLimit: 4, padding: 8, color: '#667085', callback: value => formatRate(value) } }
          }
        }
      });
    </script>
    <script>
      function closeHeaderMenus() {
        document.querySelectorAll('.mega.is-open, .header-pair-group.is-open').forEach(item => {
          item.classList.remove('is-open');
          const button = item.querySelector('button');
          if(button) button.setAttribute('aria-expanded', 'false');
        });
      }
      function initHeaderMenus() {
        document.querySelectorAll('.mega > button, .header-pair-group > button').forEach(button => {
          if(button.dataset.menuReady === '1') return;
          button.dataset.menuReady = '1';
          button.setAttribute('aria-expanded', 'false');
          button.addEventListener('click', event => {
            event.preventDefault();
            event.stopPropagation();
            const menu = button.parentElement;
            const open = !menu.classList.contains('is-open');
            closeHeaderMenus();
            if(!open) {
              button.blur();
              return;
            }
            menu.classList.toggle('is-open', open);
            button.setAttribute('aria-expanded', open ? 'true' : 'false');
          });
        });
        document.querySelectorAll('.mega-panel, .header-pair-submenu').forEach(panel => {
          panel.addEventListener('click', event => event.stopPropagation());
        });
        document.addEventListener('click', closeHeaderMenus);
        document.addEventListener('keydown', event => {
          if(event.key === 'Escape') closeHeaderMenus();
        });
      }
      function setTranslateCookie(value) {
        const maxAge = value ? '; max-age=31536000' : '; expires=Thu, 01 Jan 1970 00:00:00 GMT';
        document.cookie = `googtrans=${value || ''}; path=/${maxAge}`;
        if (location.hostname.includes('.')) {
          document.cookie = `googtrans=${value || ''}; path=/; domain=.${location.hostname}${maxAge}`;
        }
      }
      function applyTranslation(lang) {
        const combo = document.querySelector('.goog-te-combo');
        if (lang === 'en') {
          setTranslateCookie('');
          location.reload();
          return;
        }
        setTranslateCookie(`/en/${lang}`);
        if (combo) {
          combo.value = lang;
          combo.dispatchEvent(new Event('change'));
        } else {
          location.reload();
        }
      }
      function initTranslateMenu() {
        document.querySelectorAll('.translate-widget').forEach(widget => {
          if (widget.dataset.translateReady === '1') return;
          widget.dataset.translateReady = '1';
          const toggle = widget.querySelector('.translate-toggle');
          toggle.addEventListener('click', event => {
            event.stopPropagation();
            const open = !widget.classList.contains('is-open');
            document.querySelectorAll('.translate-widget.is-open').forEach(item => item.classList.remove('is-open'));
            widget.classList.toggle('is-open', open);
            toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
          });
          widget.querySelectorAll('[data-lang]').forEach(button => {
            button.addEventListener('click', () => applyTranslation(button.dataset.lang));
          });
        });
        document.addEventListener('click', () => {
          document.querySelectorAll('.translate-widget.is-open').forEach(widget => {
            widget.classList.remove('is-open');
            const toggle = widget.querySelector('.translate-toggle');
            if (toggle) toggle.setAttribute('aria-expanded', 'false');
          });
        });
      }
      function googleTranslateElementInit() {
        new google.translate.TranslateElement({ pageLanguage: 'en', autoDisplay: false, layout: google.translate.TranslateElement.InlineLayout.HORIZONTAL }, 'google_translate_element');
        initTranslateMenu();
      }
      document.addEventListener('DOMContentLoaded', initHeaderMenus);
      document.addEventListener('DOMContentLoaded', initTranslateMenu);
    </script>
    <script src="https://translate.google.com/translate_a/element.js?cb=googleTranslateElementInit"></script>
  </body>
</html>
"""


@app.route("/exchange/<pair>/")
@app.route("/exchange/<pair>")
def exchange_pair_redirect(pair):
    try:
        base, target = parse_pair_key(pair)
    except ValueError:
        return "Invalid pair", 404
    if len(base) != 3 or len(target) != 3:
        return "Invalid pair", 404
    return redirect_permanent(pair_url(base, target))


@app.route("/<pair>/")
def exchange_pair_trailing_slash_redirect(pair):
    try:
        base, target = parse_pair_key(pair)
    except ValueError:
        return "Invalid pair", 404
    if len(base) != 3 or len(target) != 3:
        return "Invalid pair", 404
    return redirect_permanent(pair_url(base, target))


@app.route("/<pair>")
def exchange_pair_page(pair):
    try:
        base, target = parse_pair_key(pair)
    except ValueError:
        return "Invalid pair", 404
    if len(base) != 3 or len(target) != 3:
        return "Invalid pair", 404
    canonical_path = pair_url(base, target)
    if request.path != canonical_path:
        return redirect_permanent(canonical_path)
    return render_cached_pair_page(base, target)


if __name__ == "__main__":
    ensure_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
