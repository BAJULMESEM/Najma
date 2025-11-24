FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    ffmpeg \
    aria2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN python -m pip install --upgrade pip
RUN pip install -r /app/requirements.txt

COPY bot_voice.py /app/bot_voice.py
COPY start.sh /app/start.sh
COPY image.jpg /app/image.jpg

RUN chmod +x /app/start.sh

ENV TEMP=/app/temp
RUN mkdir -p /app/temp

CMD ["/app/start.sh"]
