# Quick-start app image: a Python 3.11 base with uv, the project copied in, and all
# dependencies (incl. the notebooks group) synced into an in-image venv. Compose brings
# this up **idle** alongside Postgres; the user then execs a run mode — CLI, Gradio, or
# Jupyter (see the README "Quick start"). No run mode is started for you.
FROM python:3.11-slim

# uv, copied from the official image (no pip bootstrap needed).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first for better layer caching: copy only the manifest + lock
# (and the README the build references), then sync deps WITHOUT the project itself.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project --group notebooks

# Copy the rest of the project and finish the (editable) install of the package.
COPY . .
RUN uv sync --frozen --group notebooks

# Gradio (7860) and Jupyter (8888) — published by compose when those modes are run.
EXPOSE 7860 8888

# Idle by default: the infrastructure is "up" but no run mode is chosen for you.
CMD ["sleep", "infinity"]
