# 통증의학과 초진 Q&A · 글로스 추천

실제로 실행에 필요한 파일만 모은 패키지입니다.

## 구성

| 파일 | 역할 |
|---|---|
| `app.py` | Streamlit 검색 화면 |
| `api.py` | FastAPI (`POST /query`) |
| `core.py` | 데이터 로딩 · BM25/BERT 검색 · 글로스 추천 |
| `test_658_gloss_pool.json` | 글로스 풀 |
| `*0528*.xlsx` | Q&A 엑셀 |
| `.streamlit/config.toml` | 테마 (보라색 버튼, 연회색 배경) |

## 로컬 실행

```bash
pip install -r requirements.txt
python -m streamlit run app.py --server.address localhost --server.port 8501
```

API 서버:

```bash
python -m uvicorn api:app --host 0.0.0.0 --port 8502
```

- 화면: http://localhost:8501
- API: `POST http://localhost:8502/query`

## Docker

```bash
docker compose up --build
docker compose --profile api up --build
```
