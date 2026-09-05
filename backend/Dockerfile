FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml /app/pyproject.toml
COPY alembic.ini /app/alembic.ini
COPY backend/app /app/backend/app
COPY backend/migrations /app/backend/migrations
COPY backend/worker.py /app/backend/worker.py
COPY backend/campaign_service.py /app/backend/campaign_service.py
COPY backend/lead_monitor_service.py /app/backend/lead_monitor_service.py
RUN pip install --no-cache-dir .
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
ENV PYTHONPATH=/app/backend
USER appuser
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
