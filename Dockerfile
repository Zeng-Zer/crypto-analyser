FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY visuals ./visuals
RUN uv sync --locked --no-editable

RUN useradd --create-home --uid 10001 app && chown -R app:app /app

ENV PATH="/app/.venv/bin:$PATH"

USER app

EXPOSE 8000

CMD ["crypto-analyser", "live", "--host", "0.0.0.0", "--port", "8000"]
