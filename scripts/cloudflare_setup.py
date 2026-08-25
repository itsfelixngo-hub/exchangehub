#!/usr/bin/env python3
"""Apply the Cloudflare-side settings this site needs.

Cloudflare does not cache HTML by default, so the Cache-Control headers the
app sends are ignored at the edge and every request reaches the origin. This
adds a Cache Rule that makes the zone cacheable, and can switch on
Authenticated Origin Pulls.

API token scopes (My Profile -> API Tokens), all on this zone:

    Zone - Zone                   - Read    (look the zone up by name)
    Zone - Cache Rules            - Edit    (--cache-rule)
    Zone - SSL and Certificates   - Edit    (--origin-pulls)

Nothing is changed without --apply; the default run only reports.

    python3 scripts/cloudflare_setup.py                 # report current state
    python3 scripts/cloudflare_setup.py --cache-rule --apply
    python3 scripts/cloudflare_setup.py --origin-pulls --apply
"""
import argparse
import json
import os
import sys
from pathlib import Path

import requests

API_BASE = "https://api.cloudflare.com/client/v4"
CACHE_PHASE = "http_request_cache_settings"
RULE_DESCRIPTION = "ratehubfx: cache HTML at the edge, except /contact"


def load_dotenv(path: Path):
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def env(name, default=""):
    return os.environ.get(name, default).strip()


def cf_request(method, path, token, allow_missing=False, **kwargs):
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {token}"
    headers["Content-Type"] = "application/json"
    response = requests.request(method, f"{API_BASE}{path}", headers=headers, timeout=30, **kwargs)
    try:
        payload = response.json()
    except ValueError:
        response.raise_for_status()
        raise RuntimeError("Cloudflare returned a non-JSON response")
    if not payload.get("success"):
        errors = payload.get("errors") or []
        if allow_missing and response.status_code == 404:
            return None
        raise RuntimeError(f"Cloudflare API error ({response.status_code}): {errors}")
    return payload.get("result")


def zone_id_for(name, token):
    zones = cf_request("GET", f"/zones?name={name}", token)
    if not zones:
        raise RuntimeError(f"zone {name!r} not found, or the token cannot read it")
    return zones[0]["id"]


def cache_rule_for(zone_name):
    hosts = f'"{zone_name}" "www.{zone_name}"'
    return {
        "description": RULE_DESCRIPTION,
        "expression": (
            f"(http.host in {{{hosts}}} "
            'and not starts_with(http.request.uri.path, "/contact"))'
        ),
        "action": "set_cache_settings",
        "action_parameters": {
            "cache": True,
            # The app already sends Cache-Control with the TTL it wants, so
            # follow it rather than pinning a number here in a second place.
            "edge_ttl": {"mode": "respect_origin"},
            "browser_ttl": {"mode": "respect_origin"},
        },
    }


def show_cache_rules(zone, token):
    ruleset = cf_request(
        "GET", f"/zones/{zone}/rulesets/phases/{CACHE_PHASE}/entrypoint",
        token, allow_missing=True,
    )
    rules = (ruleset or {}).get("rules") or []
    print(f"  cache rules currently on the zone: {len(rules)}")
    for rule in rules:
        state = "enabled" if rule.get("enabled", True) else "disabled"
        print(f"    - [{state}] {rule.get('description') or '(no description)'}")
        print(f"        {rule.get('expression')}")
    return ruleset, rules


def apply_cache_rule(zone, zone_name, token, rules, apply):
    wanted = cache_rule_for(zone_name)
    merged = [r for r in rules if r.get("description") != RULE_DESCRIPTION]
    replaced = len(merged) != len(rules)
    merged.append(wanted)

    print("\n  rule to install:")
    print(f"    {wanted['expression']}")
    print(f"    -> {json.dumps(wanted['action_parameters'])}")
    if replaced:
        print("    (replaces the existing rule with the same description)")
    if rules and not replaced:
        print(f"    ({len(rules)} existing rule(s) kept, this one appended last)")

    if not apply:
        print("\n  dry run: nothing changed. Re-run with --apply.")
        return
    cf_request(
        "PUT", f"/zones/{zone}/rulesets/phases/{CACHE_PHASE}/entrypoint",
        token, data=json.dumps({"rules": merged}),
    )
    print("\n  applied.")


def origin_pulls(zone, token, apply):
    current = cf_request("GET", f"/zones/{zone}/origin_tls_client_auth/settings", token)
    enabled = (current or {}).get("enabled")
    print(f"  authenticated origin pulls: {'on' if enabled else 'off'}")
    if enabled:
        return
    if not apply:
        print("  dry run: nothing changed. Re-run with --apply.")
        return
    cf_request(
        "PUT", f"/zones/{zone}/origin_tls_client_auth/settings",
        token, data=json.dumps({"enabled": True}),
    )
    print("  enabled. Now uncomment ssl_client_certificate and ssl_verify_client")
    print("  in the nginx config, or nothing changes on the origin side.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cache-rule", action="store_true", help="install the edge cache rule")
    parser.add_argument("--origin-pulls", action="store_true", help="turn on Authenticated Origin Pulls")
    parser.add_argument("--apply", action="store_true", help="actually change things (default is a dry run)")
    args = parser.parse_args()

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    token = env("CF_API_TOKEN")
    zone_name = env("CF_ZONE_NAME")
    if not token or not zone_name:
        sys.exit("CF_API_TOKEN and CF_ZONE_NAME must be set (see .env.sample)")

    zone = zone_id_for(zone_name, token)
    print(f"zone {zone_name} ({zone})\n")

    print("cache rules")
    _, rules = show_cache_rules(zone, token)
    if args.cache_rule:
        apply_cache_rule(zone, zone_name, token, rules, args.apply)

    print("\norigin pulls")
    origin_pulls(zone, token, args.apply and args.origin_pulls)

    if not (args.cache_rule or args.origin_pulls):
        print("\nreport only. Pass --cache-rule and/or --origin-pulls to change things.")


if __name__ == "__main__":
    main()
