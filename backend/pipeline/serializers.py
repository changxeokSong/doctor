"""요청 바디 검증만 담당 — 실제 로직은 app/ 패키지에 있고 여기서는 재구현하지 않는다."""
from rest_framework import serializers

from app.config import GLOSS_TOP_K


class ClassifyRequestSerializer(serializers.Serializer):
    question = serializers.CharField(allow_blank=False)
    topk = serializers.IntegerField(required=False, default=5, min_value=1, max_value=20)


class RetrieveRequestSerializer(serializers.Serializer):
    question = serializers.CharField(allow_blank=False)
    subcategories = serializers.ListField(child=serializers.CharField(), allow_empty=False)
    top_k = serializers.IntegerField(required=False, default=1, min_value=1, max_value=20)
    max_examples = serializers.IntegerField(required=False, default=20, min_value=1, max_value=100)
    emb_model = serializers.CharField(required=False, allow_null=True, default=None)


class KeywordsRequestSerializer(serializers.Serializer):
    """subcategory는 v2(SpanTagger)가 대표 키워드 1개를 뽑을 때 맥락으로 실제로 쓴다
    (services.keywords 참고)."""
    subcategory = serializers.CharField(allow_blank=False)
    answer = serializers.CharField(allow_blank=False)


class GlossRequestSerializer(serializers.Serializer):
    """max_value=1000 - 2026-08-19부터 프론트가 답변 카드를 펼칠 때 사전 전체(~654개) 유사도 랭킹을
    이 엔드포인트로 지연 로딩한다(파이프라인 응답에 미리 다 채워 넣었다가 응답이 최대 ~900KB까지
    커져 서버 디스크를 채운 장애 이후 변경, backend/pipeline/services.py의 _build_candidates 참고)."""
    keywords = serializers.ListField(child=serializers.CharField(), allow_empty=False)
    top_k = serializers.IntegerField(required=False, default=GLOSS_TOP_K, min_value=1, max_value=1000)
    emb_model = serializers.CharField(required=False, allow_null=True, default=None)


class PipelineRequestSerializer(serializers.Serializer):
    """gloss_top_k 없음 - 표제어 매핑은 정확일치 여부만 넣고, 유사도 전체 랭킹은 프론트가 카드를 펼칠
    때 /api/gloss/로 따로 요청한다(services.run_pipeline/_build_candidates 참고)."""
    question = serializers.CharField(allow_blank=False)
    emb_model = serializers.CharField(required=False, allow_null=True, default=None)
    similarity_threshold = serializers.FloatField(required=False, default=0.65, min_value=0.0, max_value=1.0)
