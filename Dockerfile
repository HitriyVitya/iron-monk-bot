FROM python:3.11-slim

WORKDIR /app

# Ставим системные утилиты и sing-box
RUN apt-get update && apt-get install -y curl wget unzip libfreetype6-dev libpng-dev && rm -rf /var/lib/apt/lists/*
RUN wget https://github.com/SagerNet/sing-box/releases/download/v1.8.5/sing-box-1.8.5-linux-amd64.tar.gz \
    && tar -xvf sing-box-1.8.5-linux-amd64.tar.gz \
    && cp sing-box-1.8.5-linux-amd64/sing-box . \
    && chmod +x sing-box \
    && rm -rf sing-box-1.8.5-linux-amd64*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
EXPOSE 8080
CMD ["python", "main.py"]
