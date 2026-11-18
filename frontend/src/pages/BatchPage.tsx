import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { BatchResp, Category } from '../types/api'
import { LoadingSpinner } from '../components/LoadingSpinner'
import { ErrorBox } from '../components/ErrorBox'
import { RecipeCard } from '../components/RecipeCard'

export function BatchPage() {
  const [categories, setCategories] = useState<Category[]>([])
  const [bench, setBench] = useState('')
  const [category, setCategory] = useState('')
  const [perCategory, setPerCategory] = useState(false)
  const [top, setTop] = useState(5)
  const [maxRecipes, setMaxRecipes] = useState(10)
  const [sort, setSort] = useState<'margin' | 'profit'>('margin')
  const [recursive, setRecursive] = useState(true)
  const [noHistory, setNoHistory] = useState(true)
  const [workers, setWorkers] = useState(2)
  const [useLocal, setUseLocal] = useState(false)

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<BatchResp | null>(null)

  useEffect(() => { api.categories().then(setCategories).catch(() => {}) }, [])

  async function run() {
    if (loading) return
    setLoading(true); setError(null); setData(null)
    try {
      const r = await api.batch({
        bench: (bench || undefined) as any,
        category: category || undefined,
        per_category: perCategory, top, max_recipes: maxRecipes,
        sort, recursive, no_history: noHistory, workers,
        use_local_data: useLocal,
      })
      setData(r)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">🏆 Топ по категориям</h1>

      <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4 space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <Sel label="Верстак" value={bench} onChange={setBench} options={[
            { value: '', label: 'Любой' },
            { value: 'workbench', label: 'Верстак' },
            { value: 'laboratory_table', label: 'Лабораторный стол' },
            { value: 'kitchen_table', label: 'Кухонный стол' },
          ]} />
          <Sel label="Категория" value={category} onChange={setCategory} options={[
            { value: '', label: 'Все' },
            ...categories.map(c => ({ value: c.id, label: c.name })),
          ]} />
          <Sel label="Сортировка" value={sort} onChange={v => setSort(v as any)} options={[
            { value: 'margin', label: 'По марже' },
            { value: 'profit', label: 'По прибыли' },
          ]} />
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Num label="Топ N" value={top} onChange={setTop} />
          <Num label="Макс. рецептов" value={maxRecipes} onChange={setMaxRecipes} />
          <Num label="Потоков (запросов)" value={workers} onChange={setWorkers} />
          <div className="flex flex-col gap-1 justify-end">
            <Check label="По категориям" checked={perCategory} onChange={setPerCategory} />
            <Check label="Рекурсивный крафт" checked={recursive} onChange={setRecursive} />
            <Check label="Без истории (только лоты)" checked={noHistory} onChange={setNoHistory} />
            <Check label="📦 Из локальной базы (без запросов к API)" checked={useLocal} onChange={setUseLocal} />
          </div>
        </div>

        <button onClick={run} disabled={loading}
          className="rounded-md bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 px-4 py-2 text-sm font-semibold">
          {loading ? 'Считаю…' : 'Запустить анализ'}
        </button>
      </div>

      {loading && <LoadingSpinner label="Анализ может занять 1–3 минуты" />}
      {error && <ErrorBox error={error} />}
      {data && (
        <div className="space-y-4">
          <div className="text-sm text-slate-400">
            Проанализировано: <b>{data.total_analyzed}</b>, с ценами: <b>{data.with_full_price}</b>,
            без данных: <b>{data.without_data}</b>
          </div>
          {data.sections.map((sec, si) => (
            <section key={si} className="space-y-3">
              <h2 className="text-lg font-semibold text-emerald-400">
                {sec.category_name} — Топ-{data.top_n} {data.sort === 'margin' ? 'по марже' : 'по прибыли'}
              </h2>
              {sec.items.length === 0 && (
                <div className="text-sm text-slate-500">Нет рецептов с полными ценами</div>
              )}
              {sec.items.map((a, i) => <RecipeCard key={i} a={a} />)}
            </section>
          ))}
        </div>
      )}
    </div>
  )
}

function Sel({ label, value, onChange, options }:
  { label: string; value: string; onChange: (v: string) => void;
    options: { value: string; label: string }[] }) {
  return (
    <div>
      <label className="block text-xs text-slate-400 mb-1">{label}</label>
      <select value={value} onChange={e => onChange(e.target.value)}
        className="w-full rounded-md bg-slate-900 border border-slate-700 px-2 py-1.5 text-sm">
        {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </div>
  )
}

function Num({ label, value, onChange }:
  { label: string; value: number; onChange: (n: number) => void }) {
  return (
    <div>
      <label className="block text-xs text-slate-400 mb-1">{label}</label>
      <input type="number" value={value}
        onChange={e => onChange(parseInt(e.target.value) || 0)}
        className="w-full rounded-md bg-slate-900 border border-slate-700 px-2 py-1.5 text-sm" />
    </div>
  )
}

function Check({ label, checked, onChange }:
  { label: string; checked: boolean; onChange: (b: boolean) => void }) {
  return (
    <label className="flex items-center gap-2 cursor-pointer text-sm">
      <input type="checkbox" checked={checked} onChange={e => onChange(e.target.checked)}
        className="h-4 w-4 accent-emerald-500" />
      {label}
    </label>
  )
}