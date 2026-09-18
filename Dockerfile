# ============================================================
#  CardCheckout API - Dockerfile
#  يستخدم Python 3.11 (متوافق مع FastAPI + curl-cffi)
# ============================================================

# 1. استخدام Python 3.11 (أكثر استقراراً لمكتبة curl-cffi)
FROM python:3.11-slim

# 2. تعيين مجلد العمل
WORKDIR /app

# 3. تثبيت التبعيات الأساسية المطلوبة لـ curl-cffi
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# 4. نسخ ملف المتطلبات أولاً (للاستفادة من caching)
COPY requirements.txt .

# 5. تثبيت المتطلبات
RUN pip install --no-cache-dir -r requirements.txt

# 6. نسخ باقي الملفات
COPY . .

# 7. فتح البورت (Railway هيحدد البورت تلقائياً)
EXPOSE 8000

# 8. تشغيل التطبيق (api_server.py وليس checker_api2)
CMD ["uvicorn", "api_server:app", "--host", "0.0.0.0", "--port", "8000"]
