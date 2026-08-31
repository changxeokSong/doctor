"""문장임베딩 모델 로더. 데모에서 모델을 골라 바꿀 수 있도록 model_name을 인자로 받는다
(lru_cache는 인자값별로 따로 캐싱되므로, 모델을 바꾸면 자동으로 새로 로드되고
이전 모델 캐시도 그대로 남아있어 다시 돌아가도 재로딩이 없다).

2026-07-26(ISSUE-83) GPU로 전환: 8종 전부 GPU가 CPU보다 1.6~2.4배 빠르다는 게 백엔드 컨테이너 안에서
모델별로 재확인됐고(ISSUE-81), lr=2e-5 재학습(ISSUE-82)도 끝나 GPU 여유가 생겨서 CPU 고정을 풀었다.
2026-07-27(ISSUE-87): 사용자 요청으로 캐시 상한을 3 → 전체 모델 개수로 올려서, 한 번씩만 써보면
그 뒤로는 전부 GPU에 상주해 재로딩 없이 즉시 응답한다. 다만 VRAM 위험이 완전히 사라진 건 아니다 —
전부 동시에 GPU에 올리면(특히 e5-large-instruct 560M 포함) 6GB 한도에 가까워지거나 넘을 수 있어,
다른 GPU 작업(분류기 추론, 재학습 등)과 동시에 몰리면 OOM 가능성이 있다. 그 뒤 jungwoo 버전에서
쓰던 의료 특화 모델을 추가하면서 캐시 상한도 그때그때 맞췄다 — 처음 3종(SAP-BERT-Ko-En·KM-BERT·
Medical Bi-Encoder Q) 추가로 8→11까지 갔다가, Medical Bi-Encoder Q는 SAP-BERT-Ko-En과 성격이
겹친다고 판단해 다시 빼면서 11→10이 됐다(2026-07-27).

2026-08-10: DGX Spark(GB10) 이전으로 위 "6GB 한도"는 더 이상 정확하지 않다 — 물리 GPU가 1장뿐인
128GB 통합 메모리(시스템 RAM과 공유)로 바뀌었다. app/config.py의 EMB_MODEL_OPTIONS 주석에 모델별
파라미터 수·fp32 적재 크기를 각각 명시해뒀다 — 10종 전부 동시 캐싱해도 가중치 합계는 약 7.5GB로
128GB 대비 여유롭지만, 분류기(klue/roberta-large, fp16 ~673MB)·jungwoo 쪽 별도 모델(MiniLM
~471MB, Medical Bi-Encoder Q ~442MB)까지 다 합쳐도 10GB 안팎이라 절대량 자체는 문제가 안 된다.
다만 통합 메모리라 호스트 OS·다른 프로세스와 같은 풀을 나눠 쓰므로, "GPU 전용 VRAM"이라는 예전
전제로 캐시 상한을 다시 낮출 필요는 없다는 점만 확인해두고, 실제 여유는 `free -h`로 확인할 것
(nvidia-smi는 통합 메모리에서 메모리량을 N/A로 보여줘 참고가 안 된다).

프레임워크 무관 모듈: Streamlit 데모와 Django API가 이 모듈을 그대로 공유해서 쓴다."""
import re
from functools import lru_cache

from sentence_transformers import SentenceTransformer

from app.config import EMB_MODEL_NAME
from app.device import DEVICE


# lru_cache는 hit/miss 총계(cache_info())만 주지 "이 특정 model_name이 로드됐나"는 안 알려줘서,
# 사이드바에 "이 모델 이미 로드됨/처음 쓰면 로딩됨"을 보여주려고 별도로 집합에 기록해둔다.
_loaded_model_names: set = set()


@lru_cache(maxsize=10)
def load_embedder(model_name: str = EMB_MODEL_NAME) -> SentenceTransformer:
    # model_kwargs로 float32를 강제한다 - 안 하면 transformers가 체크포인트 config.json의
    # torch_dtype을 그대로 따라간다(예: multilingual-e5-large-instruct는 float16으로 선언돼있음).
    # 그러면 인코더 일부만 half로 로드되고 나머지는 float32로 남아 encode() 중
    # "mat1 and mat2 must have the same dtype, but got Float and Half" 에러가 난다
    # (2026-07-27 실제 배포 서버에서 재현된 에러 - ISSUE-91).
    model = SentenceTransformer(model_name, device=DEVICE.type, model_kwargs={"torch_dtype": "float32"})
    _loaded_model_names.add(model_name)
    return model


def is_embedder_loaded(model_name: str) -> bool:
    return model_name in _loaded_model_names


def cache_suffix(model_name: str) -> str:
    """모델별로 임베딩 캐시 파일을 분리하기 위한 안전한 파일명 조각."""
    return re.sub(r"[^a-zA-Z0-9]+", "_", model_name).strip("_")


def _is_e5(model_name: str) -> bool:
    return "e5-" in model_name.lower()


def prep_query(model_name: str, texts: list) -> list:
    """intfloat/multilingual-e5-* 계열은 공식 사용법상 쿼리 앞에 "query: "를 붙여야 한다
    (안 붙이면 성능이 저평가된다 - 2026-07-24 벤치마크에서 이 프리픽스 없이 측정했던 걸 뒤늦게 발견해서
    추가). 다른 모델은 그런 요구사항이 없어 원문 그대로 둔다."""
    if _is_e5(model_name):
        return [f"query: {t}" for t in texts]
    return texts


def prep_passage(model_name: str, texts: list) -> list:
    """e5 계열에서 검색 대상(코퍼스) 쪽에 붙이는 프리픽스 - query와 짝을 이루는 비대칭 인코딩."""
    if _is_e5(model_name):
        return [f"passage: {t}" for t in texts]
    return texts
