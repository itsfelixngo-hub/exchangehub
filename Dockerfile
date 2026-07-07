FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# copy app
COPY . /app

RUN chmod +x /app/fetch_rates.py /app/fetch_entrypoint.sh /app/modules/exchange_rates/fetch_entrypoint.sh || true

EXPOSE 5000

CMD ["python", "app.py"]
