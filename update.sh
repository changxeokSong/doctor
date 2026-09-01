#!/usr/bin/env bash
# 이미 deploy-*.sh로 최초 배포가 끝난 서버에서, 이후 코드 변경분만 반영할 때 쓰는 스크립트.
# 백엔드는 코드가 볼륨 마운트+StatReloader라 git pull만으로 반영되지만, 프론트엔드는 이미지 안에
# 빌드 결과물을 굽기 때문에 재빌드+재기동이 필요하다.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

if [ -z "${UPDATE_SH_BEFORE:-}" ]; then
  # 1단계: pull부터 하고, update.sh 자신이 방금 바뀌었을 수 있으니 pull된 최신 버전으로 재실행한다
  # (bash는 실행 중인 스크립트 파일이 바뀌어도 이미 읽은 옛 내용으로 계속 돈다 - 재실행 없이는
  # 이 스크립트를 고친 커밋이 와도 한 번 더 수동으로 돌려야 반영됐다).
  echo "=== 1. git pull ==="
  before=$(git rev-parse HEAD)
  git pull
  # "$0"는 bash update.sh처럼 경로 없이 실행하면 그냥 "update.sh"라 env가 PATH에서 찾다 실패한다 -
  # 이미 스크립트 디렉터리로 cd한 상태이므로 "./update.sh"로 고정해서 실행 방식과 무관하게 한다.
  exec env UPDATE_SH_BEFORE="$before" "./$(basename "${BASH_SOURCE[0]}")" "$@"
fi

# 2단계: 여기부터는 항상 방금 pull한 최신 update.sh가 실행된다.
before="$UPDATE_SH_BEFORE"
changed=$(git diff --name-only "$before" HEAD)

# deploy-*.sh가 남긴 .deploy-mode로 x86-2gpu 오버레이 필요 여부를 판단(GPU 분리 설정 유지용)
compose_files=(-f docker-compose.yml)
if [ -f .deploy-mode ] && [ "$(cat .deploy-mode)" = "x86-2gpu" ]; then
  compose_files+=(-f docker-compose.x86-2gpu.yml)
fi

echo
echo "=== 2. 프론트엔드 재빌드 ==="
docker compose "${compose_files[@]}" build frontend

# requirements.txt는 이미지에 굽는 파이썬 패키지라 볼륨 마운트로 안 잡힌다 - 바뀌었으면 백엔드도 재빌드.
rebuild_backend=0
if echo "$changed" | grep -qx "requirements.txt"; then
  echo
  echo "=== requirements.txt 변경 감지 - 백엔드 이미지도 재빌드 ==="
  docker compose "${compose_files[@]}" build backend
  rebuild_backend=1
fi

echo
echo "=== 3. 재기동 ==="
docker compose "${compose_files[@]}" up -d frontend
if [ "$rebuild_backend" = "1" ]; then
  docker compose "${compose_files[@]}" up -d backend
fi

echo
echo "=== 완료 ==="
