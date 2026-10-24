FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

COPY requirements.txt .
RUN pip install --default-timeout=100 --retries 5 --no-cache-dir -r requirements.txt

COPY worker.py .

CMD ["python", "-u", "worker.py"]
