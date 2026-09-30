FROM python:3.11-slim

# Set timezone to Asia/Jakarta (WIB)
ENV TZ=Asia/Jakarta
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# tesseract/poppler tidak dipakai: parser hanya mengekstrak PDF/PPTX/DOCX (lihat
# src/document_parser.py). Hapus baris ini kalau suatu saat OCR gambar diaktifkan.
RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source files
COPY . .

# Run bot & background scheduler
CMD ["python", "main.py"]
