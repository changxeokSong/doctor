"""추론용 디바이스. 분류기/생성기/키워드 모델처럼 고정된 단일 모델은 GPU가 비어 있으면 자동으로 쓴다
(app/embedding.py의 문장임베딩 모델만 의도적으로 CPU 고정 — 그 파일 docstring 참고)."""
import torch

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
