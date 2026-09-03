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

점수에 가산·보정을 일절 하지 않는다. 정렬도 순위 비교도 이 값 그대로다.

### 최종 목록을 추리는 3단계

```
① 근거 문턱(cutoff.minScore) 이상만 남김   — 질문마다 점수 분포 상위 topPercentile 지점에서 동적 결정
② 정확일치 > 표제어 우선 > 카테고리 우선 > 나머지 로 정렬  — 묶음 안에서는 점수 내림차순
③ 상위 cutoff.maxCount 개만 표시
```

**③에서 절대 점수로 자르지 않는 이유**: 임베딩 모델마다 유사도 스케일이 달라서, 같은 질문이라도
모델을 바꾸면 "0.65 이상"인 표제어 수가 수십 배까지 차이 난다. 개수로 자르면 모델과 무관하게
분량이 일정하다.

분석 페이지 3번 "추리는 순서"·"왜 개수로 자르나"·"점수 기준" 행에 그대로 표시된다.
`minScore`/`topPercentile`/`maxCount` 모두 하드코딩하지 않고 응답 필드를 읽는다.

> 이전에는 우선 카테고리 표제어에 점수 +0.05 가산(`CATEGORY_BOOST`)을 했고, 그다음엔 컷오프 문턱만
> 낮추는 방식(`CATEGORY_LENIENCY`)을 썼다. 둘 다 제거됐다 — 결과의 73%가 0.60~0.65 노이즈 구간에
> 뭉치는 문제가 문턱 조정으로는 해결되지 않아 개수 상한으로 바꿨다.

### 정렬은 3단 묶음

```
정확일치  >  ① 표제어 우선  >  ② 카테고리 우선  >  ③ 나머지     (묶음 안에서는 점수 내림차순)
```

- **표제어 우선** — `SUBCATEGORY_GLOSS_PRIORITY`. 세부분류별로 지정해둔 표제어 ID 목록.
- **카테고리 우선** — `SUBCATEGORY_CATEGORY_PRIORITY`. 세부분류에 어울리는 글로스 분류.
- 둘 다 **38개 세부분류 중 33개에** 정의돼 있다(전체 목록은 `backend/pipeline/services.py`의
  두 상수 참고). 규칙이 없는 5개(associated, general, adverse_reaction, sleep, skin_lesion)는
  순수 점수순 그대로다 — 단계마다 이름이 재사용되는데 한쪽 단계에만 맞는 후보라 일부러 제외했다.
  (단계)×(세부분류) 조합 기준으로는 48개 중 41개에 적용된다.
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
