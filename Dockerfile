# Python slim + Tesseract + языки
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Системные либы для tesseract/pillow/pymupdf
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-rus tesseract-ocr-kaz tesseract-ocr-eng \
    libglib2.0-0 libsm6 libxext6 libxrender1 \
    && rm -rf /var/lib/apt/lists/*

# (опционально) если нужен явный TESSDATA_PREFIX
ENV TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

# скопируй код
COPY . .

# порт API
EXPOSE 8000

# переменные по умолчанию для OCR/LLM (их можно переопределять в Coolify UI)
ENV USE_OCR=1 \
    OCR_LANGS="rus+kaz+eng" \
    OCR_DPI=300 \
    OCR_MIN_CHARS=60 \
    OCR_SAMPLING_STEP=10 \
    OCR_SECOND_PASS_PAGES=30 \
    OCR_MAX_PAGES_DOC=20 \
    OLLAMA_URL="http://<GPU_SERVER_IP>:11434" \
    OLLAMA_NUM_CTX=3072 \
    NUM_PREDICT=512 \
    STAC_MODEL="medaudit:stac-strict" \
    API_LANG=ru

# CORS: добавь свои домены фронта через переменную API_CORS (комой)
ENV API_CORS="*"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
