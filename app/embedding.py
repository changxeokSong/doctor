"""문장임베딩 모델 로더. model_name별로 lru_cache가 따로 캐싱하므로 모델을 바꿔도 이전 모델
캐시는 유지된다. Streamlit 데모와 Django API가 이 모듈을 공유한다."""
import re
from functools import lru_cache

from sentence_transformers import SentenceTransformer

from app.config import EMB_MODEL_NAME
from app.device import DEVICE


# "이 모델 이미 로드됨" UI 표시용 - lru_cache의 cache_info()는 hit/miss 총계만 주고 어떤
# model_name이 로드됐는지는 안 알려준다.
_loaded_model_names: set = set()


@lru_cache(maxsize=10)
def load_embedder(model_name: str = EMB_MODEL_NAME) -> SentenceTransformer:
    # float32 강제 - 안 하면 체크포인트의 torch_dtype(예: 일부 모델 float16)을 따라가 인코더 일부만
    # half로 로드되면서 encode() 중 dtype mismatch 에러가 난다.
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
    """intfloat/multilingual-e5-* 계열은 쿼리 앞에 "query: "를 붙여야 한다(공식 사용법 - 안 붙이면 성능 저하)."""
    if _is_e5(model_name):
        return [f"query: {t}" for t in texts]
    return texts


def prep_passage(model_name: str, texts: list) -> list:
    """e5 계열의 검색 대상(코퍼스) 쪽 프리픽스 - query와 짝을 이루는 비대칭 인코딩."""
    if _is_e5(model_name):
        return [f"passage: {t}" for t in texts]
    return texts
