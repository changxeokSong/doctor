from django.urls import path

from . import views

urlpatterns = [
    path("classify/", views.ClassifyView.as_view()),
    path("retrieve/", views.RetrieveView.as_view()),
    path("keywords/", views.KeywordsView.as_view()),
    path("gloss/", views.GlossView.as_view()),
    path("pipeline/", views.PipelineView.as_view()),
    path("embedding-models/", views.EmbeddingModelsView.as_view()),
    path("gloss-dictionary/", views.GlossDictionaryView.as_view()),
    path("dataset-stats/", views.DatasetStatsView.as_view()),
    path("examples/", views.ExamplesView.as_view()),
    path("labels/", views.LabelsView.as_view()),
]
