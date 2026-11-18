import { Link } from 'react-router-dom'
import { api } from '../api/client'

export function HomePage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">🧪 STALCRAFT Crafting Calculator</h1>
        <p className="text-slate-400 mt-1">
          Веб-версия калькулятора экономики крафта. Бэкенд:{' '}
          <code className="text-emerald-400">{api.baseUrl}</code>
        </p>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <Card to="/batch" title="🏆 Топ по категориям" desc="Пакетный анализ: самые прибыльные рецепты." />
        <Card to="/items" title="📋 Список предметов" desc="Описание, рецепт крафта и полная история торгов." />
        <Card to="/character" title="🧑 Профиль персонажа" desc="Публичные данные по нику." />
      </div>
    </div>
  )
}

function Card({ to, title, desc }: { to: string; title: string; desc: string }) {
  return (
    <Link to={to} className="block rounded-xl border border-slate-800 bg-slate-900/40 p-4 hover:border-emerald-600/50 hover:bg-slate-900 transition">
      <div className="font-semibold">{title}</div>
      <div className="text-sm text-slate-400 mt-1">{desc}</div>
    </Link>
  )
}