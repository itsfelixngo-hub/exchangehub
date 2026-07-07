#!/usr/bin/env python3
"""Fetch exchange rates and write outputs to a target uploads dir:

- `rates/{base}_{target}.json`: per-pair history arrays of {ts, base, target, rate}
- `rates/index.json`: lightweight pair manifest
- `rates.html`: a small pre-rendered HTML partial for including in a WP template

Design notes:
- Writes are atomic (write temp + os.replace).
- Keeps up to `MAX_ENTRIES_PER_PAIR` entries per currency pair to avoid file growth.
"""
import os
import time
import json
import requests
import tempfile
import calendar
from typing import Dict, List, Tuple

try:
    from .r2_storage import get_json, local_storage_enabled, put_bytes, r2_enabled
except ImportError:
    from r2_storage import get_json, local_storage_enabled, put_bytes, r2_enabled

# Configure where to write the outputs. In production set env WP_UPLOADS
MODULE_DIR = os.path.dirname(__file__)
UPLOADS_DIR = os.environ.get("WP_UPLOADS", "wp-content/uploads")
RATES_DIR = "rates"
RATES_INDEX = "index.json"
RATES_HTML = "rates.html"
RATE_CONFIG_JSON = os.environ.get("RATE_CONFIG_JSON", os.path.join(MODULE_DIR, "rate_pairs.json"))


def parse_pair_key(pair: str) -> Tuple[str, str]:
    parts = str(pair).replace("-", "_").upper().split("_")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(f"Invalid pair {pair!r}; expected BASE_TARGET, e.g. vnd_usd")
    return parts[0], parts[1]


def normalize_pairs(pairs) -> List[Tuple[str, str]]:
    out = []
    for pair in pairs:
        parsed = parse_pair_key(pair) if isinstance(pair, str) else (str(pair[0]).upper(), str(pair[1]).upper())
        if parsed[0] != parsed[1] and parsed not in out:
            out.append(parsed)
    return out


def normalize_codes(codes, excluded: str) -> List[str]:
    out = []
    for code in codes:
        code = str(code).upper()
        if code and code != excluded and code not in out:
            out.append(code)
    return out


def load_rate_config(path: str) -> List[Tuple[str, str]]:
    with open(path, "r", encoding="utf-8") as f:
        config = json.load(f)
    if isinstance(config, list):
        return normalize_pairs(config)
    if "pairs" in config:
        return normalize_pairs(config.get("pairs", []))
    base = str(config.get("base", "USD")).upper()
    return [(base, target) for target in normalize_codes(config.get("targets", []), base)]

# Pairs to fetch (edit as needed)
PAIRS: List[Tuple[str, str]] = load_rate_config(RATE_CONFIG_JSON)
PAIR_KEYS = set(PAIRS)

API_CONVERT = "https://api.exchangerate.host/convert"
# OpenExchangeRates endpoint (if you have an app id)
OXR_LATEST = "https://openexchangerates.org/api/latest.json"
OXR_DISABLED_APP_IDS = "OPENEXCHANGE_DISABLED_APP_IDS"
OXR_STATE_FILE = os.environ.get("OXR_APP_ID_STATE_FILE", "/app/.deploy-state/openexchange_app_ids_state.json")
OXR_APP_ID_COOLDOWN_SECONDS = int(os.environ.get("OXR_APP_ID_COOLDOWN_SECONDS", str(24 * 60 * 60)))
OXR_APP_ID_MONTHLY_LIMIT = int(os.environ.get("OXR_APP_ID_MONTHLY_LIMIT", "1000"))
OXR_APP_ID_MAX_USAGE_PERCENT = float(os.environ.get("OXR_APP_ID_MAX_USAGE_PERCENT", "115"))
OXR_APP_ID_RESET_DAY = int(os.environ.get("OXR_APP_ID_RESET_DAY", "1"))
OXR_APP_ID_RESET_DAYS = os.environ.get("OXR_APP_ID_RESET_DAYS", "")

# Keep this many 5-minute entries per pair (2016 = 7 days)
MAX_ENTRIES_PER_PAIR = 2016


class OXRAppIdUnavailable(RuntimeError):
    """Raised when an OXR app id should be skipped for later fetch attempts."""


def ensure_uploads_dir(path: str):
    os.makedirs(path, exist_ok=True)


def pair_key(base: str, target: str) -> str:
    return f"{base.lower()}_{target.lower()}"


def pair_json_path(rates_dir: str, base: str, target: str) -> str:
    return os.path.join(rates_dir, f"{pair_key(base, target)}.json")


def atomic_write(path: str, data: bytes, mode: int = 0o644):
    dirpath = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=dirpath)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        os.chmod(path, mode)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass


def fetch_rate(base: str, target: str) -> float:
    """Fetch a single pair using exchangerate.host as fallback."""
    resp = requests.get(API_CONVERT, params={"from": base, "to": target}, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return float(data.get("result"))


def oxr_error_text(resp) -> str:
    try:
        data = resp.json()
    except Exception:
        return resp.text[:500]
    if isinstance(data, dict):
        parts = [str(data.get(key, "")) for key in ("message", "description", "error", "status") if data.get(key)]
        return " ".join(parts) or json.dumps(data, ensure_ascii=False)[:500]
    return str(data)[:500]


def is_oxr_quota_or_key_error(status_code: int, text: str) -> bool:
    lowered = text.lower()
    if status_code == 429:
        return True
    quota_words = ("quota", "limit", "rate limit", "usage", "exceeded", "exhausted", "inactive", "invalid")
    return status_code in {401, 403} and any(word in lowered for word in quota_words)


def int_or_default(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def fetch_all_via_oxr(app_id: str):
    """Fetch full rates table from OpenExchangeRates (base USD) and return rates dict."""
    resp = requests.get(OXR_LATEST, params={"app_id": app_id}, timeout=15)
    if not resp.ok:
        error_text = oxr_error_text(resp)
        if is_oxr_quota_or_key_error(resp.status_code, error_text):
            raise OXRAppIdUnavailable(f"HTTP {resp.status_code}: {error_text}")
        resp.raise_for_status()
    data = resp.json()
    # data['rates'] is a dict like {'VND': 23456.0, 'EUR': 0.92, 'USD':1}
    rates = data.get("rates", {})
    if not rates:
        error_text = " ".join(str(data.get(key, "")) for key in ("message", "description", "error") if data.get(key))
        if error_text and is_oxr_quota_or_key_error(int_or_default(data.get("status"), 200), error_text):
            raise OXRAppIdUnavailable(error_text)
    return rates


def mask_app_id(app_id: str) -> str:
    if len(app_id) <= 8:
        return "****"
    return f"{app_id[:4]}...{app_id[-4:]}"


def get_oxr_app_ids() -> List[str]:
    raw_multi = os.environ.get("OPENEXCHANGE_APP_IDS", "")
    ids = [part.strip() for part in raw_multi.split(",") if part.strip()]
    single = os.environ.get("OPENEXCHANGE_APP_ID", "").strip()
    if single:
        ids.append(single)
    disabled = set(get_disabled_oxr_app_ids())
    out = []
    for app_id in ids:
        if app_id not in disabled and app_id not in out:
            out.append(app_id)
    return out


def get_disabled_oxr_app_ids() -> List[str]:
    raw = os.environ.get(OXR_DISABLED_APP_IDS, "")
    return [part.strip() for part in raw.split(",") if part.strip()]


def parse_oxr_reset_days() -> Dict[str, int]:
    out = {}
    for item in OXR_APP_ID_RESET_DAYS.split(","):
        if not item.strip() or ":" not in item:
            continue
        app_id, day = item.split(":", 1)
        app_id = app_id.strip()
        day_int = int_or_default(day.strip(), OXR_APP_ID_RESET_DAY)
        if app_id:
            out[app_id] = min(max(day_int, 1), 31)
    return out


def load_oxr_state() -> Dict:
    try:
        with open(OXR_STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_oxr_state(state: Dict):
    try:
        os.makedirs(os.path.dirname(OXR_STATE_FILE) or ".", exist_ok=True)
        atomic_write(OXR_STATE_FILE, json.dumps(state, ensure_ascii=False, indent=2).encode("utf-8"), mode=0o600)
    except Exception as exc:
        print(f"Could not persist OXR app id state: {exc}")


def previous_month(year: int, month: int) -> Tuple[int, int]:
    if month == 1:
        return year - 1, 12
    return year, month - 1


def effective_month_day(year: int, month: int, day: int) -> int:
    return min(max(day, 1), calendar.monthrange(year, month)[1])


def oxr_period_key(ts: int, reset_day: int) -> str:
    tm = time.gmtime(ts)
    current_reset_day = effective_month_day(tm.tm_year, tm.tm_mon, reset_day)
    if tm.tm_mday >= current_reset_day:
        year, month = tm.tm_year, tm.tm_mon
    else:
        year, month = previous_month(tm.tm_year, tm.tm_mon)
    day = effective_month_day(year, month, reset_day)
    return f"{year:04d}-{month:02d}-{day:02d}"


def oxr_allowed_requests() -> int:
    return max(1, int(OXR_APP_ID_MONTHLY_LIMIT * OXR_APP_ID_MAX_USAGE_PERCENT / 100))


def oxr_usage_record(app_id: str, state: Dict, now_ts: int) -> Dict:
    reset_day = parse_oxr_reset_days().get(app_id, OXR_APP_ID_RESET_DAY)
    period = oxr_period_key(now_ts, reset_day)
    usage = state.setdefault("usage", {})
    record = usage.get(app_id)
    if not isinstance(record, dict) or record.get("period") != period:
        record = {"period": period, "count": 0, "reset_day": reset_day}
        usage[app_id] = record
    return record


def oxr_quota_guard_allows(app_id: str, state: Dict, now_ts: int) -> bool:
    record = oxr_usage_record(app_id, state, now_ts)
    count = int(record.get("count", 0) or 0)
    allowed = oxr_allowed_requests()
    if count >= allowed:
        print(f"Skipping OXR app id {mask_app_id(app_id)}: local monthly guard {count}/{allowed} requests")
        return False
    return True


def record_oxr_success(app_id: str, state: Dict, now_ts: int):
    record = oxr_usage_record(app_id, state, now_ts)
    record["count"] = int(record.get("count", 0) or 0) + 1
    record["last_success_ts"] = now_ts
    save_oxr_state(state)


def cooldown_active(until_ts: int, now_ts: int) -> bool:
    return bool(until_ts and until_ts > now_ts)


def state_available_app_ids(app_ids: List[str], state: Dict, now_ts: int) -> List[str]:
    cooldowns = state.get("cooldowns", {})
    return [
        app_id
        for app_id in app_ids
        if not cooldown_active(int(cooldowns.get(app_id, 0) or 0), now_ts)
        and oxr_quota_guard_allows(app_id, state, now_ts)
    ]


def mark_oxr_app_id_unavailable(app_id: str, state: Dict, now_ts: int):
    cooldowns = state.setdefault("cooldowns", {})
    cooldowns[app_id] = now_ts + OXR_APP_ID_COOLDOWN_SECONDS
    save_oxr_state(state)
    retry_at = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(cooldowns[app_id]))
    print(f"Put OXR app id {mask_app_id(app_id)} on cooldown until {retry_at} after quota/key error")


def ordered_app_ids_for_run(app_ids: List[str], ts: int, state: Dict) -> List[str]:
    if not app_ids:
        return []
    start = int(state.get("next_index", 0) or 0) % len(app_ids)
    return app_ids[start:] + app_ids[:start]


def advance_oxr_cursor(app_id: str, app_ids: List[str], state: Dict):
    try:
        state["next_index"] = (app_ids.index(app_id) + 1) % len(app_ids)
        save_oxr_state(state)
    except ValueError:
        pass


def fetch_all_via_oxr_pool(app_ids: List[str], ts: int):
    errors = []
    state = load_oxr_state()
    available_app_ids = state_available_app_ids(app_ids, state, ts)
    if not available_app_ids:
        cooldowns = state.get("cooldowns", {})
        next_retry = min((int(cooldowns.get(app_id, 0) or 0) for app_id in app_ids), default=0)
        raise RuntimeError(f"All OpenExchangeRates app ids are disabled until {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(next_retry))}")

    for app_id in ordered_app_ids_for_run(available_app_ids, ts, state):
        try:
            rates = fetch_all_via_oxr(app_id)
            print(f"Fetched OXR table using app id {mask_app_id(app_id)}")
            record_oxr_success(app_id, state, ts)
            advance_oxr_cursor(app_id, available_app_ids, state)
            return rates
        except OXRAppIdUnavailable as exc:
            errors.append(f"{mask_app_id(app_id)}: {exc}")
            print(f"Cooldown OXR app id {mask_app_id(app_id)}: {exc}")
            mark_oxr_app_id_unavailable(app_id, state, ts)
        except Exception as exc:
            errors.append(f"{mask_app_id(app_id)}: {exc}")
            print(f"Failed OXR app id {mask_app_id(app_id)}: {exc}")
    raise RuntimeError("; ".join(errors) or "No OpenExchangeRates app id configured")


def load_existing(json_path: str):
    if not os.path.exists(json_path):
        return []
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def load_existing_pair(rates_dir: str, base: str, target: str):
    relative_path = os.path.join(RATES_DIR, f"{pair_key(base, target)}.json")
    if r2_enabled():
        try:
            entries = get_json(relative_path)
            if isinstance(entries, list):
                return entries
        except Exception as exc:
            print(f"Failed to read {relative_path} from Cloudflare R2: {exc}")

    if local_storage_enabled():
        return load_existing(pair_json_path(rates_dir, base, target))
    return []


def write_output(local_path: str, relative_path: str, data: bytes, content_type: str):
    wrote = False
    local_error = None

    if r2_enabled():
        put_bytes(relative_path, data, content_type=content_type)
        wrote = True

    if local_storage_enabled():
        try:
            atomic_write(local_path, data)
            print(f"Wrote {local_path}")
            wrote = True
        except Exception as exc:
            local_error = exc
            if not r2_enabled():
                raise
            print(f"Skipped local write for {local_path}: {exc}")

    if not wrote:
        raise RuntimeError("No storage target enabled. Set LOCAL_STORAGE_ENABLED=true or R2_ENABLED=true.")
    if local_error and r2_enabled():
        print("Local write failed, but Cloudflare R2 write succeeded.")


def prune_pair_entries(entries: List[dict], base: str, target: str) -> List[dict]:
    filtered = [
        e for e in entries
        if e.get("base") == base and e.get("target") == target
    ]
    return sorted(filtered, key=lambda x: x.get("ts", 0))[-MAX_ENTRIES_PER_PAIR:]


def flatten_entries(entries_by_pair: dict) -> List[dict]:
    out = []
    for entries in entries_by_pair.values():
        out.extend(entries)
    return sorted(out, key=lambda x: x.get("ts", 0))


def build_index(entries_by_pair: dict) -> dict:
    pairs = []
    for base, target in PAIRS:
        key = pair_key(base, target)
        entries = entries_by_pair.get((base, target), [])
        latest = entries[-1] if entries else None
        pairs.append({
            "key": key,
            "base": base,
            "target": target,
            "file": f"{key}.json",
            "latest": latest,
        })
    return {"pairs": pairs}


def prune_entries(entries: List[dict]) -> List[dict]:
    # Keep only configured pairs and the last MAX_ENTRIES_PER_PAIR per (base,target).
    by_pair = {}
    for e in entries:
        key = (e.get("base"), e.get("target"))
        if key not in PAIR_KEYS:
            continue
        by_pair.setdefault(key, []).append(e)
    out = []
    for key, arr in by_pair.items():
        arr_sorted = sorted(arr, key=lambda x: x.get("ts", 0))
        trimmed = arr_sorted[-MAX_ENTRIES_PER_PAIR:]
        out.extend(trimmed)
    # sort overall by ts
    return sorted(out, key=lambda x: x.get("ts", 0))


def render_html(entries: List[dict]) -> str:
    # Group latest rate per pair for display header
    latest = {}
    for e in entries:
        key = (e["base"], e["target"])
        if key not in latest or e["ts"] > latest[key]["ts"]:
            latest[key] = e

    rows = []
    for (base, target), e in sorted(latest.items()):
        rows.append(f"<tr><td>{base}</td><td>{target}</td><td>{e['rate']:.6f}</td><td>{time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(e['ts']))}</td></tr>")

    # Embed the JSON data for client-side charting if desired
    payload = json.dumps(entries)

    html = f"""
<div class="exchange-rates">
  <h3>Exchange rates (latest)</h3>
  <table>
    <thead><tr><th>Base</th><th>Target</th><th>Rate</th><th>Updated (UTC)</th></tr></thead>
    <tbody>
      {''.join(rows)}
    </tbody>
  </table>
  <script id="rates-data" type="application/json">{payload}</script>
</div>
"""
    return html


def main():
    rates_dir = os.path.join(UPLOADS_DIR, RATES_DIR)
    if local_storage_enabled():
        ensure_uploads_dir(UPLOADS_DIR)
        ensure_uploads_dir(rates_dir)
    index_path = os.path.join(rates_dir, RATES_INDEX)
    html_path = os.path.join(UPLOADS_DIR, RATES_HTML)

    entries_by_pair = {}
    for base, target in PAIRS:
        entries_by_pair[(base, target)] = load_existing_pair(rates_dir, base, target)
    ts = int(time.time())

    # If OpenExchangeRates app ids are set, fetch one full table and derive pairs.
    oxr_app_ids = get_oxr_app_ids()
    if oxr_app_ids:
        try:
            rates = fetch_all_via_oxr_pool(oxr_app_ids, ts)
            for base, target in PAIRS:
                if base not in rates or target not in rates:
                    print(f"Pair {base}->{target} missing in OXR rates; skipping")
                    continue
                # rates are per 1 USD. Compute base->target as rates[target] / rates[base]
                rate = float(rates[target]) / float(rates[base])
                entries_by_pair.setdefault((base, target), []).append({"ts": ts, "base": base, "target": target, "rate": rate})
                print(f"Fetched (OXR) {base}->{target} = {rate}")
        except Exception as exc:
            print(f"Failed fetching from OpenExchangeRates: {exc}")
            # fallback to per-pair fetch below
            for base, target in PAIRS:
                try:
                    rate = fetch_rate(base, target)
                    entries_by_pair.setdefault((base, target), []).append({"ts": ts, "base": base, "target": target, "rate": rate})
                    print(f"Fetched {base}->{target} = {rate}")
                except Exception as exc2:
                    print(f"Failed {base}->{target}: {exc2}")
    else:
        for base, target in PAIRS:
            try:
                rate = fetch_rate(base, target)
                entries_by_pair.setdefault((base, target), []).append({"ts": ts, "base": base, "target": target, "rate": rate})
                print(f"Fetched {base}->{target} = {rate}")
            except Exception as exc:
                print(f"Failed {base}->{target}: {exc}")

    for base, target in PAIRS:
        entries_by_pair[(base, target)] = prune_pair_entries(entries_by_pair.get((base, target), []), base, target)

    # write one JSON file per pair plus a lightweight index
    try:
        for base, target in PAIRS:
            path = pair_json_path(rates_dir, base, target)
            relative_path = os.path.join(RATES_DIR, os.path.basename(path))
            data = json.dumps(entries_by_pair[(base, target)], ensure_ascii=False, indent=2).encode("utf-8")
            write_output(path, relative_path, data, "application/json")
        index_data = json.dumps(build_index(entries_by_pair), ensure_ascii=False, indent=2).encode("utf-8")
        write_output(index_path, os.path.join(RATES_DIR, RATES_INDEX), index_data, "application/json")
    except Exception as exc:
        print(f"Failed to write JSON: {exc}")

    # write HTML partial atomically
    try:
        html = render_html(flatten_entries(entries_by_pair))
        write_output(html_path, RATES_HTML, html.encode("utf-8"), "text/html; charset=utf-8")
    except Exception as exc:
        print(f"Failed to write HTML: {exc}")


if __name__ == "__main__":
    main()
