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
- 프론트엔드: http://localhost:8778

## 업데이트

```bash
./update.sh   # git pull + 프론트엔드 재빌드/재기동, 한 번에 처리
```
