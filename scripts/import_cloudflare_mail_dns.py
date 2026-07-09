#!/usr/bin/env python3
import argparse
import os
import re
import shlex
import sys
from pathlib import Path

import requests


API_BASE = "https://api.cloudflare.com/client/v4"


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


def cf_request(method, path, token, **kwargs):
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
        raise RuntimeError(f"Cloudflare API error: {errors}")
    return payload.get("result")


def zone_id_for_name(token, zone_name):
    result = cf_request("GET", "/zones", token, params={"name": zone_name, "status": "active"})
    if not result:
        raise RuntimeError(f"Cloudflare zone not found: {zone_name}")
    return result[0]["id"]


def list_records(token, zone_id, record_type, name):
    return cf_request(
        "GET",
        f"/zones/{zone_id}/dns_records",
        token,
        params={"type": record_type, "name": name},
    )


def normalize_record(record):
    normalized = {
        "type": record["type"],
        "name": record["name"],
        "content": record["content"],
        "ttl": int(record.get("ttl") or 1),
    }
    if "proxied" in record:
        normalized["proxied"] = bool(record["proxied"])
    if "priority" in record:
        normalized["priority"] = int(record["priority"])
    return normalized


def matching_record(records, desired):
    prefix = desired.pop("_match_content_prefix", "")
    if prefix:
        for record in records:
            if str(record.get("content", "")).startswith(prefix):
                return record
        return None
    return records[0] if records else None


def upsert_record(token, zone_id, record, dry_run=False):
    desired = dict(record)
    api_record = normalize_record(desired)
    matches = list_records(token, zone_id, record["type"], record["name"])
    existing = matching_record(matches, desired)
    action = "create" if not existing else "update"

    if existing:
        same = (
            existing.get("content") == api_record["content"]
            and int(existing.get("ttl") or 1) == api_record["ttl"]
            and bool(existing.get("proxied", False)) == bool(api_record.get("proxied", False))
            and int(existing.get("priority") or 0) == int(api_record.get("priority") or 0)
        )
        if same:
            print(f"skip   {api_record['type']:5} {api_record['name']} already correct")
            return

    print(f"{action:6} {api_record['type']:5} {api_record['name']} -> {api_record['content']}")
    if dry_run:
        return
    if existing:
        cf_request("PUT", f"/zones/{zone_id}/dns_records/{existing['id']}", token, json=api_record)
    else:
        cf_request("POST", f"/zones/{zone_id}/dns_records", token, json=api_record)


def parse_dkim_file(path: Path, domain):
    if not path or not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    name_match = re.search(r"^\s*([A-Za-z0-9._-]+)\s+IN\s+TXT", text, re.MULTILINE)
    quoted_parts = re.findall(r'"([^"]+)"', text)
    if not name_match or not quoted_parts:
        raise RuntimeError(f"Could not parse DKIM record from {path}")

    name = name_match.group(1).rstrip(".")
    if not name.endswith(domain):
        name = f"{name}.{domain}"
    return {"type": "TXT", "name": name, "content": "".join(quoted_parts), "ttl": 1, "_match_content_prefix": "v=DKIM1"}


def default_dkim_path(domain):
    return Path(f"docker-data/dms/config/opendkim/keys/{domain}/mail.txt")


def clean_dns_name(name):
    return str(name).strip().rstrip(".")


def parse_zone_file(path: Path):
    records = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith(";"):
            continue

        proxied_match = re.search(r"cf-proxied:(true|false)", raw_line, re.IGNORECASE)
        record_part = re.sub(r"\s+;\s*cf_tags=.*$", "", raw_line).strip()
        parts = record_part.split(None, 4)
        if len(parts) < 4:
            continue

        name = clean_dns_name(parts[0])
        ttl = int(parts[1])
        record_type = parts[3].upper()
        rest = parts[4].strip() if len(parts) > 4 else ""
        proxied = proxied_match.group(1).lower() == "true" if proxied_match else None

        if record_type in {"SOA", "NS"}:
            continue
        if record_type == "A":
            record = {"type": "A", "name": name, "content": rest.split()[0], "ttl": ttl}
            if proxied is not None:
                record["proxied"] = proxied
            records.append(record)
        elif record_type == "CNAME":
            record = {"type": "CNAME", "name": name, "content": clean_dns_name(rest.split()[0]), "ttl": ttl}
            if proxied is not None:
                record["proxied"] = proxied
            records.append(record)
        elif record_type == "MX":
            mx_parts = rest.split()
            if len(mx_parts) < 2:
                raise RuntimeError(f"Invalid MX line in {path}: {raw_line}")
            records.append({
                "type": "MX",
                "name": name,
                "content": clean_dns_name(mx_parts[1]),
                "priority": int(mx_parts[0]),
                "ttl": ttl,
            })
        elif record_type == "TXT":
            quoted_parts = re.findall(r'"([^"]*)"', rest)
            content = "".join(quoted_parts) if quoted_parts else " ".join(shlex.split(rest))
            record = {"type": "TXT", "name": name, "content": content, "ttl": ttl}
            if content.startswith("v=spf1"):
                record["_match_content_prefix"] = "v=spf1"
            elif content.startswith("v=DMARC1"):
                record["_match_content_prefix"] = "v=DMARC1"
            elif content.startswith("v=DKIM1"):
                record["_match_content_prefix"] = "v=DKIM1"
            records.append(record)
        else:
            print(f"skip   unsupported {record_type} record in {path}: {name}")
    return records


def build_records(args):
    if args.zone_file:
        records = parse_zone_file(args.zone_file)
        dkim_record = parse_dkim_file(args.dkim_file, args.domain) if args.dkim_file else None
        if dkim_record and not any(record["type"] == "TXT" and record.get("_match_content_prefix") == "v=DKIM1" for record in records):
            records.append(dkim_record)
        return records

    domain = args.domain
    mail_fqdn = f"{args.mail_host}.{domain}"
    records = [
        {"type": "A", "name": mail_fqdn, "content": args.ip, "ttl": 1, "proxied": False},
        {"type": "MX", "name": domain, "content": mail_fqdn, "ttl": 1, "priority": args.mx_priority},
        {"type": "TXT", "name": domain, "content": args.spf, "ttl": 1, "_match_content_prefix": "v=spf1"},
        {"type": "TXT", "name": f"_dmarc.{domain}", "content": args.dmarc, "ttl": 1, "_match_content_prefix": "v=DMARC1"},
    ]
    dkim_record = parse_dkim_file(args.dkim_file, domain) if args.dkim_file else None
    if dkim_record:
        records.append(dkim_record)
    return records


def parse_args():
    parser = argparse.ArgumentParser(description="Import/upsert mail DNS records into Cloudflare.")
    parser.add_argument("--env-file", default=".env", help="Env file to load first. Default: .env")
    parser.add_argument("--zone-id", default="", help="Cloudflare Zone ID")
    parser.add_argument("--zone-name", default="")
    parser.add_argument("--domain", default="")
    parser.add_argument("--mail-host", default="")
    parser.add_argument("--ip", default="")
    parser.add_argument("--mx-priority", type=int, default=0)
    parser.add_argument("--spf", default="")
    parser.add_argument(
        "--dmarc",
        default="",
    )
    parser.add_argument("--dkim-file", default="", help="Path to docker-mailserver mail.txt DKIM record")
    parser.add_argument("--zone-file", default="", help="Import records from a Cloudflare/BIND zone export file")
    parser.add_argument("--no-dkim", action="store_true", help="Skip DKIM import")
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing to Cloudflare")
    return parser.parse_args()


def main():
    args = parse_args()
    load_dotenv(Path(args.env_file))

    token = env("CF_API_TOKEN")
    if not token:
        print("Missing CF_API_TOKEN", file=sys.stderr)
        return 2

    args.zone_id = args.zone_id or env("CF_ZONE_ID")
    args.zone_name = args.zone_name or env("CF_ZONE_NAME") or env("MAIL_DOMAIN") or args.domain or "ratehubfx.com"
    args.domain = args.domain or env("MAIL_DOMAIN") or args.zone_name
    args.mail_host = args.mail_host or env("MAIL_HOSTNAME") or "mail"
    args.ip = args.ip or env("MAIL_SERVER_IP") or env("VPS_IP")
    args.mx_priority = args.mx_priority or int(env("MAIL_MX_PRIORITY") or "10")
    args.spf = args.spf or env("MAIL_SPF") or "v=spf1 mx -all"
    args.dmarc = args.dmarc or env("MAIL_DMARC") or "v=DMARC1; p=quarantine; rua=mailto:test.noreply909@gmail.com"
    if not args.ip:
        print("Missing MAIL_SERVER_IP or VPS_IP", file=sys.stderr)
        return 2

    if args.no_dkim:
        args.dkim_file = None
    elif args.dkim_file:
        args.dkim_file = Path(args.dkim_file)
    else:
        path = default_dkim_path(args.domain)
        args.dkim_file = path if path.exists() else None
    args.zone_file = Path(args.zone_file) if args.zone_file else None

    zone_id = args.zone_id or zone_id_for_name(token, args.zone_name)
    records = build_records(args)
    for record in records:
        upsert_record(token, zone_id, record, dry_run=args.dry_run)
    if not args.dkim_file:
        print("note   DKIM skipped; run again with --dkim-file after mailserver generates mail.txt")


if __name__ == "__main__":
    raise SystemExit(main())
