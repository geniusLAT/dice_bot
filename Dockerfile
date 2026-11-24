FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py service.py dice_parser.py telegram_replies.py ./
CMD ["python", "main.py"]
