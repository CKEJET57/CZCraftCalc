import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { TopItemsResp } from '../types/api'
import { getRankColor } from '../utils/rankColors'

function money(value: number): string {
  return Math.round(value).toLocaleString('ru-RU') + ' ₽'
}

function formatHour(value: string | null): string {
  if (!value) return 'Нет опубликованных данных'
  const date = new Date(value)
  const formatted = date.toLocaleString('ru-RU', {
    timeZone: 'Europe/Moscow',
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
  return 'Данные за ' + formatted + ' МСК'
}

export function TopItemsPage() {
  const [data, setData] = useState<TopItemsResp | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [syncing, setSyncing] = useState(false)
  const [syncMessage, setSyncMessage] = useState('')

  async function syncMarketData() {
    setSyncing(true)
    setSyncMessage('')
    setError('')
    try {
      const result = await api.syncMarketData()
      const latest = await api.topItems(100)
      setData(latest)
      setSyncMessage(`Синхронизировано файлов: ${result.files}. Час: ${result.hour ?? 'нет данных'}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSyncing(false)
    }
  }

  useEffect(() => {
    let active = true
    api.topItems(100)
      .then(result => { if (active) setData(result) })
      .catch(err => { if (active) setError(err instanceof Error ? err.message : String(err)) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Самые продаваемые предметы</h1>
          <p className="mt-1 text-sm text-slate-400">
            {data ? formatHour(data.hour) : 'Почасовой рейтинг по количеству сделок'}
          </p>
        </div>
        {api.desktop && (
          <button
            type="button"
            onClick={syncMarketData}
            disabled={syncing}
            className="rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-sm font-medium text-slate-200 hover:bg-slate-700 disabled:opacity-50"
          >
            {syncing ? 'Синхронизация…' : 'Обновить рыночные данные'}
          </button>
        )}
      </div>
      {syncMessage && <p className="text-sm text-emerald-300">{syncMessage}</p>}

      {loading && (
        <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-6 text-sm text-slate-400">
          Загружаем рейтинг…
        </div>
      )}
      {!loading && error && (
        <div className="rounded-xl border border-rose-900/60 bg-rose-950/20 p-4 text-sm text-rose-300">
          Не удалось загрузить рейтинг: {error}
        </div>
      )}
      {!loading && !error && data && data.items.length === 0 && (
        <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-6 text-sm text-slate-400">
          За последний опубликованный час данных о продажах пока нет.
        </div>
      )}
      {!loading && !error && data && data.items.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-900/40">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-sm">
              <thead className="bg-slate-900 text-xs uppercase tracking-wide text-slate-400">
                <tr>
                  <th className="px-4 py-3 text-right">#</th>
                  <th className="px-4 py-3 text-left">Предмет</th>
                  <th className="px-4 py-3 text-right">Сделок за час</th>
                  <th className="px-4 py-3 text-right">Оборот</th>
                  <th className="px-4 py-3 text-right">Медианная цена / шт.</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((item, index) => (
                  <tr key={item.item_id} className="border-t border-slate-800 hover:bg-slate-800/40">
                    <td className="px-4 py-3 text-right font-mono text-slate-500">{index + 1}</td>
                    <td className="px-4 py-2">
                      <div className="flex items-center gap-3 min-w-0">
                        {item.icon_url && (
                          <img
                            src={item.icon_url}
                            alt=""
                            loading="lazy"
                            className="w-14 h-14 shrink-0 object-contain rounded border border-slate-700 bg-slate-900/60 p-1"
                            onError={e => { e.currentTarget.style.display = 'none' }}
                          />
                        )}
                        <div
                          className="min-w-0 font-semibold"
                          style={{ color: getRankColor(item.color) }}
                        >
                          {item.name}
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right font-mono font-semibold text-emerald-300">
                      {item.deals.toLocaleString('ru-RU')}
                    </td>
                    <td className="px-4 py-3 text-right font-mono">{money(item.turnover)}</td>
                    <td className="px-4 py-3 text-right font-mono">{money(item.median_unit)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
