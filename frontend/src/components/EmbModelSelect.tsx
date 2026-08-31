import type { EmbeddingModelOption } from '../api/types'

interface Props {
  embOptions: EmbeddingModelOption[]
  embModel: string
  onEmbModelChange: (modelId: string) => void
  className?: string
  id?: string
}

export function EmbModelSelect({ embOptions, embModel, onEmbModelChange, className, id }: Props) {
  return (
    <select
      id={id}
      className={
        className ??
        'bg-white border border-[var(--mh-border)] rounded-lg text-[var(--mh-text)] px-2.5 py-2 text-[13px] outline-none focus:border-[var(--mh-accent)]'
      }
      value={embModel}
      onChange={(e) => onEmbModelChange(e.target.value)}
    >
      {embOptions.map((opt) => (
        <option key={opt.model_id} value={opt.model_id}>
          {opt.loaded ? '✅' : '⏳'} {opt.label}
        </option>
      ))}
    </select>
  )
}
