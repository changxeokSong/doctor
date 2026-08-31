"""문진 단계(label_stage)/세부분류(label_subcategory) 분류기 (dual-head). backbone은 하드코딩이 아니라
models/deployed/model_final/label_maps.json의 model_name으로 결정된다(2026-07-24 기준 klue/roberta-large,
ISSUE-40 참고 — 이전엔 base였음).

세부분류는 문진 단계 밑에 종속된 하위 개념이라서(예: "과거질환" 단계면 세부분류는 history 하나뿐),
두 head를 완전히 독립적으로 그냥 argmax하면 논리적으로 말이 안 되는 조합이 나올 수 있고, 특히
복합 질문("A일 때 아파요, 아니면 B일 때 아파요?")에서는 세부분류 확신도가 크게 흐트러지는 걸
실측으로 확인했다(2026-07-24, "앉아 있을 때/서 있을 때" 질문에서 세부분류 확신도 20.3%까지 하락).
그래서 예측된 1위 단계에 실제로 속하는 세부분류만 남기고 나머지는 제외한 뒤 다시 정규화한다 —
"1단계(문진 단계)를 먼저 정하고, 그 안에서 2단계(세부분류)를 고른다"는 계층 구조를 추론 시점에
강제하는 것. 재학습 없이 바로 적용 가능."""
import json
import os
import threading
from functools import lru_cache

import pandas as pd
import torch
import torch.nn as nn
from transformers import AutoTokenizer, AutoModel, AutoConfig

from app.config import MODEL_DIR, CLASSIFIER_TRAIN_EXCEL, CLASSIFIER_TRAIN_SHEET
from app.device import DEVICE

# Django runserver의 요청별 스레드가 동시에 콜드 로딩을 트리거하면 두 스레드가 동시에 GPU에 큰 모델을
# 올리려다 부딪힐 수 있다 — app/models/generator.py에서 이 레이스로 인한 meta tensor 크래시를 실제로
# 재현한 뒤(ISSUE-52) 모든 GPU 모델 로더에 동일하게 락을 걸기로 했다.
_load_lock = threading.Lock()


class MultiTaskClassifier(nn.Module):
    def __init__(self, model_name, num_stage_labels, num_sub_labels, dropout=0.1):
        super().__init__()
        self.config = AutoConfig.from_pretrained(model_name)
        self.encoder = AutoModel.from_pretrained(model_name, config=self.config)
        hidden = self.config.hidden_size
        self.dropout = nn.Dropout(dropout)
        self.stage_head = nn.Linear(hidden, num_stage_labels)
        self.sub_head = nn.Linear(hidden, num_sub_labels)

    def forward(self, input_ids=None, attention_mask=None, token_type_ids=None, **kwargs):
        outputs = self.encoder(
            input_ids=input_ids,
            attention_mask=attention_mask,
            token_type_ids=token_type_ids,
        )
        cls_repr = self.dropout(outputs.last_hidden_state[:, 0, :])
        return self.stage_head(cls_repr), self.sub_head(cls_repr)


@lru_cache(maxsize=None)
def load_model():
    with _load_lock:
        with open(os.path.join(MODEL_DIR, "label_maps.json"), encoding="utf-8") as f:
            maps = json.load(f)

        id2stage = {int(k): v for k, v in maps["id2stage"].items()}
        id2sub = {int(k): v for k, v in maps["id2sub"].items()}

        tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
        model = MultiTaskClassifier(maps["model_name"], len(id2stage), len(id2sub))
        state_dict = torch.load(os.path.join(MODEL_DIR, "pytorch_model.bin"), map_location="cpu")
        model.load_state_dict(state_dict)
        model.eval()
        model.to(DEVICE)
        if DEVICE.type == "cuda":
            # 이 GPU(6GB)는 데스크톱·Jupyter 커널과 공유돼 여유가 빠듯하다(실측: roberta-large로
            # 교체 후 GPU 메모리 부족으로 generator가 "meta tensor" 에러를 냄, 2026-07-24). 추론
            # 전용이라 정확도 손실 없이 메모리를 절반 가까이 줄이는 half precision으로 여유를 확보한다.
            model.half()

        return model, tokenizer, id2stage, id2sub, maps["max_length"]


@lru_cache(maxsize=None)
def stage_to_subcategories() -> dict:
    """분류기 학습 소스 엑셀에서 실제로 관측된 단계->세부분류 매핑을 그대로 뽑는다."""
    df = pd.read_excel(CLASSIFIER_TRAIN_EXCEL, sheet_name=CLASSIFIER_TRAIN_SHEET)
    return (
        df.groupby("label_stage")["label_subcategory"]
        .apply(lambda s: set(s))
        .to_dict()
    )


def predict(question: str, topk: int = 5):
    model, tokenizer, id2stage, id2sub, max_length = load_model()
    enc = tokenizer(
        question,
        return_tensors="pt",
        padding="max_length",
        truncation=True,
        max_length=max_length,
    ).to(DEVICE)
    with torch.no_grad():
        stage_logits, sub_logits = model(**enc)

    stage_prob = torch.softmax(stage_logits, dim=-1)[0]
    sub_prob = torch.softmax(sub_logits, dim=-1)[0]

    stage_top = torch.topk(stage_prob, min(topk, len(id2stage)))
    stage_results = [(id2stage[int(i)], float(p)) for p, i in zip(stage_top.values, stage_top.indices)]

    # 1위로 예측된 단계에 실제로 속하는 세부분류만 남기고 나머지는 0으로 눌러서 재정규화한다.
    top_stage_label = stage_results[0][0]
    valid_subs = stage_to_subcategories().get(top_stage_label)
    if valid_subs:
        mask = torch.tensor([id2sub[i] in valid_subs for i in range(len(id2sub))], device=sub_prob.device)
        if mask.any():
            sub_prob = sub_prob * mask
            sub_prob = sub_prob / sub_prob.sum()

    sub_top = torch.topk(sub_prob, min(topk, len(id2sub)))
    sub_results = [(id2sub[int(i)], float(p)) for p, i in zip(sub_top.values, sub_top.indices)]

    return stage_results, sub_results
