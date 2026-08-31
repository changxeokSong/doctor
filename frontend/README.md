# React 프론트엔드

Vite + React + TypeScript + Tailwind + TanStack Query. Django 백엔드(`backend/`, `:8000`)를 호출한다.

## 실행

```bash
cd frontend
npm install   # 최초 1회
npm run dev   # http://localhost:5173, /api/* 요청은 :8000으로 자동 프록시(vite.config.ts)
```

백엔드(`backend/`)를 먼저 `:8000`에 띄워둬야 한다.

## 구조

- `src/api/types.ts` — 백엔드 응답 타입(백엔드 `pipeline/services.py`와 1:1 대응)
- `src/api/client.ts` — fetch 래퍼
- `src/components/` — `Sidebar`(설정/모델선택/데이터셋현황), `QuestionInput`, `PredictionResult`,
  `CandidatesPanel`(답변후보 + 키워드/표제어 매핑)
- `src/App.tsx` — 위 컴포넌트들을 엮는 오케스트레이션(기존 `demo_app.py`와 동일한 역할)
