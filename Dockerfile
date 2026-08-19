FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .
RUN mkdir -p data/inbox
ENV WEB_HOST=0.0.0.0
ENV WEB_PORT=8000
CMD ["python", "-m", "app.main"]
