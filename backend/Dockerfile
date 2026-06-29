FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY backend ./backend
RUN python -m pip install --upgrade pip && python -m pip install .
EXPOSE 7860 8000 8001
CMD ["agentic-scd-dashboard"]
