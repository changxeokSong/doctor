"""요청 바디 검증만 담당 — 실제 로직은 app/ 패키지에 있고 여기서는 재구현하지 않는다."""
from rest_framework import serializers

from app.config import GLOSS_TOP_K, EMB_MODEL_OPTIONS


def _emb_model_field():
    """임의 문자열이 그대로 SentenceTransformer(model_id)로 넘어가 잘못된 HF repo를 내려받으려
    들지 않도록, 실제 후보 목록(EMB_MODEL_OPTIONS)에 있는 값만 허용한다."""
    return serializers.ChoiceField(
        choices=list(EMB_MODEL_OPTIONS.values()), required=False, allow_null=True, default=None,
    )


class ClassifyRequestSerializer(serializers.Serializer):
    question = serializers.CharField(allow_blank=False)
    topk = serializers.IntegerField(required=False, default=5, min_value=1, max_value=20)


class RetrieveRequestSerializer(serializers.Serializer):
    question = serializers.CharField(allow_blank=False)
    subcategories = serializers.ListField(child=serializers.CharField(), allow_empty=False)
    top_k = serializers.IntegerField(required=False, default=1, min_value=1, max_value=20)
    max_examples = serializers.IntegerField(required=False, default=20, min_value=1, max_value=100)
    emb_model = _emb_model_field()


class KeywordsRequestSerializer(serializers.Serializer):
    """subcategory는 v2(SpanTagger)가 대표 키워드 1개를 뽑을 때 맥락으로 실제로 쓴다
    (services.keywords 참고)."""
    subcategory = serializers.CharField(allow_blank=False)
    answer = serializers.CharField(allow_blank=False)


class GlossRequestSerializer(serializers.Serializer):
    """max_value=1000 - 답변 카드를 펼칠 때 사전 전체 유사도 랭킹을 지연 로딩하는 용도."""
    keywords = serializers.ListField(child=serializers.CharField(), allow_empty=False)
    top_k = serializers.IntegerField(required=False, default=GLOSS_TOP_K, min_value=1, max_value=1000)
    emb_model = _emb_model_field()


class PipelineRequestSerializer(serializers.Serializer):
    """gloss_top_k 없음 - 유사도 전체 랭킹은 프론트가 카드 펼칠 때 /api/gloss/로 따로 요청한다."""
    question = serializers.CharField(allow_blank=False)
    emb_model = _emb_model_field()
    similarity_threshold = serializers.FloatField(required=False, default=0.65, min_value=0.0, max_value=1.0)
