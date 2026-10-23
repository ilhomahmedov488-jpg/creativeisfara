FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home studio
COPY --chown=studio:studio backend/ .
COPY --chown=studio:studio frontend/ /frontend/
RUN mkdir -p /app/media /app/staticfiles && chown -R studio:studio /app/media /app/staticfiles
USER studio
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "60", "--access-logfile", "-"]
