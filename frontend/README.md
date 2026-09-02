# React 프론트엔드

Vite + React + TypeScript + Tailwind + TanStack Query. Django 백엔드(`backend/`, `:8000`)를 호출한다.
LLM 호출 없음 — 백엔드가 계산한 값을 그대로 렌더링만 한다.

## 실행

```bash
cd frontend
npm install   # 최초 1회
npm run dev   # http://localhost:8778/demo1, /api/* 는 :8000으로 프록시(vite.config.ts)
npm run build # tsc -b + vite build (배포는 정적 빌드가 이미지에 구워짐)
npm run lint  # oxlint
```

백엔드를 먼저 `:8000`에 띄워야 한다.

## 구조

- `src/api/types.ts` — 백엔드 응답 타입. **자동 생성이 아니라 수동 동기화**라, `pipeline/services.py`가
  필드를 바꾸면 여기도 같이 고쳐야 한다(런타임에 안 잡힌다).
- `src/api/client.ts` — fetch 래퍼
- `src/App.tsx` — 최상위 상태 + `main`/`dictionary`/`analysis` 3화면 전환
- `src/components/`
  - `QuestionInput` — 질문 입력
  - `CandidatesPanel` — `RecommendedGlossesTable`(핵심 표제어 표), `RecommendationStats`, `ResultJsonViewer`
  - `AnalysisPanel` — 분석 페이지(분류 → 검색 → 답변 Pool → 컷오프 → 순위 재배정 → 소요시간)
  - `GlossDictionaryPage` — 글로스 사전 전체 + 문진단계·세부분류 현황 + 최근 출력 목록
- `src/reference.css` — 참고 사이트(LLM 기반 시스템) 원본 CSS. **함부로 수정하지 않는다.**
  우리 전용 규칙은 파일 하단 "우리 화면 전용" 블록에만 추가한다(`.rank-table`, `.priority-badge*`).
- `src/utils/gloss.ts` — `stripCategory()`(카테고리 접두어 제거)

## 표제어 점수·정렬 규칙 (화면 해석에 필요)

### 표시되는 "점수"는 순수 임베딩 유사도다

세부분류의 우선 카테고리에 속하는 표제어는 점수를 조작하지 않고, 대신 **근거 인정 컷오프 문턱을
`analysis.cutoff.categoryLeniency`만큼 낮춰서** 통과시킨다(정확일치는 애초에 컷오프 대상이 아님).
그래서 유사도가 근거 문턱을 아깝게 못 넘어 통째로 탈락하는 표제어를 살리면서도, 화면의 "점수"·
"점수 순위"는 항상 순수 유사도 그대로다. 분석 페이지 3번 "점수 기준" 행과 "컷오프" 행에 표시된다.
값은 하드코딩하지 않고 응답의 `categoryLeniency` 필드를 그대로 읽는다.

### 정렬은 3단 묶음

```
정확일치  >  ① 표제어 우선  >  ② 카테고리 우선  >  ③ 나머지     (묶음 안에서는 점수 내림차순)
```

- **표제어 우선** — `SUBCATEGORY_GLOSS_PRIORITY`. 세부분류별로 지정해둔 표제어 ID 목록.
- **카테고리 우선** — `SUBCATEGORY_CATEGORY_PRIORITY`. 세부분류에 어울리는 글로스 분류.
- 둘 다 **49개 세부분류 중 8개에만** 정의돼 있다(location, side, chief_complaint, surgery_site,
  pain_score, quality, prior_treatment, treatment_choice). 나머지 41개는 순수 점수순 그대로다.
- 그래서 점수가 낮은 표제어가 높은 표제어보다 위에 오는 일이 생긴다 — 버그가 아니라 이 규칙 때문이다.

`AnalysisPanel.describeOrder()`는 이 문구를 **하드코딩하지 않고 응답 순서에서 역으로 판별한다** —
백엔드 정렬키가 바뀌어도 화면 설명이 실제와 어긋나지 않게 하기 위함. 정확일치는 묶음과 무관하게
맨 앞으로 빠지므로 판별에서 제외한다.

### 화면에서 확인하는 법

- **우선순위 배지** — "글로스·문진 현황"의 최근 출력 표. 앞당겨진 행에 `표제어 우선`/`카테고리 우선` 배지.
  출처 배지(`.source-badge`)와 의미 축이 달라 클래스를 분리했다(`.priority-badge*`).
- **스코어 정렬 토글** — 같은 표의 "스코어" 헤더 클릭 → 점수 내림차순, 재클릭 → 백엔드 순서 복귀.
- **순위 재배정** — 분석 페이지 3번. 점수 순위 대비 몇 칸 움직였는지와 사유(`표제어 우선`/`카테고리 우선`/
  `밀림으로 인한 상승`)를 행별로 보여준다. 사유별 합계 = 전체 상승 행 수.

## 주의

- 상태 공유(임베딩 모델 선택 등)는 `App.tsx` state를 props로 내려 쓴다. 컴포넌트마다 따로 만들지 않는다.
- `recentOutputs`는 localStorage에 저장하고 **스키마를 검증**한다. 필드를 추가하면 `App.tsx`의 검증기도
  같이 늘려야 타입 선언(비옵셔널)과 저장값이 어긋나지 않는다. 검증에 걸린 옛 캐시는 조용히 버려지므로
  업그레이드 직후 최근 출력 목록이 한 번 비어 보인다(질문 1회 실행하면 복구).
- 타입 체크만으로 동작을 증명하지 않는다. `npm run dev`로 실제 브라우저에서 확인한다.
