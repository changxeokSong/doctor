# 통증의학과 문진 → 수어 글로스 추천기

- 의사 질문 입력 → 환자 답변용 한국수어(KSL) 표제어 추천
- LLM 없이 임베딩 유사도 기반

## 실행

```bash
git clone <이 저장소 URL>
cd doctor

# models/ 폴더만 별도 준비 (용량 커서 git 미포함 - models/README.md 참고)

./deploy-dgxspark.sh    # DGX Spark(GPU 1장) 서버
./deploy-x86-2gpu.sh    # 일반 x86_64 + GPU 2장 서버
```

- 백엔드: http://localhost:8000
- 프론트엔드: http://localhost:8778 (첫 화면에서 데모 2개 중 선택)

## 데모 2개

**demo1** (`/demo1`) — 메인 데모

- 파이프라인: 질문 분류(단계/세부분류) → 코퍼스 검색 → 답변 키워드 추출 → 표제어(gloss) 임베딩 매칭

**demo2** (`/jungwoo/`) — BM25 하이브리드 검색 데모

- 파이프라인: BM25 + BERT 임베딩 하이브리드 검색 → 답변 매칭
- 메인과 완전히 별개 앱 (자체 코드/의존성)

## 업데이트

```bash
./update.sh   # git pull + 프론트엔드 재빌드/재기동, 한 번에 처리
```
