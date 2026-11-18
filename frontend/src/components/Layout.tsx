import { Link, NavLink, Outlet } from 'react-router-dom'
import { api } from '../api/client'

const items = [
  { to: '/', label: 'Главная', end: true },
  { to: '/batch', label: 'Топ по категориям' },
  { to: '/items', label: 'Предметы и рецепты' },
  { to: '/character', label: 'Персонаж' },
]

export function Layout() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800">
        <div className="mx-auto max-w-7xl px-4 py-3 flex items-center gap-6 flex-wrap">
          <Link to="/" className="font-bold text-lg whitespace-nowrap">
            🧪 STALCRAFT Crafting
          </Link>
          <nav className="flex flex-wrap gap-1 text-sm">
            {items.map(n => (
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
          <div className="ml-auto text-xs text-slate-500 font-mono truncate max-w-xs">
            {api.desktop ? 'Desktop · IPC' : `API: ${api.baseUrl}`}
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  )
}
