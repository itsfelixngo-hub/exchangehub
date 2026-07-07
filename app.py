try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from modules.exchange_rates.app import app, ensure_db


if __name__ == "__main__":
    ensure_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
