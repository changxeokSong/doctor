"""프로젝트 전역 경로/하이퍼파라미터 설정. 모든 모듈이 여기서 상수를 가져다 쓴다."""

# models/deployed/ = 실제 서비스용, models/experiments/ = 미검증/폐기 실험 - 폴더로 분리해둠.
MODEL_DIR = "./models/deployed/model_final"

CORPUS_EXCEL = "corpus/통증의학과_초진_의사문의_답변_키워드_이현_0528.xlsx"
# 원본(비증강) 데이터 출처값 - 검색 코퍼스와 데이터셋 통계에서 "기존" 판정 기준.
ORIGINAL_QUESTION_SOURCES = {"추가문진", "기존분리"}
# "확장 예시"는 이름과 달리 LLM 증강이 아니라 사람이 쓴 원본 예시라 원본으로 취급한다.
ORIGINAL_ANSWER_SOURCES = {"확장 예시", "기존 환자문장"}
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

# (단계, 세부분류)별 주/보조 의미 부류 - 오프라인 1회 라벨링 결과를 고정해둔 것으로, 실행 중에는
# LLM을 호출하지 않는다. "-"는 특정 부류로 규정하기 애매한 경우(인사말/신원확인 등).
SUBCATEGORY_SEMANTIC_ROLES: dict[tuple[str, str], dict] = {
    ("과거질환", "history"): {"primary": "disease", "secondary": ["symptom", "time", "polarity"]},
    ("생활습관", "general"): {"primary": "-", "secondary": ["polarity", "severity"]},
    ("생활습관", "lifestyle"): {"primary": "lifestyle", "secondary": ["frequency", "number", "food"]},
    ("생활습관", "occupation"): {"primary": "occupation", "secondary": ["lifestyle", "body_action"]},
    ("수술 및 입원 이력", "exam_history"): {"primary": "treatment", "secondary": ["time", "polarity"]},
    ("수술 및 입원 이력", "surgery_history"): {"primary": "treatment", "secondary": ["body_part", "time", "polarity"]},
    ("수술 및 입원 이력", "surgery_site"): {"primary": "body_part", "secondary": ["position", "treatment"]},
    ("수술 및 입원 이력", "surgery_time"): {"primary": "time", "secondary": ["number"]},
    ("알레르기 및 약물반응", "adverse_reaction"): {"primary": "symptom", "secondary": ["pain_quality", "treatment", "polarity"]},
    ("알레르기 및 약물반응", "associated"): {"primary": "symptom", "secondary": ["disease", "pain_quality", "body_part"]},
    ("알레르기 및 약물반응", "medication_use"): {"primary": "treatment", "secondary": ["frequency", "polarity"]},
    ("약물복용", "medication_name"): {"primary": "treatment", "secondary": ["disease"]},
    ("약물복용", "medication_use"): {"primary": "treatment", "secondary": ["frequency", "polarity"]},
    ("진료개시", "chief_complaint"): {"primary": "body_part", "secondary": ["symptom", "disease", "pain_quality", "severity"]},
    ("진료개시", "exam_history"): {"primary": "treatment", "secondary": ["time", "polarity"]},
    ("진료개시", "greeting"): {"primary": "-", "secondary": ["polarity"]},
    ("진료개시", "identity"): {"primary": "-", "secondary": []},
    ("진료개시", "prior_treatment"): {"primary": "treatment", "secondary": ["time", "polarity"]},
    ("치료 방향 설명 및 선택 제안", "treatment_choice"): {"primary": "treatment", "secondary": ["polarity"]},
    ("통증 동반증상", "associated"): {"primary": "symptom", "secondary": ["disease", "pain_quality", "body_part"]},
    ("통증 동반증상", "neuro_weakness"): {"primary": "pain_quality", "secondary": ["body_part", "symptom", "polarity"]},
    ("통증 동반증상", "red_flag"): {"primary": "symptom", "secondary": ["disease", "body_part", "polarity"]},
    ("통증 동반증상", "sleep"): {"primary": "lifestyle", "secondary": ["time", "severity", "polarity"]},
    ("통증 동반증상", "swelling"): {"primary": "symptom", "secondary": ["body_part", "severity", "polarity"]},
    ("통증 발생시점", "onset"): {"primary": "time", "secondary": ["polarity"]},
    ("통증 발생시점", "pattern"): {"primary": "time", "secondary": ["frequency", "pain_quality"]},
    ("통증 부위", "disc_or_muscle"): {"primary": "body_part", "secondary": ["disease", "pain_quality"]},
    ("통증 부위", "location"): {"primary": "body_part", "secondary": ["position"]},
    ("통증 부위", "side"): {"primary": "position", "secondary": ["body_part"]},
    ("통증 시간대/상황별 변화", "function"): {"primary": "body_action", "secondary": ["severity", "polarity"]},
    ("통증 시간대/상황별 변화", "severity"): {"primary": "severity", "secondary": ["pain_quality", "time"]},
    ("통증 시간대/상황별 변화", "time_variation"): {"primary": "time", "secondary": ["severity", "frequency"]},
    ("통증 시간대/상황별 변화", "trigger_posture"): {"primary": "position", "secondary": ["body_action", "severity"]},
    ("통증 양상", "general"): {"primary": "pain_quality", "secondary": ["body_part", "severity"]},
    ("통증 양상", "quality"): {"primary": "pain_quality", "secondary": ["body_part", "severity"]},
    ("통증 양상", "skin_lesion"): {"primary": "symptom", "secondary": ["body_part", "pain_quality"]},
    ("통증 유발/완화 요인", "dental_trigger"): {"primary": "body_action", "secondary": ["body_part", "food"]},
    ("통증 유발/완화 요인", "pattern"): {"primary": "pain_quality", "secondary": ["frequency", "time"]},
    ("통증 유발/완화 요인", "sensory_trigger"): {"primary": "pain_quality", "secondary": ["body_action", "severity"]},
    ("통증 유발/완화 요인", "severity"): {"primary": "severity", "secondary": ["pain_quality", "treatment"]},
    ("통증 유발/완화 요인", "treatment_effect"): {"primary": "treatment", "secondary": ["severity", "polarity"]},
    ("통증 유발/완화 요인", "trigger_posture"): {"primary": "position", "secondary": ["body_action", "severity"]},
    ("통증 지속성/패턴", "duration"): {"primary": "time", "secondary": ["frequency", "number"]},
    ("통증 지속성/패턴", "frequency"): {"primary": "frequency", "secondary": ["time", "number"]},
    ("통증 지속성/패턴", "pattern"): {"primary": "pain_quality", "secondary": ["frequency", "time"]},
    ("통증 지속성/패턴", "trigger_posture"): {"primary": "position", "secondary": ["body_action", "severity"]},
    ("통증강도", "function"): {"primary": "severity", "secondary": ["body_action", "polarity"]},
    ("통증강도", "pain_score"): {"primary": "severity", "secondary": ["number"]},
    ("통증강도", "severity"): {"primary": "severity", "secondary": ["pain_quality"]},
}

# 검증 전이라 models/deployed/가 아닌 experiments/ 백업 경로를 직접 가리킴.
KEYWORD_MODEL_DIR = "./models/experiments/keyword_extractor_model_v2_deployed_until_20260725_backup"
KEYWORD_MAX_LENGTH = 96
