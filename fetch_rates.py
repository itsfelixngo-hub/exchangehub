try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from modules.exchange_rates.fetch_rates import main


if __name__ == "__main__":
    main()
