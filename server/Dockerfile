FROM python:3.12-slim

RUN groupadd -r mq && useradd -r -g mq mq

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

RUN mkdir -p /app/data && chown -R mq:mq /app/data

USER mq

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python3 -c "from urllib.request import urlopen; urlopen('http://localhost:8000/healthz')"

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
