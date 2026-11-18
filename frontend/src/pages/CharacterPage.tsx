import { useState, useEffect, useMemo } from 'react'
import { api } from '../api/client'
import { LoadingSpinner } from '../components/LoadingSpinner'
import { ErrorBox } from '../components/ErrorBox'

interface StatMeta {
  id: string
  category: string
  type: string
  name: {
    lines?: { ru?: string; en?: string }
    text?: string
  }
}

interface CharData {
  username: string
  status: string
  alliance: string
  lastLogin: string
  stats: { id: string; type: string; value: any }[]
}

const CATEGORY_NAMES: Record<string, string> = {
  SURVIVAL: 'Выживание',
  COMBAT: 'Бой',
  EXPLORATION: 'Исследование',
  ECONOMY: 'Экономика',
  SESSION_MODES: 'Режимы',
  HIDEOUT: 'Убежище',
  NONE: 'Прочее',
}

const CATEGORY_ORDER = ['SURVIVAL', 'COMBAT', 'EXPLORATION', 'ECONOMY', 'SESSION_MODES', 'HIDEOUT', 'NONE']

export function CharacterPage() {
  const [name, setName] = useState('')
  const [region, setRegion] = useState('RU')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<CharData | null>(null)
  const [statsMeta, setStatsMeta] = useState<Record<string, StatMeta>>({})

  useEffect(() => {
    api.statsMetadata()
      .then((list) => {
        const dict = (list as StatMeta[]).reduce((acc, item) => {
          acc[item.id] = item
          return acc
        }, {} as Record<string, StatMeta>)
        setStatsMeta(dict)
      })
      .catch(err => console.error('Ошибка загрузки stats.json:', err))
  }, [])

  async function run() {
    if (!name.trim() || loading) return
    setLoading(true)
    setError(null)
    setData(null)
    try {
      setData(await api.character({ name: name.trim(), region }) as unknown as CharData)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  const formatValue = (value: any, type: string) => {
    if (value === undefined || value === null) return '—'

    if (type === 'DATE') {
      return new Date(value).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' })
    }

    if (type === 'DURATION') {
      const secs = Math.floor(value / 1000)
      const days = Math.floor(secs / 86400)
      const hours = Math.floor((secs % 86400) / 3600)
      const mins = Math.floor((secs % 3600) / 60)
      const parts = []
      if (days > 0) parts.push(`${days}д`)
      if (hours > 0) parts.push(`${hours}ч`)
      if (mins > 0 || parts.length === 0) parts.push(`${mins}м`)
      return parts.join(' ')
    }

    if (type === 'DECIMAL') {
      return Number(value).toLocaleString('ru-RU', { maximumFractionDigits: 1 })
    }

    return Number(value).toLocaleString('ru-RU')
  }

  const groupedStats = useMemo(() => {
    if (!data?.stats || !statsMeta) return []

    const groups: Record<string, { name: string, value: string }[]> = {}

    data.stats.forEach(stat => {
      const meta = statsMeta[stat.id]
      if (!meta) return

      const statName = meta.name?.lines?.ru || meta.name?.text || stat.id
      if (!statName) return

      const cat = meta.category || 'NONE'
      if (!groups[cat]) groups[cat] = []

      groups[cat].push({
        name: statName,
        value: formatValue(stat.value, stat.type)
      })
    })

    return CATEGORY_ORDER
      .filter(cat => groups[cat] && groups[cat].length > 0)
      .map(cat => ({
        id: cat,
        title: CATEGORY_NAMES[cat] || cat,
        items: groups[cat].sort((a, b) => a.name.localeCompare(b.name))
      }))
  }, [data, statsMeta])

  return (
    <div className="space-y-6 pb-20">
      <h1 className="text-2xl font-bold">🧑 Профиль персонажа</h1>

      <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4 flex gap-3">
        <input value={name} onChange={e => setName(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && run()}
          placeholder="Ник персонажа"
          className="flex-1 rounded-md bg-slate-900 border border-slate-700 px-3 py-2 text-sm" />
        <input value={region} onChange={e => setRegion(e.target.value.toUpperCase())}
          className="w-24 rounded-md bg-slate-900 border border-slate-700 px-3 py-2 text-sm" />
        <button onClick={run} disabled={loading || !name.trim()}
          className="rounded-md bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 px-4 py-2 text-sm font-semibold">
          {loading ? '…' : 'Найти'}
        </button>
      </div>

      {loading && <LoadingSpinner />}
      {error && <ErrorBox error={error} />}

      {data && (
        <div className="space-y-6 animate-in fade-in duration-300 w-full">
          <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div>
              <h2 className="text-2xl font-bold text-emerald-400">{data.username}</h2>
              <div className="text-sm text-slate-400 flex flex-wrap gap-3 mt-1">
                <span>Фракция: <span className="text-slate-200 uppercase">{data.alliance}</span></span>
                <span>Последний вход: <span className="text-slate-200">{new Date(data.lastLogin).toLocaleString('ru-RU')}</span></span>
              </div>
            </div>
            {data.status && (
              <div className="text-sm text-slate-300 whitespace-pre-wrap italic bg-slate-900/60 p-2 rounded border border-slate-800/50 max-w-sm">
                {data.status.replace(/§./g, '')}
              </div>
            )}
          </div>

          <div className="flex flex-col gap-4">
            {groupedStats.map(group => (
              <details key={group.id}
                className="group rounded-xl border border-slate-800 bg-slate-900/40 overflow-hidden"
                open>
                <summary className="flex items-center justify-between p-4 cursor-pointer select-none hover:bg-slate-800/30 transition">
                  <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider">
                    {group.title}
                  </h3>
                  <span className="text-slate-500 transition-transform duration-200 group-open:rotate-180">▼</span>
                </summary>

                <div className="p-4 pt-0 flex flex-col gap-1.5 border-t border-slate-800/50">
                  {group.items.map((item, i) => (
                    <div key={i} className="flex justify-between items-start text-sm gap-4 py-1 hover:bg-slate-800/20 px-2 -mx-2 rounded">
                      <span className="text-slate-400">{item.name}</span>
                      <span className="font-mono text-slate-200 text-right whitespace-nowrap">{item.value}</span>
                    </div>
                  ))}
                </div>
              </details>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
