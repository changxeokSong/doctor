// backend/pipeline/services.py의 반환 구조와 1:1로 맞춘 타입.

export interface LabelProb {
  label: string
  prob: number
}

export interface RagExample {
  answer: string
  keyword: string
  source: string
}

export interface RagMatch {
  matched_question: string
  matched_question_source: string
  matched_stage: string
  matched_subcategory: string
  similarity: number
  examples: RagExample[]
}

export interface GlossHit {
  name: string
  origin_number: number
  score: number
}

export interface GlossResult {
  exact: GlossHit | null
  hits: GlossHit[]
}

export interface CandidateKeyword {
  keyword: string
  confidence: number | null
  start: number | null
  end: number | null
  no_gloss: boolean
  gloss_exact: GlossHit | null
}

export interface GlossEvidence {
  answer_index: number
  keyword: string
  score: number
  start: number | null
  end: number | null
}

export interface RecommendedGloss {
  name: string
  origin_number: number
  score: number
  is_exact: boolean
  evidence: GlossEvidence[]
}

export interface GlossApiResult {
  results: Record<string, GlossResult>
}

export interface Candidate {
  answer: string
  answer_source: string
  keywords: CandidateKeyword[]
}

export interface PipelineTiming {
  classify_ms: number
  retrieve_ms: number
  keyword_extract_ms: number
  gloss_ms: number
  total_ms: number
  cold_start: boolean
}

export interface EmbModelUsed {
  model_id: string
  label: string
}

export interface GroundTruth {
  stage: string
  subcategory: string
}

export interface PipelineResult {
  stage_results: LabelProb[]
  sub_results: LabelProb[]
  top_stage: LabelProb
  top_sub: LabelProb
  retrieval_ok: boolean
  similarity: number
  used_filter: boolean
  matched_question: string | null
  matched_question_source: string | null
  retrieval_candidates: Candidate[]
  recommended_glosses: RecommendedGloss[]
  evidence_min_score: number
  ground_truth: GroundTruth | null
  emb_model_used: EmbModelUsed
  timing: PipelineTiming
}

export interface EmbeddingModelOption {
  rank: number
  label: string
  model_id: string
  is_default: boolean
  loaded: boolean
}

export interface EmbeddingModelsResult {
  options: EmbeddingModelOption[]
  default_model_id: string
}

export interface GlossDictionaryEntry {
  origin_number: number
  name: string
  category: string
}

export interface GlossCategoryCount {
  category: string
  count: number
}

export interface GlossDictionaryResult {
  total: number
  categories: GlossCategoryCount[]
  glosses: GlossDictionaryEntry[]
}

export interface DatasetStatsRow {
  단계: string
  '질문(기존)': number
  '질문(증강)': number
  '질문 합계': number
  '답변(기존)': number
  '답변(증강)': number
  '답변 합계': number
}

export interface LabelListsResult {
  stages: string[]
  subcategories: string[]
  stage_to_subcategories: Record<string, string[]>
}
