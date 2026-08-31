"""프로젝트 전역 경로/하이퍼파라미터 설정. 모든 모듈이 여기서 상수를 가져다 쓴다."""

# models/deployed/ = 지금 실제로 서비스에 쓰는 모델들. models/experiments/ = 재학습 시도했지만
# 기존을 못 이겨서(또는 아직 검증 중이라) 배포 안 한 것들 — 절대 헷갈리면 안 돼서 폴더 자체를 분리했다.
MODEL_DIR = "./models/deployed/model_final"

CORPUS_EXCEL = "corpus/통증의학과_초진_의사문의_답변_키워드_이현_0528.xlsx"
# 분류기 학습에 실제로 쓰인 소스 — label_maps.json의 라벨셋이 여기서 나왔다. 추론 자체는 이 엑셀을
# 읽지 않지만(모델에 라벨이 이미 고정돼 있음), 단계->세부분류 그룹핑을 보여줄 때 참고용으로 쓴다.
CLASSIFIER_TRAIN_EXCEL = "corpus/통증의학과_모델입력_균형보강_학습준비본_0528.xlsx"
CLASSIFIER_TRAIN_SHEET = "01_학습데이터_균형보강"
# 2026-08-19: 기본값을 ko-sroberta-multitask(범용)에서 snumin44/sap-bert-ko-en(의료 특화)로 교체.
# 계기: 표제어 중심 집계 기능을 만들다가 "고혈압" 쿼리에서 ko-sroberta 임베딩이 사실상 무너져있는 걸
# 발견함(동의어 1,894개 중 72개가 스코어 0.999+, 평균 유사도 0.63 — 완전 무관한 단어들까지 전부 높게
# 나옴). 같은 쿼리를 SAP-BERT-Ko-En으로 하면 "혈압" 0.7951이 1위로 정상 매칭됨. ISSUE-88 벤치마크에서도
# SAP-BERT-Ko-En이 gloss Recall@1 95.3%(ko-sroberta 86.5%보다 높음)·변별력 0.164(ko-sroberta
# 0.115보다 높음)로 정확도는 오히려 우세했고, 속도만 2.5~4배 느렸다(40.5ms vs 13~16ms — 절대값은
# 여전히 파이프라인 전체(~1-2s) 대비 작음)는 이유로 그동안 순위표 9위에 머물러 있었다. 이 프로젝트
# 도메인이 의료(통증의학과)라는 걸 감안해 정확도를 우선. ISSUE-90(임베딩 모델 "추천" 라벨 제거 결정)과
# 상충하지 않음 — 그건 UI에서 순위/추천 배지를 안 보여준다는 결정이고, 이건 기본값 자체를 데이터
# 근거로 바꾸는 별개의 결정이다(EMB_MODEL_OPTIONS 순서·라벨은 그대로 둠).
EMB_MODEL_NAME = "snumin44/sap-bert-ko-en"
MIN_CANDIDATES_FOR_FILTER = 1

# 데모 사이드바에서 검색용 임베딩 모델을 골라 비교해볼 수 있게 후보 목록을 둔다.
# 2026-07-27 변경: 라벨에서 "추천"·메달·순위·"⚠ 정확도 최하위" 같은 가치판단 문구를 뺐다 — 그
# 순위는 우리 코퍼스(gloss 654개, RAG held-out 103건)라는 좁은 테스트셋 하나로 잰 것이고, 실제
# 사용자 질문은 말투가 완전히 다를 수 있어서 "여기서 1등이 실사용에서도 1등"이라고 단정할 근거가
# 약하다(특히 의료 특화 3종은 우리 데이터가 아니라 각자 다른 의료 코퍼스로 파인튜닝됐음). 측정된
# 숫자 자체(Recall·변별력·속도)는 데모 화면(EvalSummary)에 그대로 보여주되, 어느 게 "낫다"는 판단은
# 사용자가 직접 하도록 라벨은 모델 이름만 담백하게 둔다.
# (2026-07-24 비교 실험 9종 + 2026-07-27 의료 특화 3종 추가 실험: scripts/eval/compare_gloss_top5_by_model.py,
#  compare_rag_retrieval_by_model.py 결과 — 상세 수치는 embedding_model_comparison.html·progress_log
#  ISSUE-88·90 참고. 속도(ms)는 GTX 1660 6GB(로컬 개발 PC) 측정이라 배포 서버(GTX 1080Ti) GPU가
#  다르면 달라질 수 있고, Recall·변별력은 하드웨어 무관하게 동일하다)
# 2026-08-10(ISSUE-93): DGX Spark 이전 후 GPU 메모리 예산을 다시 계산할 수 있도록 모델별 파라미터
# 수를 라벨에 직접 표기한다("약 110M"처럼 — HuggingFace Hub 기준 실측치, 안 붙은 것도 전부 확인함).
# 라벨은 이 dict의 key일 뿐 선택 로직은 model_id(value)로 이뤄져서(backend/pipeline/services.py의
# embedding_model_options()가 label은 그대로 노출, 프론트는 model_id로 선택) 라벨 문구를 바꿔도
# 동작에는 영향 없다. app/embedding.py가 model_kwargs로 float32를 강제하므로 GPU 적재 크기 ≈
# 파라미터 수 × 4bytes(fp16이 아님 — 이유는 embedding.py 주석 참고). 10종 전부 동시 캐싱
# (lru_cache maxsize=10) 시 가중치 합계는 약 7.5GB(fp32) — DGX Spark의 128GB 통합 메모리 기준으로는
# 여유롭지만, 예전 6GB GPU 카드 기준으로는 이미 넘는 크기였다.
EMB_MODEL_OPTIONS = {
    "KoSimCSE-bert-multitask (약 110M)": "BM-K/KoSimCSE-bert-multitask",
    "KoSimCSE-roberta-multitask (약 110M)": "BM-K/KoSimCSE-roberta-multitask",
    "ko-sroberta-multitask (약 110M)": "jhgan/ko-sroberta-multitask",
    "KR-SBERT-V40K (약 111M)": "snunlp/KR-SBERT-V40K-klueNLI-augSTS",
    "multilingual-e5-large-instruct (약 560M, 10종 중 최대)": "intfloat/multilingual-e5-large-instruct",
    "multilingual-e5-small (약 118M)": "intfloat/multilingual-e5-small",
    "STS-multilingual-mpnet-v2(Gameselo) (약 278M)": "Gameselo/STS-multilingual-mpnet-base-v2",
    "paraphrase-multilingual-mpnet-v2 (약 278M)": "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
    "SAP-BERT-Ko-En (기본값, 의료 특화, 약 111M)": "snumin44/sap-bert-ko-en",
    "KM-BERT (한국어 의료 특화, 약 99M)": "madatnlp/km-bert",
}
# 2026-07-27 Medical-Bi-Encoder-Q(snumin44/medical-biencoder-ko-bert-question) 제외: SAP-BERT-Ko-En과
# 성격이 겹친다는(둘 다 의료 특화 bi-encoder 계열) 사용자 판단으로 목록에서 뺐다 — 실측 자체는
# progress_log ISSUE-88·91에 그대로 남아있으니 필요하면 다시 추가하면 된다.
# 2026-07-26 F2LLM-0.6B 제외: 9종 중 속도 최하위(gloss 128.3ms/검색 186.9ms)에 정확도도 중위권이라
# 실사용 후보로서 필요가 없다고 판단해 목록에서 뺐다. 코드는 그냥 목록 항목 하나 삭제일 뿐이라(우리가
# 학습한 모델이 아니라 사전학습 체크포인트 비교 대상이었음) 별도 백업 없이 삭제 — 필요하면
# "codefuse-ai/F2LLM-0.6B"를 다시 이 표에 추가하면 그만이다.

# 2026-07-25부로 전체 3,800개 대신 서강대 테스트셋(서강대_테스트_origin_numbers_658.txt, 실사전 존재
# 654개)으로만 검색 범위를 좁힌다 — 전체 사전은 scripts/에서 필터링해서
# ETRI_KSL_Dictionary_r40_서강대658_20260725.xlsx로 새로 만들어뒀다. 원본 전체 사전 파일 자체는
# 그대로 두고(삭제 안 함), 이 상수만 바꾸면 언제든 되돌릴 수 있다.
GLOSS_EXCEL = "corpus/ETRI_KSL_Dictionary_r40_서강대658_20260725.xlsx"
GLOSS_TOP_K = 10

# 2026-08-19(진하형 피드백): v4(kiwi)는 질문 맥락과 무관하게 답변의 내용어를 전부 뽑아, "무릎이
# 아파서 왔어요"에서 무릎/아프다/오다가 다 나오는 문제가 있었다. 2026-07-25(ISSUE-62)에 "설명
# 단순성"을 이유로 deployed에서 뺐던 v2(SpanTagger, 세부분류를 프리픽스로 넣어 답변당 대표 키워드
# 1개만 예측 - 정확히 이 문제를 풀던 모델)를 시험 삼아 되살린다. 아직 검증 전이라 models/deployed/로
# 옮기지 않고 experiments/ 백업 경로를 직접 가리킨다 - 품질이 확인되면 models/README.md 관례대로
# deployed/로 옮길 것.
KEYWORD_MODEL_DIR = "./models/experiments/keyword_extractor_model_v2_deployed_until_20260725_backup"
KEYWORD_MAX_LENGTH = 96

