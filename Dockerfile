FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# copy app
COPY . /app

RUN chmod +x /app/fetch_rates.py /app/fetch_entrypoint.sh /app/modules/exchange_rates/fetch_entrypoint.sh || true

EXPOSE 5000

# gunicorn (gthread) instead of the Flask dev server: the dev server is
# single-process and was running with debug=True in production.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--worker-class", "gthread", "--threads", "8", "--timeout", "60", "--graceful-timeout", "30", "--keep-alive", "15", "--access-logfile", "-", "app:app"]
