---
name: gloss-recommender-team
description: 통증의학과 문진 → 수어 글로스 추천기 프로젝트(Django 백엔드 app/·backend, React/Vite 프론트엔드, Docker 배포)에서 기능 추가·버그 수정·리팩터링·배포 변경 작업을 할 때 반드시 사용. "임베딩 모델", "표제어", "gloss", "글로스", "문진", "분류기", "코퍼스", "docker-compose", "배포 스크립트", "update.sh", "deploy-dgxspark", "deploy-x86" 등의 키워드나 이 저장소(app/config.py, backend/pipeline, frontend/src) 경로가 언급되면 트리거한다. 후속 요청("다시 확인해줘", "이것도 반영해줘", "그 기능 수정", "배포 다시", "이전 작업 보완")에도 재사용한다. 단순 질문(코드가 왜 이렇게 짜였는지 설명 등)은 오케스트레이터 없이 직접 답해도 된다.
---

# 수어 글로스 추천기 개발팀 오케스트레이터

## Phase 0: 컨텍스트 확인

작업 시작 전에 먼저 확인한다.

1. `_workspace/gloss-team/` 존재 여부 확인
   - 존재 + 사용자가 이전 작업의 부분 수정/보완 요청 → **부분 재실행**: 관련 에이전트만
     `SendMessage`로 재소환(팀이 이미 없으면 아래 팀 생성부터).
   - 존재 + 완전히 새 기능/버그 요청 → 기존 `_workspace/gloss-team/`을
     `_workspace/gloss-team_prev/`로 옮기고 **새 실행**.
   - 미존재 → **초기 실행**.
2. 요청 범위 파악 — 백엔드/ML만인지, 프론트엔드만인지, 배포/인프라만인지, 여러 영역이 겹치는지.
   영역이 하나뿐이고 검증까지 필요 없는 아주 작은 변경(오타 수정 등)이면 팀을 만들지 않고
   해당 에이전트 하나만 `Agent` 도구로 직접 호출해도 된다(오버헤드 절감).

## Phase 1: 팀 구성

**실행 모드: 에이전트 팀** (2개 이상 영역이 겹치는 일반적인 경우).

```
TeamCreate(team_name: "gloss-recommender", members: 요청 범위에 맞게 선택)
```

- 항상 필요: 작업 영역에 해당하는 에이전트(`ml-backend`/`frontend`/`devops` 중 관련된 것)
- 기능/버그 수정이 코드 변경을 동반하면 `qa`를 반드시 포함한다(경계면 검증)
- 순수 문서/커밋 메시지 정리처럼 코드 변경이 없는 작업은 `qa` 생략 가능

각 에이전트는 `.claude/agents/{ml-backend,frontend,devops,qa}.md` 정의를 그대로 따른다.
모든 `Agent`/`TeamCreate` 호출에 `model: "opus"`를 명시한다.

## Phase 2: 작업 분배

`TaskCreate`로 작업을 쪼개서 담당 에이전트에게 배정한다. 의존관계가 있으면
(예: 백엔드 API shape이 먼저 정해져야 프론트가 타입을 맞출 수 있음) `TaskUpdate`로 순서를
명시한다.

**데이터 전달**:
- 태스크 기반(`TaskCreate`/`TaskUpdate`) — 작업 상태·의존관계
- 메시지 기반(`SendMessage`) — API shape 변경, 경로/포트 변경처럼 실시간으로 맞춰야 하는 정보
- 파일 기반 — 큰 산출물(예: 여러 파일에 걸친 설계 결정)은 `_workspace/gloss-team/`에 기록,
  파일명 규칙: `{순번}_{에이전트}_{내용}.md`

## Phase 3: 검증

코드 변경이 있었다면 `qa`에게 경계면 검증을 요청한다. 실제로 서버/브라우저를 띄워 확인하는 것을
우선한다(코드만 읽고 판단하지 않는다) — `.claude/agents/qa.md`의 검증 체크리스트 참고.

## Phase 4: 종합 및 정리

- 결과를 사용자에게 요약 보고한다(무엇을 바꿨는지, 검증 결과, 남은 이슈가 있다면 명시).
- `_workspace/gloss-team/`은 감사 추적용으로 남겨둔다(삭제하지 않음).
- 팀을 정리한다(다음 요청이 이어질 걸 알고 있으면 유지해도 된다).

## 에러 핸들링

- 에이전트가 실패하면 1회 재시도한다. 재시도도 실패하면 해당 부분 없이 진행하고, 최종 보고서에
  "이 부분은 실패했다"고 명시한다 — 조용히 누락시키지 않는다.
- 두 에이전트가 같은 파일을 두고 다른 결정을 내리면(예: ml-backend와 devops가 경로 상수를
  다르게 이해) 자동으로 한쪽을 지우지 않고, 오케스트레이터가 사용자에게 확인한다.

## 팀 크기

기본 4명(ml-backend/frontend/devops/qa). 작업 범위가 한 영역뿐이면 그 영역 에이전트 + qa만
소집해도 된다 — 4명을 매번 다 부를 필요는 없다.

## 테스트 시나리오

**정상 흐름**: "임베딩 모델 선택 후보에 새 모델 하나 추가해줘" →
`ml-backend`가 `app/config.py`의 `EMB_MODEL_OPTIONS`에 항목 추가 →
`qa`가 `GET /api/embedding-models/` 응답에 새 옵션이 나오는지, `frontend`의 드롭다운에
자동으로 반영되는지(별도 프론트 코드 변경 불필요) 확인 → 완료 보고.

**에러 흐름**: "포트를 8778에서 다른 값으로 바꿔줘" 중 `devops`가 `docker-compose.yml`은
바꿨지만 `backend/config/settings.py`의 CORS 목록을 놓친 경우 → `qa`가 grep으로 이전 포트
값이 settings.py에 남아있는 걸 발견 → `devops`에게 구체적으로 리포트 → `devops`가 수정 →
`qa` 재검증 후 완료.
