# jungwoo/app.py 전용 Streamlit 앱 — 메인 프로젝트와 완전히 독립된 이미지(코드·의존성 분리),
# 단 GPU는 같이 쓴다(사용자 요청, 2026-07-27) — 베이스 이미지를 메인 backend와 동일하게 맞춰서
# torch가 이미 CUDA에 맞게 설치돼 있는 상태로 시작한다.
# 2026-08-10: DGX Spark(GB10 Grace Blackwell 단일칩, arm64/sm_121) 대응으로 베이스 이미지를
# backend와 동일하게 NGC PyTorch 컨테이너로 교체(자세한 이유는 Dockerfile.backend 참고).
# ⚠ GB10은 물리적으로 GPU가 1장뿐이라(통합 SoC) 메인 앱(분류기+임베딩 최대 8종)과 반드시 같은
# GPU·같은 128GB 통합 메모리 풀을 공유한다 — 예전처럼 카드를 분리해서 VRAM을 나눌 방법이 없으므로
# 동시에 무거운 모델을 여러 개 올리면 OOM 위험이 이전보다 더 크다.
FROM nvcr.io/nvidia/pytorch:25.11-py3

WORKDIR /srv

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY jungwoo/requirements.txt .
# 2026-08-10(ISSUE-93): --no-cache-dir → BuildKit 캐시 마운트 — 이유는 Dockerfile.backend 참고.
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.txt

COPY jungwoo/ ./

ENV PYTHONUNBUFFERED=1
EXPOSE 8501

# --server.baseUrlPath=jungwoo: nginx가 /jungwoo/ 하위 경로로 프록시하므로 Streamlit도
# 같은 하위 경로 기준으로 정적 리소스·웹소켓 경로를 생성하게 맞춰야 한다.
# --server.enableCORS/XsrfProtection=false: 리버스 프록시 뒤에서 흔히 겪는 403/연결 문제 방지.
CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", "--server.address=0.0.0.0", \
     "--server.baseUrlPath=jungwoo", \
     "--server.enableCORS=false", "--server.enableXsrfProtection=false", \
     "--browser.gatherUsageStats=false"]
