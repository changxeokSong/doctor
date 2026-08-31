#!/usr/bin/env bash
# DGX Spark(GB10 Grace Blackwell, arm64/sm_121, GPU 물리 1장) 전용 배포 스크립트.
# 서버에 이 저장소 폴더를 통째로 복사한 뒤 './deploy-dgxspark.sh' 한 번만 실행하면 빌드+기동까지 끝난다.
# 전제조건(서버에 미리 설치돼 있어야 함):
#   - Docker Engine + Docker Compose plugin
#   - GPU를 쓰려면: NVIDIA 드라이버 + nvidia-container-toolkit
#     (설치 확인: `docker run --rm --gpus all nvcr.io/nvidia/cuda:13.0.1-devel-ubuntu24.04 nvidia-smi`가 성공해야 함)
#   - 2026-08-10: DGX Spark용으로 CUDA 13 태그 교체 — 기존 12.4.1 태그는 x86_64 기준이라 이 서버
#     아키텍처(Grace/aarch64)와 안 맞았다.
#
# GPU가 2장인 일반 x86_64 서버는 이 스크립트가 아니라 ./deploy-x86-2gpu.sh를 쓸 것.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

echo "=== 1. 필수 파일 확인 ==="
# corpus/의 xlsx 3개와 jungwoo/ 전체는 git에 포함돼 있어 git clone만 하면 이미 존재한다(2026-08-31부로
# 루트에 흩어져 있던 xlsx를 corpus/로 모으고 소스도 git 추적 대상이 됨) - 그래서 별도 복사가 필요한 건
# git에 못 올리는 모델 가중치(models/, 100MB 초과) 뿐이다. cache/는 없어도 첫 요청 때 자동 생성된다
# (아래에서 폴더만 미리 만들어둠).
missing=0
for f in \
  "corpus/통증의학과_초진_의사문의_답변_키워드_이현_0528.xlsx" \
  "corpus/통증의학과_모델입력_균형보강_학습준비본_0528.xlsx" \
  "corpus/ETRI_KSL_Dictionary_r40_서강대658_20260725.xlsx"
do
  if [ ! -f "$f" ]; then
    echo "  ✗ 없음: $f (git clone이 아니라 zip 등으로 일부만 받은 건 아닌지 확인할 것)"
    missing=1
  else
    echo "  ✓ 있음: $f"
  fi
done
if [ ! -d "models" ]; then
  echo "  ✗ 폴더 없음: models/ (모델 체크포인트 - git에 안 올라가 있음, README.md '모델 준비' 절 참고)"
  missing=1
else
  echo "  ✓ 있음: models/ ($(du -sh models 2>/dev/null | cut -f1))"
fi
if [ "$missing" = "1" ]; then
  echo
  echo "필수 파일/폴더가 빠져있다. README.md '모델 준비' 절을 참고해 models/를 채워둘 것."
  exit 1
fi
mkdir -p logs backups cache

echo
echo "=== 2. Docker 확인 ==="
if ! command -v docker >/dev/null 2>&1; then
  echo "docker가 설치돼 있지 않다. https://docs.docker.com/engine/install/ 참고해 먼저 설치할 것."
  exit 1
fi
docker compose version >/dev/null 2>&1 || { echo "docker compose(플러그인)가 없다. docker-compose-plugin 설치 필요."; exit 1; }

echo
echo "=== 3. GPU 확인(선택) ==="
if docker run --rm --gpus all nvcr.io/nvidia/cuda:13.0.1-devel-ubuntu24.04 nvidia-smi >/dev/null 2>&1; then
  echo "  ✓ GPU 컨테이너 접근 확인됨 — GPU 가속으로 실행된다."
else
  echo "  ⚠ GPU 컨테이너 접근 실패 — nvidia-container-toolkit 미설치이거나 GPU가 없는 서버로 보인다."
  echo "    이 경우 docker-compose.yml의 deploy.resources.reservations.devices 블록을 지우고"
  echo "    CPU로만 실행해야 한다(분류기·생성기·키워드추출이 느려짐, app/device.py가 자동으로 CPU 폴백함)."
fi

echo
echo "=== 4. 이미지 빌드 ==="
docker compose build

echo
echo "=== 5. 기동 ==="
docker compose up -d

echo
echo "=== 완료 ==="
echo "백엔드:   http://localhost:8000/api/embedding-models/  (헬스체크용)"
echo "프론트엔드: http://localhost:8778/"
echo "로그 보기: docker compose logs -f"
echo "종료:      docker compose down"
