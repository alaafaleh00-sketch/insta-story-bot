FROM python:3.10-slim

# تثبيت حزم النظام المطلوبة لبناء مكتبات الصور والتشفير
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt-get/lists/*

WORKDIR /app

# تحديث pip وتثبيت المتطلبات
RUN pip install --upgrade pip

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
