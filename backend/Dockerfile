FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

COPY backend/requirements.lock ./backend/requirements.lock
RUN pip install --no-cache-dir -r backend/requirements.lock

COPY backend/app ./backend/app

COPY knowledge ./knowledge

# Non-root: this service never needs to write anywhere.
RUN useradd --create-home --uid 10001 mentor && chown -R mentor /app
USER mentor

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "backend"]
