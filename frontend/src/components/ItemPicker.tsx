import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import type { Item } from '../types/api'
import { useDebounce } from '../hooks/useDebounce'

interface Props {
  value: string
  onChange: (itemId: string) => void
  placeholder?: string
  craftable?: boolean
}

export function ItemPicker({ value, onChange, placeholder, craftable = false }: Props) {
  const [query, setQuery] = useState('')
  const [items, setItems] = useState<Item[]>([])
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [open, setOpen] = useState(false)
  const debounced = useDebounce(query, 300)

  useEffect(() => {
    if (!value) setQuery('')
  }, [value])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setLoadError(null)

    api.items(debounced.trim() || undefined, craftable)
      .then(r => {
        if (!cancelled) setItems(r.slice(0, 50))
      })
      .catch((e: unknown) => {
        if (cancelled) return
        setItems([])
        setLoadError(e instanceof Error ? e.message : String(e))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => { cancelled = true }
  }, [debounced, craftable])

  const filtered = useMemo(() => {
    if (!query.trim()) return items
    const q = query.trim().toLocaleLowerCase()
    return items.filter(i =>
      i.name.toLocaleLowerCase().includes(q) ||
      i.item_id.toLocaleLowerCase().includes(q)
    )
  }, [items, query])

  function selectItem(item: Item) {
    onChange(item.item_id)
    setQuery(item.name)
    setOpen(false)
    setLoadError(null)
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter') {
      e.preventDefault()
      if (filtered.length > 0 && !loading) selectItem(filtered[0])
    } else if (e.key === 'Escape') {
      setOpen(false)
    } else if (e.key === 'ArrowDown') {
      setOpen(true)
    }
  }

  return (
    <div className="relative">
      <input
        className="w-full rounded-md bg-slate-900 border border-slate-700 px-3 py-2 text-sm focus:outline-none focus:border-emerald-500"
        placeholder={placeholder ?? 'Введите название предмета (например: Хорог)'}
        value={query}
        autoComplete="off"
        aria-autocomplete="list"
        aria-expanded={open}
        onChange={e => { setQuery(e.target.value); setOpen(true); setLoadError(null) }}
        onKeyDown={handleKeyDown}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
      />
      {open && (
        <div className="absolute z-20 mt-1 w-full max-h-80 overflow-auto rounded-md border border-slate-700 bg-slate-900 shadow-xl">
          {loading && <div className="px-3 py-2 text-xs text-slate-500">Поиск предметов…</div>}
          {!loading && loadError && (
            <div className="px-3 py-2 text-xs text-rose-300 whitespace-pre-wrap">
              Не удалось загрузить список предметов: {loadError}
            </div>
          )}
          {!loading && !loadError && filtered.length === 0 && (
            <div className="px-3 py-2 text-xs text-slate-500">Ничего не найдено</div>
          )}
          {!loadError && filtered.map(i => (
            <button
              key={i.item_id}
              type="button"
              className="w-full text-left px-3 py-1.5 text-sm hover:bg-slate-800 flex justify-between gap-2"
              onMouseDown={e => e.preventDefault()}
              onClick={() => selectItem(i)}
            >
              <span className="truncate font-medium text-slate-200">{i.name}</span>
            </button>
          ))}
          {!loading && !loadError && filtered.length > 0 && (
            <div className="border-t border-slate-800 px-3 py-1 text-[11px] text-slate-500">
              Enter — выбрать первый результат
            </div>
          )}
        </div>
      )}
    </div>
  )
}
