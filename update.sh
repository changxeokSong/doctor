#!/usr/bin/env bash
# 이미 deploy-*.sh로 최초 배포가 끝난 서버에서, 이후 코드 변경분만 반영할 때 쓰는 스크립트.
# './update.sh' 한 번이면 git pull부터 프론트엔드 재빌드까지 끝난다.
#
# 백엔드(backend/pipeline, app/)는 docker-compose.yml에서 코드가 볼륨 마운트돼 있고 Django
# runserver가 StatReloader로 파일 변경을 자동 감지하므로, git pull만으로 이미 반영된다(재빌드·
# 재기동 불필요). 반면 프론트엔드는 Dockerfile에서 `npm run build` 결과물을 이미지 안에 굽기
# 때문에 git pull만으로는 반영되지 않아 이미지 재빌드 + 컨테이너 재기동이 꼭 필요하다
# (2026-08-31, 사용자 요청 - "git pull하면 바로 쓸 수 있게").
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

echo "=== 1. git pull ==="
git pull

echo
echo "=== 2. 프론트엔드 재빌드 ==="
docker compose build frontend

echo
echo "=== 3. 프론트엔드 재기동 ==="
docker compose up -d frontend

echo
echo "=== 완료 ==="
echo "백엔드는 코드가 볼륨 마운트돼 있어 git pull만으로 이미 자동 반영됨(StatReloader)."
echo "requirements.txt(파이썬 패키지)나 frontend/package.json(node 패키지)이 바뀐 경우엔"
echo "이 스크립트만으로 부족하다 - 그때는 'docker compose build backend'(또는 frontend)를"
echo "따로 한 번 더 실행할 것."
