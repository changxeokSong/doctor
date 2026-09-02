# ── 베이스 이미지: Python 3.11 slim ──────────────────────────────────
FROM python:3.11-slim

# 시스템 의존성 (kiwipiepy 빌드 + 한국어 로케일)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── PyTorch CPU-only 먼저 설치 (GPU 불필요 → 이미지 크기 대폭 감소) ──
RUN pip install --no-cache-dir \
    torch==2.4.0 torchvision==0.19.0 torchaudio==2.4.0 \
    --index-url https://download.pytorch.org/whl/cpu

# ── 나머지 패키지 ────────────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── 앱 소스 및 데이터 복사 ─────────────────────────────────────────
COPY . .

# HuggingFace 모델 캐시 경로 설정 (볼륨 마운트 대상)
ENV HF_HOME=/app/.cache/huggingface
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0
ENV STREAMLIT_SERVER_PORT=8501
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

EXPOSE 8501 8502

# 기본 실행: Streamlit Q&A 앱
CMD ["python", "-m", "streamlit", "run", "app.py", \
     "--server.address", "0.0.0.0", \
     "--server.port", "8501"]
