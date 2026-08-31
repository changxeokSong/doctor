"""문진 단계(label_stage)/세부분류(label_subcategory) 분류기 (dual-head).
backbone은 models/deployed/model_final/label_maps.json의 model_name으로 결정된다.

세부분류는 문진 단계에 종속된 하위 개념이라(예: "과거질환" 단계면 세부분류는 history 하나뿐)
두 head를 독립적으로 argmax하면 논리적으로 안 맞는 조합이 나올 수 있어, 예측된 1위 단계에
실제로 속하는 세부분류만 남기고 재정규화한다."""
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

# 동시 요청이 콜드 로딩을 동시에 트리거하면 GPU 모델 로드가 레이스로 크래시할 수 있어 락을 건다.
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
            # 추론 전용이라 정확도 손실 없이 GPU 메모리를 절반 가까이 줄일 수 있다.
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
