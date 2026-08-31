#!/usr/bin/env bash
# 이미 deploy-*.sh로 최초 배포가 끝난 서버에서, 이후 코드 변경분만 반영할 때 쓰는 스크립트.
# 백엔드는 코드가 볼륨 마운트+StatReloader라 git pull만으로 반영되지만, 프론트엔드는 이미지 안에
# 빌드 결과물을 굽기 때문에 재빌드+재기동이 필요하다.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

# deploy-*.sh가 남긴 .deploy-mode로 x86-2gpu 오버레이 필요 여부를 판단(GPU 분리 설정 유지용)
compose_files=(-f docker-compose.yml)
if [ -f .deploy-mode ] && [ "$(cat .deploy-mode)" = "x86-2gpu" ]; then
  compose_files+=(-f docker-compose.x86-2gpu.yml)
fi

echo "=== 1. git pull ==="
git pull

echo
echo "=== 2. 프론트엔드 재빌드 ==="
docker compose "${compose_files[@]}" build frontend

echo
echo "=== 3. 프론트엔드 재기동 ==="
docker compose "${compose_files[@]}" up -d frontend

echo
echo "=== 완료 ==="
echo "백엔드는 코드가 볼륨 마운트돼 있어 git pull만으로 이미 자동 반영됨(StatReloader)."
echo "requirements.txt(파이썬 패키지)나 frontend/package.json(node 패키지)이 바뀐 경우엔"
echo "이 스크립트만으로 부족하다 - 그때는 'docker compose ${compose_files[*]} build backend'"
echo "(또는 frontend)를 따로 한 번 더 실행할 것."
