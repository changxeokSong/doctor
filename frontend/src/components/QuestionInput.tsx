interface Props {
  value: string
  onChange: (v: string) => void
  onSubmit: (q?: string) => void
  loading: boolean
  canSubmit: boolean
}

export function QuestionInput({ value, onChange, onSubmit, loading, canSubmit }: Props) {
  return (
    <div className="card">
      <textarea
        aria-label="의사 질문 입력"
        className="ask-input"
        placeholder="예: 어디가 제일 아프세요?"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) onSubmit()
        }}
      />
      <div className="ask-row">
        <button type="button" className="btn" disabled={loading || !canSubmit} onClick={() => onSubmit()}>
          키워드 추천
        </button>
        <span className="hint">Ctrl+Enter</span>
        {loading && (
          <span role="status" className="status-line visible">
            <span className="spinner" />
            추천 중...
          </span>
        )}
      </div>
    </div>
  )
}
