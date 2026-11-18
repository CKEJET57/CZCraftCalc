import { useState } from 'react'
import type { CostNode, Ingredient } from '../types/api'
import { fmtPrice, sourceTag } from '../utils/format'

interface RecipeTreeProps {
  ingredients: Ingredient[]
  excludedIds?: string[]
  pendingExcludedIds?: string[]
  onToggleExclude?: (id: string) => void
}

export function RecipeTree({
  ingredients,
  excludedIds = [],
  pendingExcludedIds = [],
  onToggleExclude,
}: RecipeTreeProps) {
  return (
    <div className="space-y-0.5 font-mono text-sm">
      {ingredients.map((ing, i) => (
        <IngredientRow
          key={`${ing.item_id}-${i}`}
          ing={ing}
          depth={0}
          excludedIds={excludedIds}
          pendingExcludedIds={pendingExcludedIds}
          onToggleExclude={onToggleExclude}
        />
      ))}
    </div>
  )
}

function renderBadge(source: string, craftPath: any) {
  const tag = sourceTag(source)
  if (source === 'craft' && craftPath && craftPath.craft_yield > 0) {
    return (
      <span className={`px-1.5 py-0.5 rounded text-xs whitespace-nowrap ${tag.cls}`}>
        крафт (выход {craftPath.craft_yield})
      </span>
    )
  }
  return <span className={`px-1.5 py-0.5 rounded text-xs whitespace-nowrap ${tag.cls}`}>{tag.label}</span>
}

function IngredientRow({
  ing, depth, excludedIds, pendingExcludedIds, onToggleExclude,
}: {
  ing: Ingredient
  depth: number
  excludedIds: string[]
  pendingExcludedIds: string[]
  onToggleExclude?: (id: string) => void
}) {
  const isExcluded = excludedIds.includes(ing.item_id)
  const isPending = pendingExcludedIds.includes(ing.item_id)
  const hasCraft = Boolean(ing.craft_path?.children?.length)
  const isCraftItem = ing.source === 'craft' && hasCraft
  // По умолчанию раскрываем дерево для предметов, помеченных «крафт»
  const [expanded, setExpanded] = useState(isCraftItem)
  const pad = `${depth * 1.5}rem`

  const displaySource = isExcluded ? 'excluded' : ing.source
  // Цену показываем только у реальной покупки на рынке.
  // У «крафта» цена = ингредиенты + энергия (энергия уже в отдельной строке),
  // у «склада» цена = 0 — в дереве эти цифры не нужны.
  const showPrice = displaySource === 'market'
  // Поддерево «крафта» — реальные входы, флаг hidePrices пробрасывается как есть.
  // Поддерево «рынка» / «склада» — только справка, цены в нём скрываем.
  const childHidePrices = displaySource !== 'craft'

  const rowCls = `flex items-start gap-2 py-0.5 rounded px-2 transition select-none ${
    onToggleExclude ? 'cursor-pointer' : 'cursor-default'
  } ${
    isPending
      ? 'bg-slate-800/80 ring-1 ring-inset ring-amber-500/30'
      : 'hover:bg-slate-900/50'
  }`

  return (
    <div>
      <div
        className={rowCls}
        style={{ paddingLeft: pad }}
        onClick={onToggleExclude ? () => onToggleExclude(ing.item_id) : undefined}
      >
        {hasCraft ? (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation()
              setExpanded(v => !v)
            }}
            className="w-4 shrink-0 text-center text-slate-400 hover:text-slate-200"
            aria-label={expanded ? 'Свернуть дерево крафта' : 'Развернуть дерево крафта'}
            aria-expanded={expanded}
          >
            {expanded ? '▾' : '▸'}
          </button>
        ) : (
          <span className="w-4 shrink-0" aria-hidden="true" />
        )}

        <span className="flex-1 min-w-0 break-words text-slate-300" title={ing.name}>
          {ing.name}
        </span>
        <span className="w-12 text-right text-slate-400">×{ing.amount}</span>
        {renderBadge(displaySource, ing.craft_path)}
        {/* Пустые спаны сохраняют выравнивание колонок независимо от showPrice */}
        <span className="w-24 text-right text-slate-400">
          {showPrice ? fmtPrice(ing.unit_price) : ''}
        </span>
        <span className="w-24 text-right font-semibold">
          {showPrice ? fmtPrice(ing.total_price) : ''}
        </span>
      </div>

      {expanded && hasCraft && ing.craft_path && (
        <>
          {/* Строку «крафт: N× (выход M)» для крафт-предметов не показываем:
              выход уже в плашке. Для рынка/склада — оставляем как контекст. */}
          {ing.source !== 'craft' && (
            <div
              className="text-xs text-violet-400 py-0.5"
              style={{ paddingLeft: `${depth * 1.5 + 1}rem` }}
            >
              ↳ крафт: {ing.craft_path.craft_runs}× (выход {ing.craft_path.craft_yield})
            </div>
          )}
          {ing.craft_path.children!.map((c, i) => (
            <CostNodeRow
              key={`${c.item_id}-${i}`}
              node={c}
              depth={depth + 1}
              excludedIds={excludedIds}
              pendingExcludedIds={pendingExcludedIds}
              onToggleExclude={onToggleExclude}
              hidePrices={childHidePrices}
            />
          ))}
        </>
      )}
    </div>
  )
}

function CostNodeRow({
  node, depth, excludedIds, pendingExcludedIds, onToggleExclude, hidePrices = false,
}: {
  node: CostNode
  depth: number
  excludedIds: string[]
  pendingExcludedIds: string[]
  onToggleExclude?: (id: string) => void
  hidePrices?: boolean
}) {
  const isExcluded = excludedIds.includes(node.item_id)
  const isPending = pendingExcludedIds.includes(node.item_id)
  const hasCraft = Boolean(node.children?.length)
  const isCraftNode = node.source === 'craft' && hasCraft
  const [expanded, setExpanded] = useState(isCraftNode)
  const pad = `${depth * 1.5}rem`

  const displaySource = isExcluded ? 'excluded' : node.source
  // Та же логика, что и в IngredientRow: цена только для реальной покупки
  // и только если мы не внутри информационного поддерева.
  const showPrice = displaySource === 'market' && !hidePrices
  const childHidePrices = hidePrices || displaySource !== 'craft'

  const rowCls = `flex items-start gap-2 py-0.5 rounded px-2 transition select-none ${
    onToggleExclude ? 'cursor-pointer' : 'cursor-default'
  } ${
    isPending
      ? 'bg-slate-800/80 ring-1 ring-inset ring-amber-500/30'
      : 'hover:bg-slate-900/50'
  }`

  return (
    <div>
      <div
        className={rowCls}
        style={{ paddingLeft: pad }}
        onClick={onToggleExclude ? () => onToggleExclude(node.item_id) : undefined}
      >
        {hasCraft ? (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation()
              setExpanded(v => !v)
            }}
            className="w-4 shrink-0 text-center text-slate-400 hover:text-slate-200"
            aria-label={expanded ? 'Свернуть дерево крафта' : 'Развернуть дерево крафта'}
            aria-expanded={expanded}
          >
            {expanded ? '▾' : '▸'}
          </button>
        ) : (
          <span className="w-4 shrink-0" aria-hidden="true" />
        )}

        <span className="flex-1 min-w-0 break-words text-slate-300" title={node.name || node.item_id}>
          {node.name || node.item_id}
        </span>
        <span className="w-12 text-right text-slate-400">×{node.amount}</span>
        {renderBadge(displaySource, node)}
        <span className="w-24 text-right text-slate-400">
          {showPrice ? fmtPrice(node.unit_price) : ''}
        </span>
        <span className="w-24 text-right font-semibold">
          {showPrice ? fmtPrice(node.cost) : ''}
        </span>
      </div>

      {expanded && hasCraft && node.children && (
        <>
          {node.source !== 'craft' && (
            <div
              className="text-xs text-violet-400 py-0.5"
              style={{ paddingLeft: `${depth * 1.5 + 1}rem` }}
            >
              ↳ крафт: {node.craft_runs}× (выход {node.craft_yield})
            </div>
          )}
          {node.children.map((c, i) => (
            <CostNodeRow
              key={`${c.item_id}-${i}`}
              node={c}
              depth={depth + 1}
              excludedIds={excludedIds}
              pendingExcludedIds={pendingExcludedIds}
              onToggleExclude={onToggleExclude}
              hidePrices={childHidePrices}
            />
          ))}
        </>
      )}
    </div>
  )
}