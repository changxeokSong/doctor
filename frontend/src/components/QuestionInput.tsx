import type { EmbeddingModelOption } from '../api/types'
import { EmbModelSelect } from './EmbModelSelect'

interface Props {
  value: string
  onChange: (v: string) => void
  // q 있으면 그 값으로 바로 실행 (예시 버튼 클릭용)
  onSubmit: (q?: string) => void
  examples: string[]
  loading: boolean
  embOptions: EmbeddingModelOption[]
  embModel: string
  onEmbModelChange: (modelId: string) => void
}

export function QuestionInput({ value, onChange, onSubmit, examples, loading, embOptions, embModel, onEmbModelChange }: Props) {
  return (
    <div className="card bg-[var(--mh-surface)] border border-[var(--mh-border)] rounded-xl p-[18px] shadow-[var(--mh-card-shadow)]">
      <textarea
        aria-label="의사 질문 입력"
        className="w-full border-[1.5px] border-[var(--mh-border)] rounded-[10px] px-[15px] py-[13px] text-[15px] outline-none resize-none h-[76px] focus:border-[var(--mh-accent)]"
        placeholder="예: 어디가 제일 아프세요?"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) onSubmit()
        }}
      />
      <div className="flex items-center gap-2 mt-3">
        <label htmlFor="emb-model-select" className="text-xs text-[var(--mh-muted)] font-bold shrink-0">임베딩 모델</label>
        <EmbModelSelect
          id="emb-model-select"
          embOptions={embOptions} embModel={embModel} onEmbModelChange={onEmbModelChange}
          className="min-w-0 flex-1 bg-white border border-[var(--mh-border)] rounded-lg text-[var(--mh-text)] px-2.5 py-1.5 text-[13px] outline-none focus:border-[var(--mh-accent)]"
        />
      </div>
      <div className="flex items-center gap-3 mt-3">
        <button
          type="button"
          disabled={loading || !embModel}
          className="rounded-[9px] px-6 py-[11px] text-sm font-bold text-white bg-[var(--mh-accent)] hover:bg-[var(--mh-accent-hover)] disabled:opacity-45 disabled:pointer-events-none"
          onClick={() => onSubmit()}
        >
          키워드 추천
        </button>
        <span className="text-xs text-[var(--mh-muted-2)]">Ctrl+Enter</span>
        {loading && (
          <span role="status" className="text-[13px] text-[var(--mh-accent)] font-medium">
            <span className="inline-block w-3.5 h-3.5 border-2 border-[var(--mh-accent)]/30 border-t-[var(--mh-accent)] rounded-full animate-spin align-middle mr-1.5" />
            추천 중...
          </span>
        )}
      </div>
      <div className="flex flex-wrap gap-2 mt-3 pt-3 border-t border-[var(--mh-border)]">
        {examples.map((ex) => (
          <button
            key={ex}
            disabled={loading}
            className="text-[13px] font-semibold bg-white border border-[var(--mh-border)] text-[#3c3c43] rounded-[9px] px-3.5 py-2 hover:bg-[var(--mh-surface-2)] disabled:opacity-45 disabled:pointer-events-none"
            onClick={() => { onChange(ex); onSubmit(ex) }}
          >
            {ex}
          </button>
        ))}
      </div>
    </div>
  )
}
