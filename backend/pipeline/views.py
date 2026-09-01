"""얇은 HTTP 레이어 — 요청 검증(serializers)과 서비스 호출(services)만 하고, 로직은 갖지 않는다."""
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .serializers import (
    ClassifyRequestSerializer, RetrieveRequestSerializer,
    KeywordsRequestSerializer, GlossRequestSerializer, PipelineRequestSerializer,
)


class ClassifyView(APIView):
    def post(self, request):
        req = ClassifyRequestSerializer(data=request.data)
        req.is_valid(raise_exception=True)
        return Response(services.classify(**req.validated_data))


class RetrieveView(APIView):
    def post(self, request):
        req = RetrieveRequestSerializer(data=request.data)
        req.is_valid(raise_exception=True)
        return Response(services.retrieve(**req.validated_data))


class KeywordsView(APIView):
    def post(self, request):
        req = KeywordsRequestSerializer(data=request.data)
        req.is_valid(raise_exception=True)
        return Response(services.keywords(**req.validated_data))


class GlossView(APIView):
    def post(self, request):
        req = GlossRequestSerializer(data=request.data)
        req.is_valid(raise_exception=True)
        return Response(services.gloss(**req.validated_data))


class PipelineView(APIView):
    def post(self, request):
        req = PipelineRequestSerializer(data=request.data)
        req.is_valid(raise_exception=True)
        return Response(services.run_pipeline(**req.validated_data))


class EmbeddingModelsView(APIView):
    def get(self, request):
        return Response(services.embedding_model_options())


class GlossDictionaryView(APIView):
    def get(self, request):
        return Response(services.gloss_dictionary())


class DatasetStatsView(APIView):
    def get(self, request):
        return Response({"rows": services.dataset_stats()})


class SubcategoryStatsView(APIView):
    def get(self, request):
        return Response({"rows": services.subcategory_stats()})


class ExamplesView(APIView):
    def get(self, request):
        try:
            n = int(request.query_params.get("n", 5))
        except ValueError:
            n = 5
        n = max(0, min(n, 50))
        return Response({"examples": services.example_questions(n)})


class LabelsView(APIView):
    def get(self, request):
        return Response(services.label_lists())
