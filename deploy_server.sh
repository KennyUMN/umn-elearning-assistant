#!/bin/bash
set -e

echo "🚀 Mempersiapkan UMN E-Learning Assistant di Home Server..."

# 1. Update system & install dependencies
if command -v apt-get &> /dev/null; then
    echo "📦 Menginstall dependencies sistem (Tesseract OCR & Python)..."
    sudo apt-get update -y
    sudo apt-get install -y python3 python3-venv python3-pip tesseract-ocr tesseract-ocr-ind tesseract-ocr-eng poppler-utils
fi

# 2. Setup Virtual Environment
if [ ! -d "venv" ]; then
    echo "🐍 Membuat Python Virtual Environment..."
    python3 -m venv venv
fi

echo "📦 Menginstall modul Python..."
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

# 3. Setup Systemd Service (Optional)
if [ -d "/etc/systemd/system" ]; then
    CURRENT_DIR=$(pwd)
    CURRENT_USER=$(whoami)

    echo "⚙️ Mendaftarkan systemd background service..."
    sed -i "s|WorkingDirectory=.*|WorkingDirectory=${CURRENT_DIR}|g" umn-assistant.service
    sed -i "s|ExecStart=.*|ExecStart=${CURRENT_DIR}/venv/bin/python main.py|g" umn-assistant.service
    sed -i "s|User=.*|User=${CURRENT_USER}|g" umn-assistant.service

    sudo cp umn-assistant.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable umn-assistant
    sudo systemctl restart umn-assistant
    echo "✅ Service aktif! Cek status dengan: sudo systemctl status umn-assistant"
fi

echo "🎉 Deployment selesai!"
