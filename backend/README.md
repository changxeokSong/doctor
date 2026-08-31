# Django 백엔드

`app/` 패키지(모델 추론/검색/NLP)를 REST API로 감싼 얇은 레이어. 커스텀 DB 모델 없음(무상태).

## 실행 환경

heavy ML 의존성(torch/transformers/sentence-transformers/kiwipiepy 등)이 필요해서, base conda 환경을
그대로 클론한 `django_backend` 환경을 쓴다.

```bash
# 최초 1회만
conda create -n django_backend --clone base -y
conda run -n django_backend pip install -r backend/requirements.txt

# 실행 (항상 저장소 루트 doctor/ 에서, app/config.py의 엑셀 상대경로 때문)
conda run -n django_backend python backend/manage.py runserver 8000
```

## 엔드포인트 (`/api/...`)

- `POST /classify/` `{question}` → 단계/세부분류 예측
- `POST /retrieve/` `{question, subcategories[], top_k, max_examples, emb_model}` → 검색(retriever, 임베딩+DB 검색 — 생성 없음)
- `POST /keywords/` `{subcategory, answer, mode}` (mode: hybrid/v1/v2/v3/v4)
- `POST /gloss/` `{keywords[], top_k, emb_model}` → 표제어 매핑
- `POST /pipeline/` `{question, emb_model, similarity_threshold, gloss_top_k}` → 전체 플로우 한 번에
- `GET /embedding-models/` → 순위 포함 임베딩 모델 후보 목록
- `GET /gloss-dictionary/` → 표제어 사전 전체 목록 + 카테고리별 개수
- `GET /dataset-stats/` → 데이터셋 현황 표
- `GET /examples/?n=5` → 예시 질문 샘플
- `GET /labels/` → 단계/세부분류 라벨 목록

`pipeline/views.py`는 요청 검증(`serializers.py`)과 서비스 호출(`services.py`)만 하는 얇은 레이어이고,
실제 로직은 전부 `app/`에 있다 — 로직을 여기서 다시 구현하지 말 것.
