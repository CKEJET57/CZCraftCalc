import { useState, useMemo } from 'react'
import {
  LineChart, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid,
} from 'recharts'
import { api } from '../api/client'
import type {
  HistoryResp, RecipeAnalysis, ItemDetails, ItemVariant,
  InfoBlock, InfoBlockElement, Deal, MarketAnalysisResp,
} from '../types/api'
import { ItemPicker } from '../components/ItemPicker'
import { LoadingSpinner } from '../components/LoadingSpinner'
import { ErrorBox } from '../components/ErrorBox'
import { RecipeCard } from '../components/RecipeCard'
import { MarketAnalysisPanel } from '../components/MarketAnalysisPanel'
import { fmtPrice, fmtPct } from '../utils/format'
import { getRankColor } from '../utils/rankColors'

const ALLOWED_COMPACT_STATS = [
  'Тип боеприпасов', 'Тип', 'Вес', 'Прочность', 'Макс. прочность',
  'Скорость передвижения', 'Урон', 'Объем магазина', 'Максимальная дистанция',
  'Скорострельность', 'Перезарядка', 'Тактическая перезарядка',
  'Эргономика оружия', 'Разброс', 'Разброс от бедра', 'Вертикальная отдача',
  'Горизонтальная отдача', 'Доставание', 'Прицеливание', 'Урон в голову', 'Урон по конечностям',
]

const PAGE_SIZE = 30

const WEAPON_MARKERS = [
  'Урон', 'Объем магазина', 'Разброс', 'Скорострельность', 'Перезарядка',
  'Урон в голову', 'Урон по конечностям', 'Вертикальная отдача',
]

const ARMOR_MARKERS = [
  'Габариты', 'Пулестойкость', 'Защита от разрыва', 'Защита от взрыва',
]

interface Settings {
  fee: number
  maxDepth: number
  workers: number
  recursive: boolean
  noHistory: boolean
  ignoreMissing: boolean
  useLocal: boolean
}

const DEFAULT_SETTINGS: Settings = {
  fee: 5,
  maxDepth: 12,
  workers: 4,
  recursive: true,
  noHistory: true,
  ignoreMissing: false,
  useLocal: false,
}

function settingsEqual(a: Settings | null, b: Settings): boolean {
  if (!a) return false
  return (
    a.fee === b.fee && a.maxDepth === b.maxDepth && a.workers === b.workers &&
    a.recursive === b.recursive && a.noHistory === b.noHistory &&
    a.ignoreMissing === b.ignoreMissing && a.useLocal === b.useLocal
  )
}

export function ItemPage() {
  const [itemId, setItemId] = useState('')
  const [quickLoading, setQuickLoading] = useState(false)

  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [lastRunSettings, setLastRunSettings] = useState<Settings | null>(null)

  const [itemDetails, setItemDetails] = useState<ItemDetails | null>(null)
  const [variants, setVariants] = useState<ItemVariant[] | null>(null)
  const [variantLevel, setVariantLevel] = useState(0)
  const [statView, setStatView] = useState<'compact' | 'detailed'>('compact')

  const [historyData, setHistoryData] = useState<HistoryResp | null>(null)
  const [allDeals, setAllDeals] = useState<Deal[]>([])
  const [historyPage, setHistoryPage] = useState(0)
  const [hasMoreDeals, setHasMoreDeals] = useState(false)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [viewMode, setViewMode] = useState<'chart' | 'list'>('chart')

  const [recipeData, setRecipeData] = useState<RecipeAnalysis[] | null>(null)
  const [recipeLoading, setRecipeLoading] = useState(false)
  const [recipeError, setRecipeError] = useState<string | null>(null)
  const [recipeElapsed, setRecipeElapsed] = useState<number | null>(null)

  // Рыночная аналитика
  const [marketData, setMarketData] = useState<MarketAnalysisResp | null>(null)
  const [marketDays, setMarketDays] = useState(7)
  const [marketLoading, setMarketLoading] = useState(false)

  const [excludedIds, setExcludedIds] = useState<string[]>([])
  const [lastRunExcludedIds, setLastRunExcludedIds] = useState<string[]>([])

  const [error, setError] = useState<string | null>(null)

  // ─── Загрузчики ───

  async function loadQuickData(id: string) {
    setItemDetails(null); setVariants(null); setVariantLevel(0)
    setHistoryData(null); setAllDeals([]); setHistoryPage(0); setHasMoreDeals(false)
    setHistoryLoading(true); setError(null)
    setQuickLoading(true)

    try {
      const [dRes, vRes, hRes] = await Promise.all([
        api.itemDetails(id).catch(() => null),
        api.itemVariants(id).catch(() => null),
        api.history({ item_id: id, limit: 200, show: PAGE_SIZE, page: 0, sort: 'newest' }),
      ])
      if (dRes) setItemDetails(dRes)
      if (vRes?.available) setVariants(vRes.variants)
      setHistoryData(hRes)
      setAllDeals(hRes.deals)
      setHasMoreDeals(hRes.total_pages > 1)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setHistoryLoading(false)
      setQuickLoading(false)
    }
  }

  async function loadMoreDeals() {
    if (!itemId || !hasMoreDeals || historyLoading) return
    setHistoryLoading(true)
    try {
      const nextPage = historyPage + 1
      const h = await api.history({
        item_id: itemId, limit: 200, show: PAGE_SIZE, page: nextPage, sort: 'newest',
      })
      setAllDeals(prev => [...prev, ...h.deals])
      setHistoryPage(nextPage)
      setHasMoreDeals(nextPage + 1 < h.total_pages)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setHistoryLoading(false)
    }
  }

  async function runRecipe(id: string, s: Settings, exclusions: string[]) {
    if (!id) return
    setRecipeLoading(true); setRecipeError(null); setRecipeData(null); setRecipeElapsed(null)
    const t0 = performance.now()

    try {
      const r = await api.recipe({
        item_id: id,
        recursive: s.recursive,
        no_history: s.noHistory,
        fee: s.fee,
        max_depth: s.maxDepth,
        workers: s.workers,
        ignore_missing: s.ignoreMissing,
        exclude: exclusions,
        use_local_data: s.useLocal,
      })
      setRecipeData(r.recipes)
      setLastRunSettings(s)
      setLastRunExcludedIds(exclusions)
    } catch (e: any) {
      setRecipeError(e.message)
    } finally {
      setRecipeLoading(false)
      setRecipeElapsed((performance.now() - t0) / 1000)
    }
  }

  async function loadMarketData(id: string, days: number) {
    setMarketLoading(true)
    try {
      const r = await api.marketAnalysis(id, days)
      console.log('[market-analysis] OK', r)
      setMarketData(r)
    } catch {
      setMarketData(null)
    } finally {
      setMarketLoading(false)
    }
  }

  // ─── Обработчики ───

  function onSelectItem(id: string) {
    setItemId(id)
    setExcludedIds([])
    setLastRunExcludedIds([])
    setRecipeData(null); setRecipeError(null); setRecipeElapsed(null)
    setMarketData(null)
    setStatView('compact')
    loadQuickData(id)
    runRecipe(id, settings, [])
    loadMarketData(id, marketDays)
  }

  function onRecalculate() {
    if (!itemId) return
    runRecipe(itemId, settings, excludedIds)
  }

  function onMarketDaysChange(d: number) {
    setMarketDays(d)
    if (itemId) loadMarketData(itemId, d)
  }

  function toggleExclude(id: string) {
    setExcludedIds(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
    )
  }

  // ─── Производные ───

  const settingsChanged = !settingsEqual(lastRunSettings, settings)
  const exclusionsChanged =
    excludedIds.length !== lastRunExcludedIds.length ||
    excludedIds.some(id => !lastRunExcludedIds.includes(id))
  const hasPendingChanges = (settingsChanged || exclusionsChanged) && Boolean(lastRunSettings)

  // «Ожидающие» исключения — те, что ещё не применены в последнем расчёте.
  // Именно их и подсвечиваем янтарным кольцом; после пересчёта кольцо гаснет,
  // а тег «склад» и общая подсветка фона остаются.
  const pendingExcludedIds = useMemo(() => {
    const set = new Set<string>()
    for (const id of excludedIds) {
      if (!lastRunExcludedIds.includes(id)) set.add(id)
    }
    for (const id of lastRunExcludedIds) {
      if (!excludedIds.includes(id)) set.add(id)
    }
    return Array.from(set)
  }, [excludedIds, lastRunExcludedIds])

  const hasUpgrade = Boolean(variants && variants.length > 0)
  const maxLevel = variants?.length ?? 0

  const displayBlocks = useMemo(() => {
    if (!itemDetails) return []
    if (variantLevel > 0 && variants) {
      const v = variants.find(x => x.level === variantLevel)
      if (v) return v.blocks
    }
    return itemDetails.blocks
  }, [itemDetails, variants, variantLevel])

  // Описание (первый text-блок с пустым title) отделяем от остальных блоков
  const description = useMemo(() => {
    for (const b of displayBlocks) {
      if (b.type === 'text' && !b.title) return b.text ?? null
    }
    return null
  }, [displayBlocks])

  const blocksWithoutDescription = useMemo(
    () => displayBlocks.filter(b => !(b.type === 'text' && !b.title)),
    [displayBlocks],
  )

  // Категория: сначала пробуем recipeData, потом fallback по названиям статов
  const isWeapon = useMemo(() => {
    const cat = (recipeData?.[0]?.category ?? '').toLowerCase()
    if (cat.includes('weapon')) return true
    if (cat.includes('armor') || cat.includes('clothes')) return false

    const names = new Set<string>()
    itemDetails?.blocks.forEach(b => b.elements?.forEach(e => names.add(e.name)))
    return WEAPON_MARKERS.some(s => names.has(s))
  }, [itemDetails, recipeData])

  const isArmorOrClothes = useMemo(() => {
    const cat = (recipeData?.[0]?.category ?? '').toLowerCase()
    if (cat.includes('armor') || cat.includes('clothes')) return true

    const names = new Set<string>()
    itemDetails?.blocks.forEach(b => b.elements?.forEach(e => names.add(e.name)))
    return ARMOR_MARKERS.some(s => names.has(s))
  }, [itemDetails, recipeData])

  const compactElements = useMemo(() => {
    const els: InfoBlockElement[] = []
    blocksWithoutDescription.forEach(block => {
      if (block.type === 'list' && block.elements) {
        block.elements.forEach(el => {
          if (
            ALLOWED_COMPACT_STATS.includes(el.name) ||
            el.name.includes('Урон в голову') ||
            el.name.includes('Урон по конечностям')
          ) {
            els.push(el)
          }
        })
      }
    })
    return els
  }, [blocksWithoutDescription])

  const chartData = useMemo(() => {
    return allDeals
      .filter(d => d.time)
      .map(d => ({
        t: new Date(d.time!).toLocaleString('ru-RU', {
          day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
        }),
        price: Math.round(d.unit),
        amount: d.amount,
      }))
      .reverse()
  }, [allDeals])

  const sortedRecipes = useMemo(() => {
    if (!recipeData) return []
    return [...recipeData].sort((a, b) => {
      const ap = a.profit ?? -Infinity
      const bp = b.profit ?? -Infinity
      return bp - ap
    })
  }, [recipeData])

  // ─── Рендер ───

  return (
    <div className="space-y-6 pb-20">
      {/* [1] Поиск и настройки */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4 space-y-3">
        <div className="flex gap-3 items-end">
          <div className="flex-1">
            <label className="block text-xs text-slate-400 mb-1">Предмет</label>
            <ItemPicker value={itemId} onChange={onSelectItem} />
          </div>
          <button
            onClick={() => setSettingsOpen(v => !v)}
            className="rounded-md border border-slate-700 hover:border-slate-500 px-3 py-2 text-sm text-slate-300 flex items-center gap-1 shrink-0"
          >
            Настройки {settingsOpen ? '▴' : '▾'}
          </button>
          <button
            onClick={onRecalculate}
            disabled={recipeLoading || !itemId}
            className="rounded-md bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 px-4 py-2 text-sm font-semibold shrink-0"
          >
            {recipeLoading ? 'Считаю…' : 'Рассчитать'}
          </button>
        </div>

        {settingsOpen && (
          <div className="space-y-3 pt-3 border-t border-slate-800">
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              <Num label="Комиссия (%)" value={settings.fee}
                onChange={v => setSettings(s => ({ ...s, fee: v }))} step={0.5} />
              <Num label="Макс. глубина" value={settings.maxDepth}
                onChange={v => setSettings(s => ({ ...s, maxDepth: v }))} />
              <Num label="Потоков" value={settings.workers}
                onChange={v => setSettings(s => ({ ...s, workers: v }))} />
            </div>
            <div className="flex flex-wrap gap-4 text-sm">
              <Check label="Рекурсивный крафт" checked={settings.recursive}
                onChange={v => setSettings(s => ({ ...s, recursive: v }))} />
              <Check label="Без истории (только лоты)" checked={settings.noHistory}
                onChange={v => setSettings(s => ({ ...s, noHistory: v }))} />
              <Check label="Игнорировать ошибки цен" checked={settings.ignoreMissing}
                onChange={v => setSettings(s => ({ ...s, ignoreMissing: v }))} />
              <Check label="Из локальной базы" checked={settings.useLocal}
                onChange={v => setSettings(s => ({ ...s, useLocal: v }))} />
            </div>
          </div>
        )}
      </div>

      {/* Sticky «Пересчитать» */}
      {hasPendingChanges && !recipeLoading && itemId && (
        <div className="sticky top-4 z-20 flex justify-center">
          <button
            onClick={onRecalculate}
            className="rounded-full bg-emerald-600 hover:bg-emerald-500 px-6 py-2.5 text-sm font-bold shadow-lg shadow-emerald-900/50 flex items-center gap-2 text-white"
          >
            🔄 Пересчитать
            {excludedIds.length > 0 && (
              <span className="text-emerald-200">(склад: {excludedIds.length})</span>
            )}
          </button>
        </div>
      )}

      {error && <ErrorBox error={error} />}

      {/* Лоадер быстрых данных (характеристики + история) */}
      {itemId && quickLoading && (
        <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-6 text-center">
          <LoadingSpinner label="Загрузка характеристик и истории…" />
        </div>
      )}

      {/* [2] Идентичность + характеристики */}
      {itemDetails && historyData && (
        <div className="rounded-xl border border-slate-800 bg-slate-900/40 overflow-hidden">
          <ItemHeader
            itemDetails={itemDetails}
            itemName={historyData.item_name}
            description={description}
            hasUpgrade={hasUpgrade}
            maxLevel={maxLevel}
            variantLevel={variantLevel}
            setVariantLevel={setVariantLevel}
          />
          <div className="border-t border-slate-800 p-4">
            <ItemStats
              displayBlocks={blocksWithoutDescription}
              isArmorOrClothes={isArmorOrClothes}
              isWeapon={isWeapon}
              statView={statView}
              setStatView={setStatView}
              compactElements={compactElements}
            />
          </div>
        </div>
      )}

      {/* [3] Расчёт крафта */}
      {itemId && itemDetails && historyData && (
        <div className="space-y-3">
          <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">
            Расчёт крафта
          </h3>

          {recipeLoading && (
            <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-6 text-center">
              <LoadingSpinner label="Анализ экономики. Обычно 30–90 сек." />
              <div className="text-xs text-slate-500 mt-2">
                Уменьшите «Макс. глубину» или выключите «Рекурсивный крафт», чтобы ускорить.
              </div>
            </div>
          )}

          {!recipeLoading && recipeError && <ErrorBox error={recipeError} />}

          {!recipeLoading && !recipeError && recipeData && recipeData.length === 0 && (
            <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4 text-sm text-slate-500">
              Предмет невозможно получить через крафт или бартер.
            </div>
          )}

          {!recipeLoading && !recipeError && sortedRecipes.length > 0 && (
            <div className="space-y-3">
              {sortedRecipes.map((r, i) => (
                <AccordionRecipe
                  key={`${r.bench}-${r.result_item_id}-${i}`}
                  rank={i + 1}
                  recipe={r}
                  defaultExpanded={i === 0}
                  excludedIds={excludedIds}
                  pendingExcludedIds={pendingExcludedIds}
                  onToggleExclude={toggleExclude}
                />
              ))}
              {recipeElapsed != null && (
                <div className="text-xs text-slate-500">Готово за {recipeElapsed.toFixed(1)} с</div>
              )}
            </div>
          )}
        </div>
      )}

      {/* [3.5] Рыночная аналитика */}
      {itemId && (
        <MarketAnalysisPanel
          data={marketData}
          days={marketDays}
          onDaysChange={onMarketDaysChange}
          loading={marketLoading}
        />
      )}

      {/* [4] История */}
      {historyData && (
        <ItemHistory
          historyData={historyData}
          deals={allDeals}
          chartData={chartData}
          viewMode={viewMode}
          setViewMode={setViewMode}
          hasMore={hasMoreDeals}
          loading={historyLoading}
          onLoadMore={loadMoreDeals}
        />
      )}
    </div>
  )
}

// ─────────────────────────────────────────────
// Аккордеон одного RecipeCard
// ─────────────────────────────────────────────

function AccordionRecipe({
  rank, recipe, defaultExpanded, excludedIds, pendingExcludedIds, onToggleExclude,
}: {
  rank: number
  recipe: RecipeAnalysis
  defaultExpanded: boolean
  excludedIds: string[]
  pendingExcludedIds: string[]
  onToggleExclude: (id: string) => void
}) {
  const [open, setOpen] = useState(defaultExpanded)
  const profitCls = (recipe.profit ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'
  const marginCls = (recipe.margin_pct ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/40 overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between gap-3 p-4 text-left hover:bg-slate-800/30 transition"
      >
        <div className="flex items-center gap-3 min-w-0">
          <span className="text-slate-500 font-mono text-sm shrink-0">#{rank}</span>
          <div className="min-w-0">
            <div className="font-semibold text-slate-100 truncate">
              {recipe.result_name}{' '}
              <span className="text-slate-500">×{recipe.result_amount}</span>
            </div>
            <div className="text-xs text-slate-500 truncate">
              {recipe.kind === 'barter' ? (
                <>
                  <span className="px-1 py-0.5 rounded bg-violet-500/15 text-violet-300 mr-1">бартер</span>
                  {recipe.subcategory}
                </>
              ) : (
                <>{recipe.category} / {recipe.subcategory}</>
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-4 shrink-0 text-sm">
          {recipe.profit != null && (
            <span className={`font-mono font-semibold ${profitCls}`}>
              {fmtPrice(recipe.profit)}
            </span>
          )}
          {recipe.margin_pct != null && (
            <span className={`font-mono text-xs ${marginCls}`}>
              {fmtPct(recipe.margin_pct)}
            </span>
          )}
          <span className="text-slate-400 w-4 text-center">{open ? '▾' : '▸'}</span>
        </div>
      </button>
      {open && (
        <div className="px-4 pb-4">
          <RecipeCard
            a={recipe}
            excludedIds={excludedIds}
            pendingExcludedIds={pendingExcludedIds}
            onToggleExclude={onToggleExclude}
            bare
            hideHeader
          />
        </div>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────
// Header: иконка, имя, описание, +/- прокачка
// ─────────────────────────────────────────────

function ItemHeader({
  itemDetails, itemName, description, hasUpgrade, maxLevel, variantLevel, setVariantLevel,
}: {
  itemDetails: ItemDetails
  itemName: string
  description: string | null
  hasUpgrade: boolean
  maxLevel: number
  variantLevel: number
  setVariantLevel: React.Dispatch<React.SetStateAction<number>>
}) {
  return (
    <div className="p-4">
      <div className="flex gap-4 items-start">
        {itemDetails.icon_url && (
          <div className="shrink-0">
            <img
              src={itemDetails.icon_url}
              alt={itemName}
              className="w-[120px] h-[120px] object-contain rounded border border-slate-700 bg-slate-900/60 p-1"
              onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
            />
          </div>
        )}

        <div className="flex-1 min-w-0">
          <h2
            className="text-xl font-bold text-slate-100 mb-1 truncate"
            style={{ color: getRankColor(itemDetails.color) }}
          >
            {itemName}
          </h2>
          {description && (
            <p className="text-xs text-slate-400 leading-relaxed whitespace-pre-wrap">
              {description}
            </p>
          )}
        </div>

        {hasUpgrade && (
          <div className="shrink-0 flex flex-col items-end">
            <div className="flex items-center gap-1 rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-1 mt-1">
              <button
                type="button"
                onClick={() => setVariantLevel(v => Math.max(0, v - 1))}
                disabled={variantLevel <= 0}
                aria-label="Понизить уровень прокачки"
                className="w-7 h-7 flex items-center justify-center rounded text-emerald-400 hover:bg-emerald-500/20 disabled:opacity-30 disabled:cursor-not-allowed font-bold select-none leading-none"
              >−</button>
              <span className="min-w-[3.25rem] text-center text-sm font-mono font-bold text-emerald-400 select-none">
                {variantLevel === 0 ? '0' : `+${variantLevel}`}
              </span>
              <button
                type="button"
                onClick={() => setVariantLevel(v => Math.min(maxLevel, v + 1))}
                disabled={variantLevel >= maxLevel}
                aria-label="Повысить уровень прокачки"
                className="w-7 h-7 flex items-center justify-center rounded text-emerald-400 hover:bg-emerald-500/20 disabled:opacity-30 disabled:cursor-not-allowed font-bold select-none leading-none"
              >+</button>
            </div>
            {variantLevel > 0 && (
              <button
                type="button"
                onClick={() => setVariantLevel(0)}
                className="text-xs text-slate-400 hover:text-slate-200 underline mt-1.5"
              >Сброс</button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────
// Stats: компакт / подробно
// ─────────────────────────────────────────────

function ItemStats({
  displayBlocks, isArmorOrClothes, isWeapon, statView, setStatView, compactElements,
}: {
  displayBlocks: InfoBlock[]
  isArmorOrClothes: boolean
  isWeapon: boolean
  statView: 'compact' | 'detailed'
  setStatView: (v: 'compact' | 'detailed') => void
  compactElements: InfoBlockElement[]
}) {
  const effectiveView: 'compact' | 'detailed' = isWeapon ? statView : 'detailed'

  return (
    <>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-bold text-slate-200 flex items-center gap-2">
          <span className="text-slate-400">📄</span> Характеристики
        </h3>
        {isWeapon && (
          <div className="flex bg-slate-900 rounded-md p-1 border border-slate-800">
            <button onClick={() => setStatView('compact')}
              className={`px-3 py-1 text-xs rounded transition ${statView === 'compact' ? 'bg-slate-700 text-white shadow' : 'text-slate-400 hover:text-slate-200'}`}>
              Компактный
            </button>
            <button onClick={() => setStatView('detailed')}
              className={`px-3 py-1 text-xs rounded transition ${statView === 'detailed' ? 'bg-slate-700 text-white shadow' : 'text-slate-400 hover:text-slate-200'}`}>
              Подробный
            </button>
          </div>
        )}
      </div>

      {effectiveView === 'compact' ? (
        <div className="flex flex-col">
          {compactElements.map((el, i) => (
            <div key={i} className="flex justify-between items-center text-sm px-2 py-1 hover:bg-slate-800/30 rounded">
              <span style={{ color: el.nameColor ? `#${el.nameColor}` : '#94a3b8' }}>{el.name}</span>
              <span className="font-semibold font-mono text-right" style={{ color: el.valueColor ? `#${el.valueColor}` : '#fff' }}>{el.value}</span>
            </div>
          ))}
          {compactElements.length === 0 && (
            <div className="text-sm text-slate-500 italic p-2">Нет данных для компактного отображения</div>
          )}
        </div>
      ) : (
        <div className="space-y-4">
          {displayBlocks.map((block, idx) => {
            const hasTitle = Boolean(block.title)
            const content = (
              <>
                {block.type === 'list' && block.elements && (
                  <div className="flex flex-col gap-0.5 mt-1">
                    {block.elements.map((el, i) => (
                      <div key={i} className="flex justify-between text-sm px-2 py-0.5 hover:bg-slate-800/30 rounded">
                        <span style={{ color: el.nameColor ? `#${el.nameColor}` : '#94a3b8' }}>{el.name}</span>
                        <span className="font-semibold font-mono" style={{ color: el.valueColor ? `#${el.valueColor}` : '#fff' }}>{el.value}</span>
                      </div>
                    ))}
                  </div>
                )}
                {block.type === 'text' && (
                  <p className="text-sm text-slate-300 leading-relaxed whitespace-pre-wrap mt-1">
                    {block.text}
                  </p>
                )}
              </>
            )

            if (hasTitle && !isArmorOrClothes) {
              return (
                <details key={idx} className="group" open>
                  <summary className="cursor-pointer text-xs font-semibold text-emerald-400/80 hover:text-emerald-400 uppercase tracking-wider select-none flex items-center gap-2">
                    <span className="transition-transform group-open:rotate-90">▶</span>
                    {block.title}
                  </summary>
                  <div className="pl-4 mt-2 border-l border-slate-800">{content}</div>
                </details>
              )
            }
            return (
              <div key={idx} className="mt-4">
                {hasTitle && (
                  <div className="text-xs font-semibold text-emerald-400/80 uppercase tracking-wider mb-2">{block.title}</div>
                )}
                {content}
              </div>
            )
          })}
        </div>
      )}
    </>
  )
}

// ─────────────────────────────────────────────
// История: график / список + «Показать ещё»
// ─────────────────────────────────────────────

function ItemHistory({
  historyData, deals, chartData, viewMode, setViewMode, hasMore, loading, onLoadMore,
}: {
  historyData: HistoryResp
  deals: Deal[]
  chartData: any[]
  viewMode: 'chart' | 'list'
  setViewMode: (m: 'chart' | 'list') => void
  hasMore: boolean
  loading: boolean
  onLoadMore: () => void
}) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">История сделок</h3>
        <div className="flex bg-slate-900 rounded-md p-1 border border-slate-800">
          <button onClick={() => setViewMode('chart')}
            className={`px-3 py-1 text-xs rounded transition ${viewMode === 'chart' ? 'bg-slate-700 text-white shadow' : 'text-slate-400 hover:text-slate-200'}`}>
            График
          </button>
          <button onClick={() => setViewMode('list')}
            className={`px-3 py-1 text-xs rounded transition ${viewMode === 'list' ? 'bg-slate-700 text-white shadow' : 'text-slate-400 hover:text-slate-200'}`}>
            Список
          </button>
        </div>
      </div>

      {!historyData.stats.n_deals ? (
        <div className="text-sm text-slate-500">
          {historyData.stats.empty_reason ?? 'Нет данных о сделках'}
        </div>
      ) : viewMode === 'chart' ? (
        <div className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
            <Stat label="Сделок" value={String(historyData.stats.n_deals)} />
            <Stat label="Медиана" value={fmtPrice(historyData.stats.median)} />
            <Stat label="Мин. цена" value={fmtPrice(historyData.stats.min)} />
            <Stat label="Макс. цена" value={fmtPrice(historyData.stats.max)} />
          </div>
          <div className="h-64 bg-slate-900/60 rounded border border-slate-800 p-3">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 10, right: 10, left: 10, bottom: 0 }}>
                <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                <XAxis dataKey="t" stroke="#64748b" fontSize={11} minTickGap={30} />
                <YAxis stroke="#64748b" fontSize={11} domain={['auto', 'auto']} />
                <Tooltip content={<CustomTooltip />} cursor={{ stroke: '#334155', strokeWidth: 1, strokeDasharray: '3 3' }} />
                <Line type="monotone" dataKey="price" name="Цена" stroke="#34d399" strokeWidth={2} dot={false} activeDot={{ r: 4, fill: '#34d399', stroke: '#0f172a' }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="rounded border border-slate-800 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-slate-900 text-slate-400">
                <tr>
                  <th className="text-left px-3 py-2">Время</th>
                  <th className="text-right px-3 py-2">Цена/шт</th>
                  <th className="text-right px-3 py-2">Кол-во</th>
                  <th className="text-right px-3 py-2">Итого</th>
                </tr>
              </thead>
              <tbody>
                {deals.map((d, i) => (
                  <tr key={i} className="border-t border-slate-800 hover:bg-slate-900/50">
                    <td className="px-3 py-1.5 text-slate-300">
                      {d.time ? new Date(d.time).toLocaleString('ru-RU') : '—'}
                    </td>
                    <td className="px-3 py-1.5 text-right font-mono">{fmtPrice(d.unit)}</td>
                    <td className="px-3 py-1.5 text-right">{d.amount}</td>
                    <td className="px-3 py-1.5 text-right font-mono">{fmtPrice(d.price)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {hasMore && (
            <div className="flex justify-center">
              <button
                onClick={onLoadMore}
                disabled={loading}
                className="rounded bg-slate-800 hover:bg-slate-700 disabled:opacity-50 px-4 py-1.5 text-sm"
              >
                {loading ? 'Загрузка…' : 'Показать ещё'}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────
// Утилиты
// ─────────────────────────────────────────────

function CustomTooltip({ active, payload, label }: any) {
  if (active && payload && payload.length) {
    const data = payload[0].payload
    return (
      <div className="rounded-md border border-slate-700 bg-slate-900/95 p-2 text-sm shadow-xl backdrop-blur">
        <p className="text-slate-400 mb-1">{label}</p>
        <p className="font-semibold text-emerald-400">Цена: {data.price.toLocaleString('ru-RU')} ₽/шт</p>
        <p className="text-slate-300">Куплено: <span className="font-bold">{data.amount} шт</span></p>
      </div>
    )
  }
  return null
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md bg-slate-900/60 border border-slate-800 px-3 py-2">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="font-semibold font-mono">{value}</div>
    </div>
  )
}

function Num({ label, value, onChange, step = 1 }:
  { label: string; value: number; onChange: (n: number) => void; step?: number }) {
  return (
    <div>
      <label className="block text-xs text-slate-400 mb-1">{label}</label>
      <input type="number" step={step} value={value}
        onChange={e => onChange(parseFloat(e.target.value) || 0)}
        className="w-full rounded-md bg-slate-900 border border-slate-700 px-2 py-1.5 text-sm" />
    </div>
  )
}

function Check({ label, checked, onChange }:
  { label: string; checked: boolean; onChange: (b: boolean) => void }) {
  return (
    <label className="flex items-center gap-2 cursor-pointer">
      <input type="checkbox" checked={checked} onChange={e => onChange(e.target.checked)}
        className="h-4 w-4 accent-emerald-500" />
      {label}
    </label>
  )
}