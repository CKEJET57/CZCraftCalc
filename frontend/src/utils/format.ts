export function fmtPrice(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—'
  return `${Math.round(v).toLocaleString('ru-RU')} ₽`
}

export function fmtPct(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—'
  return `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`
}

export function sourceTag(source: string): { label: string; cls: string } {
  switch (source) {
    case 'craft': return { label: 'крафт', cls: 'bg-violet-500/15 text-violet-300' }
    case 'market':
    case 'history':
    case 'lots': return { label: 'рынок', cls: 'bg-sky-500/15 text-sky-300' }
    case 'excluded': return { label: 'склад', cls: 'bg-amber-500/15 text-amber-300' }
    case 'barter': return { label: '', cls: '' }
    default: return { label: 'нет', cls: 'bg-rose-500/15 text-rose-300' }
  }
}