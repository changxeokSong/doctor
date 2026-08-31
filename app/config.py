"""프로젝트 전역 경로/하이퍼파라미터 설정. 모든 모듈이 여기서 상수를 가져다 쓴다."""

# models/deployed/ = 실제 서비스용, models/experiments/ = 미검증/폐기 실험 - 폴더로 분리해둠.
MODEL_DIR = "./models/deployed/model_final"

CORPUS_EXCEL = "corpus/통증의학과_초진_의사문의_답변_키워드_이현_0528.xlsx"
CLASSIFIER_TRAIN_EXCEL = "corpus/통증의학과_모델입력_균형보강_학습준비본_0528.xlsx"
CLASSIFIER_TRAIN_SHEET = "01_학습데이터_균형보강"
EMB_MODEL_NAME = "snumin44/sap-bert-ko-en"
MIN_CANDIDATES_FOR_FILTER = 1

# key(라벨)는 화면 표시용, value(model_id)만 로직에 쓰인다 - 라벨 문구는 자유롭게 바꿔도 무방.
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

GLOSS_EXCEL = "corpus/ETRI_KSL_Dictionary_r40_서강대658_20260725.xlsx"
GLOSS_TOP_K = 10

# 검증 전이라 models/deployed/가 아닌 experiments/ 백업 경로를 직접 가리킴.
KEYWORD_MODEL_DIR = "./models/experiments/keyword_extractor_model_v2_deployed_until_20260725_backup"
KEYWORD_MAX_LENGTH = 96
