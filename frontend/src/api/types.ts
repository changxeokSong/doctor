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
  candidate_count: number
  corpus_count: number
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
  gloss_top: GlossHit | null
}

export type GlossSource = 'answer_evidence' | 'intent_expansion'

// 세부분류별 우선순위 규칙으로 점수 순서를 거슬러 앞당겨진 행 - 'gloss'가 'category'보다 정렬 키에서 앞선다.
export type PriorityKind = 'gloss' | 'category' | null

export interface RecommendedGloss {
  keyword: string
  glossId: number
  score: number
  source: GlossSource
  prioritized: boolean
  priorityKind: PriorityKind
}

export interface GlossTableRow {
  keyword: string
  glossId: number
  score: number
  category: string
  source: GlossSource
  prioritized: boolean
  priorityKind: PriorityKind
  evidenceSentence: string
  evidenceStart: number | null
  evidenceEnd: number | null
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

export interface PipelineStats {
  final_count: number
  evidence_count: number
  expansion_count: number
  dropped_count: number
  answers_total: number
  answers_resolved: number
  total_ms: number
}

export interface ExcludedGloss {
  keyword: string
  glossId: number
  score: number
  category: string
}

export interface AnalysisClassification {
  question: string
  predictedStage: string
  predictedStageProb: number
  predictedSub: string
  predictedSubProb: number
  usedStage: string
  usedSub: string
  subMargin: number
  searchedSubs: string[]
  path: string
  reason: string
  latencyMs: number
}

export interface AnalysisRetrieval {
  matchedQuestion: string | null
  matchedQuestionSource: string | null
  similarity: number
  similarityThreshold: number
  retrievalOk: boolean
  usedFilter: boolean
  candidateCount: number
  corpusCount: number
  latencyMs: number
}

export interface AnalysisAnswerPool {
  total: number
  keywordFound: number
  noGlossCount: number
  resolved: number
  sources: { source: string; count: number }[]
  latencyMs: number
}

export interface AnalysisCutoff {
  minScore: number
  topPercentile: number
  excludedCount: number
  // 사전 전체가 아니라 상위 일부 표본만 온다 - 개수는 excludedCount를 써야 한다.
  excludedSample: ExcludedGloss[]
  latencyMs: number
}

export interface AnalysisLatency {
  classifyMs: number
  retrieveMs: number
  keywordExtractMs: number
  glossScoringMs: number
  totalMs: number
}

export interface PipelineAnalysis {
  classification: AnalysisClassification
  retrieval: AnalysisRetrieval
  answerPool: AnalysisAnswerPool
  cutoff: AnalysisCutoff
  latency: AnalysisLatency
}

export interface KeywordsEnvelope {
  question: string
  stage: string
  subCategory: string
  count: number
  keywords: RecommendedGloss[]
  output: [string, number][]
  tuples: [number, string, number][]
  pairs: [string, number][]
  idPairs: [number, number][]
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
  table_rows: GlossTableRow[]
  evidence_min_score: number
  stats: PipelineStats
  analysis: PipelineAnalysis
  keywords_envelope: KeywordsEnvelope
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

export interface RecentOutputGloss {
  glossId: number
  keyword: string
  score: number
  source: GlossSource
  prioritized: boolean
  priorityKind: PriorityKind
}

export interface RecentOutputEntry {
  question: string
  stage: string
  subCategory: string
  timestamp: number
  glosses: RecentOutputGloss[]
}

export interface SubcategoryStatRow {
  단계: string
  세부분류: string
  질문: number
  답변: number
  // 세부분류별 정적 라벨 - 질문마다 실행 중 계산되는 값이 아니다. 없으면 '-' / 빈 배열.
  primary_role: string
  secondary_roles: string[]
}

export interface LabelListsResult {
  stages: string[]
  subcategories: string[]
  stage_to_subcategories: Record<string, string[]>
}
