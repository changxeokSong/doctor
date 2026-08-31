#!/usr/bin/env bash
# 일반 x86_64 + GPU 2장 서버 전용 - backend=GPU 0 / jungwoo=GPU 1로 물리 분리(docker-compose.x86-2gpu.yml).
# 전제조건: Docker Engine + Compose plugin, NVIDIA 드라이버 + nvidia-container-toolkit.
# GPU가 1장뿐이거나 DGX Spark라면 이 스크립트가 아니라 ./deploy-dgxspark.sh를 쓸 것.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
compose_files=(-f docker-compose.yml -f docker-compose.x86-2gpu.yml)

echo "=== 1. 필수 파일 확인 ==="
# corpus/·jungwoo/는 git 포함이라 clone만 하면 존재 - 별도 복사가 필요한 건 models/(git 미포함)뿐.
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
gpu_check_image="nvidia/cuda:12.1.1-runtime-ubuntu22.04"
if docker run --rm --gpus all "$gpu_check_image" nvidia-smi >/dev/null 2>&1; then
  echo "  ✓ GPU 컨테이너 접근 확인됨 — GPU 가속으로 실행된다."
  n_gpus=$(docker run --rm --gpus all "$gpu_check_image" nvidia-smi -L | wc -l)
  if [ "$n_gpus" -lt 2 ]; then
    echo "  ⚠ GPU가 ${n_gpus}장만 보인다(이 스크립트는 backend=GPU 0/jungwoo=GPU 1을 요구) —"
    echo "    docker-compose.x86-2gpu.yml의 device_ids를 서버 실제 GPU 개수에 맞게 고치거나,"
    echo "    GPU가 1장뿐이면 이 스크립트 대신 ./deploy-dgxspark.sh(GPU 1장 구성)를 쓸 것."
  fi
else
  echo "  ⚠ GPU 컨테이너 접근 실패 — nvidia-container-toolkit 미설치이거나 GPU가 없는 서버로 보인다."
  echo "    이 경우 docker-compose.x86-2gpu.yml의 deploy.resources.reservations.devices 블록을 지우고"
  echo "    CPU로만 실행해야 한다(분류기·생성기·키워드추출이 느려짐, app/device.py가 자동으로 CPU 폴백함)."
fi

echo
echo "=== 4. 이미지 빌드 ==="
docker compose "${compose_files[@]}" build

echo
echo "=== 5. 기동 ==="
docker compose "${compose_files[@]}" up -d

echo
echo "=== 완료 ==="
echo "백엔드:   http://localhost:8000/api/embedding-models/  (헬스체크용)"
echo "프론트엔드: http://localhost:8778/"
echo "로그 보기: docker compose ${compose_files[*]} logs -f"
echo "종료:      docker compose ${compose_files[*]} down"
