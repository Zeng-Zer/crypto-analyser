FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1

RUN useradd --create-home --uid 10001 app && install -d -o app -g app /app

WORKDIR /app

COPY --chown=app:app pyproject.toml uv.lock README.md ./
COPY --chown=app:app src ./src
COPY --chown=app:app visuals ./visuals

ENV PATH="/app/.venv/bin:$PATH"

USER app

RUN uv sync --locked --no-editable

EXPOSE 8000

CMD ["crypto-analyser", "live", "--host", "0.0.0.0", "--port", "8000"]
