# 통증의학과 문진 → 수어 글로스 추천기

환자가 문진에 답한 내용을 한국수어(KSL) 글로스로 옮길 때 쓸 표제어 후보를 추천하는 시스템.
의사 질문 → (단계/세부분류 분류 + 코퍼스 검색) → 답변 키워드 추출 → 표제어 사전 임베딩 매칭
순서로 동작하며, LLM은 쓰지 않는다(임베딩 유사도 기반).

## 구조

```
app/                 실제 로직(모델 추론, 검색, NLP, 표제어 매핑) - 전부 여기 있음
backend/             Django REST API. app/을 감싸는 얇은 레이어(backend/README.md 참고)
frontend/            React/Vite 데모 화면(frontend/README.md 참고)
models/              모델 가중치(git 미포함 - 아래 "모델 준비" 참고)
models/README.md     어떤 모델이 실제 배포판이고 어떤 게 폐기된 실험인지 정리
jungwoo/              BM25 하이브리드 검색 데모(별개 앱)
data/, notebooks/, reports/, analysis/, scripts/   학습·분석·리포트 원본(git 미포함, 로컬에만 존재)
```

## 실행

### 백엔드

`backend/README.md` 참고. 요약:

```bash
conda create -n django_backend --clone base -y   # 최초 1회
conda run -n django_backend pip install -r backend/requirements.txt
conda run -n django_backend python backend/manage.py runserver 8000   # 항상 저장소 루트에서
```

### 프론트엔드

`frontend/README.md` 참고. 요약:

```bash
cd frontend
npm install
npm run dev
```

## 모델 준비 (git에 안 올라가 있음)

`models/`, `checkpoints/`는 전체 17GB가 넘고 그중 데모에 실제로 필요한 파일 2개도 각각
100MB(분류기 1.3GB, 키워드 추출기 423MB)를 넘어 GitHub 자체에 못 올린다(100MB 파일 크기 제한).
그래서 `.gitignore`로 빼고, 데모를 돌리는 데 정확히 필요한 것만 아래에 적어둔다 — 이 두 폴더를
저장소 루트의 같은 경로에 별도로 받아서 넣으면 된다.

| 경로 | 역할 | 크기 |
|---|---|---|
| `models/deployed/model_final/` | 문진단계·세부분류 분류기(klue/roberta-large) | 1.3GB |
| `models/experiments/keyword_extractor_model_v2_deployed_until_20260725_backup/` | 답변 키워드 추출기 v2(대표 키워드 1개, 세부분류 맥락 반영) | 423MB |

두 경로 모두 `app/config.py`의 `MODEL_DIR`/`KEYWORD_MODEL_DIR` 상수가 그대로 가리키는 경로라서
폴더명을 바꾸면 안 된다. 나머지(`models/experiments/`의 다른 폴더들)는 전부 기각된 실험/백업이라
데모 실행에는 필요 없다 — 뭐가 왜 기각됐는지는 `models/README.md` 참고.

## 표제어 사전 · 코퍼스 엑셀

저장소 루트에 있는 3개 xlsx는 실제로 git에 포함돼 있고(용량이 작음), `app/config.py`가 파일명
그대로 상대경로로 읽는다 — 실행 시 반드시 저장소 루트가 작업 디렉터리여야 한다.

- `ETRI_KSL_Dictionary_r40_서강대658_20260725.xlsx` — 표제어 사전(655개)
- `통증의학과_초진_의사문의_답변_키워드_이현_0528.xlsx` — 질문/답변 검색용 코퍼스
- `통증의학과_모델입력_균형보강_학습준비본_0528.xlsx` — 분류기 학습 데이터
