#!/usr/bin/env python3
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from modules.exchange_rates.r2_storage import sync_uploads_dir


def main():
    uploads_dir = os.environ.get("WP_UPLOADS", "wp-content/uploads")
    uploaded = sync_uploads_dir(uploads_dir, include_root_files=("rates.html", "rates.json"))
    print(f"Uploaded {uploaded} file(s) from {uploads_dir} to Cloudflare R2")


if __name__ == "__main__":
    main()
