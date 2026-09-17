FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MAX_DB_PATH=/data/school_bot.db

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY maxbot ./maxbot

# база лежит на томе, чтобы расписание и домашка переживали пересборку образа
RUN mkdir -p /data
VOLUME ["/data"]

CMD ["python", "-m", "maxbot"]
