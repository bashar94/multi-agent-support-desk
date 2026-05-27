FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV SUPPORT_DESK_HOST=0.0.0.0
ENV SUPPORT_DESK_PORT=8080
ENV SUPPORT_DESK_DB=/app/.data/support_desk.sqlite3

WORKDIR /app

COPY . /app

ARG SUPPORT_DESK_EXTRAS=""
RUN if [ -n "$SUPPORT_DESK_EXTRAS" ]; then pip install --no-cache-dir ".[${SUPPORT_DESK_EXTRAS}]"; fi

EXPOSE 8080

CMD ["python", "-m", "supportdesk.server"]
