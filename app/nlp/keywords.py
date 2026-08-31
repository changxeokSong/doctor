"""학습 기반 SpanTagger - 답변 하나당 "대표 키워드" 1개만 예측한다. 세부분류를 프리픽스로 같이
넣어(f"{subcategory} : {answer}") 질문 맥락을 반영해서, "아프다"/"오다" 같은 일반 서술어를 걸러내고
"무릎"처럼 실제 정보량이 있는 span만 고른다."""
import os
import threading
from functools import lru_cache

import torch
import torch.nn as nn
from transformers import AutoTokenizer, AutoModel, AutoConfig

from app.config import KEYWORD_MODEL_DIR, KEYWORD_MAX_LENGTH
from app.device import DEVICE
from app.nlp.morphology import strip_trailing_particle, strip_filler_adverbs

# 동시 요청이 콜드 로딩을 동시에 트리거하는 레이스를 막는다.
_load_lock = threading.Lock()


class SpanTagger(nn.Module):
    def __init__(self, model_name, num_labels=3, dropout=0.1):
        super().__init__()
        self.config = AutoConfig.from_pretrained(model_name)
        self.encoder = AutoModel.from_pretrained(model_name, config=self.config)
        self.dropout = nn.Dropout(dropout)
        self.classifier = nn.Linear(self.config.hidden_size, num_labels)

    def forward(self, input_ids=None, attention_mask=None, token_type_ids=None, **kwargs):
        out = self.encoder(input_ids=input_ids, attention_mask=attention_mask, token_type_ids=token_type_ids)
        return self.classifier(self.dropout(out.last_hidden_state))


def _collect_spans(offsets, preds):
    """BIO 예측(0=O, 1=B, 2=I)에서 문자 offset 기준 (start, end) span 목록을 뽑는다."""
    spans, cur_start, prev_end = [], None, None
    for (start, end), lab in zip(offsets, preds):
        if start == end:  # 특수토큰/패딩
            continue
        if lab == 1:  # B
            if cur_start is not None:
                spans.append((cur_start, prev_end))
            cur_start, prev_end = start, end
        elif lab == 2 and cur_start is not None:  # I
            prev_end = end
        else:
            if cur_start is not None:
                spans.append((cur_start, prev_end))
            cur_start = None
    if cur_start is not None:
        spans.append((cur_start, prev_end))
    return spans


@lru_cache(maxsize=None)
def load_keyword_model():
    with _load_lock:
        tok = AutoTokenizer.from_pretrained(KEYWORD_MODEL_DIR)
        kw_model = SpanTagger("klue/roberta-base")
        state = torch.load(os.path.join(KEYWORD_MODEL_DIR, "pytorch_model.bin"), map_location="cpu")
        kw_model.load_state_dict(state)
        kw_model.eval()
        kw_model.to(DEVICE)
        if DEVICE.type == "cuda":
            kw_model.half()
        return kw_model, tok


def extract_keyword_learned(subcategory: str, answer: str):
    """대표 키워드 1개(v2)와 그 신뢰도(선택된 span 토큰들의 평균 softmax 확률)를 함께 반환한다.
    spans가 여러 개 예측되면(보통 없음) 가장 긴 것을 채택한다."""
    keyword_model, keyword_tokenizer = load_keyword_model()
    prefix = f"{subcategory} : "
    full_text = prefix + answer
    enc = keyword_tokenizer(full_text, truncation=True, max_length=KEYWORD_MAX_LENGTH,
                             padding="max_length", return_offsets_mapping=True, return_tensors="pt")
    offsets = enc.pop("offset_mapping")[0].tolist()
    enc = enc.to(DEVICE)
    with torch.no_grad():
        logits = keyword_model(**enc)
    probs = torch.softmax(logits[0], dim=-1)
    preds = torch.argmax(logits[0], dim=-1).tolist()
    spans = _collect_spans(offsets, preds)
    if not spans:
        return "", 0.0
    s, e = max(spans, key=lambda x: x[1] - x[0])
    tok_conf = [
        float(probs[i, preds[i]])
        for i, (o_s, o_e) in enumerate(offsets)
        if o_s != o_e and o_s >= s and o_e <= e
    ]
    confidence = round(sum(tok_conf) / len(tok_conf), 4) if tok_conf else 0.0
    cleaned = strip_trailing_particle(strip_filler_adverbs(full_text[s:e]))
    return cleaned, confidence
