FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /usr/local/bin/uv
COPY requirements-ingestion.txt ./
RUN uv pip install --system --no-cache -r requirements-ingestion.txt
COPY src ./src
RUN useradd --create-home --uid 10001 tradevalue && chown -R tradevalue:tradevalue /app
USER tradevalue
# Downloads the season CSVs from TRADEVALUE_DATA_BLOB_URL, then runs ingestion against them.
CMD ["sh", "-c", "set -e; data_dir=$(mktemp -d); python -m app.ScriptingFiles.FullDataScript.fetch_data --destination \"$data_dir\"; TRADEVALUE_DATA_DIR=\"$data_dir\" exec python -m app.ScriptingFiles.FullDataScript.run_all"]
