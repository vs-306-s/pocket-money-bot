# Бот «Карманные деньги по оценкам»: Python + openpyxl для отчётов
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Europe/Moscow \
    DATA_DIR=/app/data

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# база и готовые отчёты живут в /app/data
VOLUME ["/app/data"]

CMD ["python", "main.py"]
