FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

COPY requirements.txt ./
COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /usr/local/bin/uv
RUN uv pip install --system --no-cache -r requirements.txt

COPY app ./app
COPY database ./database

RUN useradd --create-home --uid 10001 tradevalue \
    && chown -R tradevalue:tradevalue /app
USER tradevalue

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers"]
