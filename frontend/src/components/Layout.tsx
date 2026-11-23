import { useState } from 'react'
import { Link, NavLink, Outlet } from 'react-router-dom'
import { api } from '../api/client'

const items = [
  { to: '/', label: 'Главная', end: true },
  { to: '/batch', label: 'Топ по категориям' },
  { to: '/items', label: 'Предметы и рецепты' },
  { to: '/top-items', label: 'Самые продаваемые' },
  { to: '/character', label: 'Персонаж' },
]

export function Layout() {
  const [syncing, setSyncing] = useState(false)
  const [syncMessage, setSyncMessage] = useState('')
  const [syncError, setSyncError] = useState('')
  const visibleItems = api.desktop
    ? items.filter(item => !['/', '/batch', '/character'].includes(item.to))
    : items

  async function syncMarketData() {
    if (syncing) return
    setSyncing(true)
    setSyncMessage('')
    setSyncError('')
    try {
      const result = await api.syncMarketData()
      setSyncMessage(`Обновлено файлов: ${result.files}; час: ${result.hour ?? 'нет данных'}`)
      window.dispatchEvent(new Event('market-data-synced'))
    } catch (err) {
      setSyncError(err instanceof Error ? err.message : String(err))
    } finally {
      setSyncing(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800">
        <div className="mx-auto max-w-7xl px-4 py-3 flex items-center gap-4 flex-wrap">
          <Link to="/" className="font-bold text-lg whitespace-nowrap">
            🧪 STALCRAFT Crafting
          </Link>
          <nav className="flex flex-wrap gap-1 text-sm">
            {visibleItems.map(n => (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.end}
                className={({ isActive }) =>
                  `px-3 py-1.5 rounded-md transition ${
                    isActive
                      ? 'bg-emerald-500/15 text-emerald-300'
                      : 'text-slate-300 hover:bg-slate-800'
                  }`
                }
              >
                {n.label}
              </NavLink>
            ))}
          </nav>
          {api.desktop && (
            <button
              type="button"
              onClick={syncMarketData}
              disabled={syncing}
              className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm font-medium text-slate-200 hover:bg-slate-700 disabled:opacity-50"
            >
              {syncing ? 'Синхронизация…' : 'Обновить рыночные данные'}
            </button>
          )}
          <div className="ml-auto text-xs text-slate-500 font-mono truncate max-w-xs">
            {api.desktop ? 'Desktop · IPC' : `API: ${api.baseUrl}`}
          </div>
        </div>
        {api.desktop && (syncMessage || syncError) && (
          <div className={`mx-auto max-w-7xl px-4 pb-2 text-xs ${syncError ? 'text-rose-300' : 'text-emerald-300'}`}>
            {syncError || syncMessage}
          </div>
        )}
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  )
}
