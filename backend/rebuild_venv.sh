#!/usr/bin/env bash
set -euo pipefail

# Hardcode path backend, jangan andalkan $0
cd /home/backend/project/ClipHub-v2/backend

# Fail-fast: pastikan requirements.txt benar-benar ada
if [[ ! -f requirements.txt ]]; then
  echo "FATAL: requirements.txt tidak ditemukan di $(pwd)"
  echo "Save dulu file requirements.txt di folder backend sebelum run script ini."
  exit 1
fi

echo "== 1. Matikan venv lama & hapus =="
deactivate 2>/dev/null || true
rm -rf venv

echo "== 2. Buat venv baru & upgrade pip/setuptools/wheel =="
python3.12 -m venv venv
./venv/bin/pip install --upgrade pip setuptools wheel

echo "== 3. Install torch trio (CUDA 12.1) — WAJIB --index-url, BUKAN --extra =="
# torch 2.5.1+cu121 cocok dengan NVIDIA driver 12.2 (12020)
./venv/bin/pip install \
  torch==2.5.1 \
  torchvision==0.20.1 \
  torchaudio==2.5.1 \
  --index-url https://download.pytorch.org/whl/cu121

echo "== 4. Install sisa dependency dari requirements.txt =="
./venv/bin/pip install -r requirements.txt

echo "== 5. Bersihkan distribusi invalid (~etuptools, ~yannote-core, ~umpy) =="
find ./venv/lib/python3.12/site-packages -maxdepth 1 -name '~*' -exec rm -rf {} +

echo "== 6. Verifikasi =="
./venv/bin/python3 -c "
import torch, torchaudio, torchvision
print('torch      :', torch.__version__)
print('torchvision:', torchvision.__version__)
print('torchaudio :', torchaudio.__version__)
print('CUDA avail :', torch.cuda.is_available())
"
./venv/bin/python3 -c "from rfdetr import RFDETRLarge; print('RF-DETR OK')"
./venv/bin/python3 -c "import pyannote.audio; print('PyAnnote OK')"
./venv/bin/python3 -c "import insightface; print('InsightFace OK')"
./venv/bin/python3 -c "import mediapipe; print('MediaPipe OK')"

echo "== Selesai. Jika semua baris di atas print 'OK' tanpa traceback, venv bersih. =="