import type { MarketAnalysisResp, MarketLiquidity, BestTimeBucket } from '../types/api'
import { fmtPrice } from '../utils/format'

const LEVEL_STYLE: Record<string, { label: string; cls: string }> = {
  HIGH:   { label: 'высокая', cls: 'bg-emerald-500/15 text-emerald-300' },
  MEDIUM: { label: 'средняя', cls: 'bg-amber-500/15 text-amber-300' },
  LOW:    { label: 'низкая',  cls: 'bg-rose-500/15 text-rose-300' },
}

const WEEKDAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']

export function MarketAnalysisPanel({ data, days, onDaysChange, loading }: {
  data: MarketAnalysisResp | null
  days: number
  onDaysChange: (d: number) => void
  loading: boolean
}) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">Рыночная аналитика</h3>
        <div className="flex bg-slate-900 rounded-md p-1 border border-slate-800 text-xs">
          {[7, 14, 30, 90].map(d => (
            <button key={d} onClick={() => onDaysChange(d)}
              className={`px-2 py-1 rounded ${days === d ? 'bg-slate-700 text-white' : 'text-slate-400 hover:text-slate-200'}`}>
              {d}д
            </button>
          ))}
        </div>
      </div>

      {loading && <div className="text-sm text-slate-500">Загрузка аналитики…</div>}

      {!loading && data?.warnings && data.warnings.length > 0 && (
        <div className="rounded border border-amber-500/30 bg-amber-500/5 p-2 text-xs text-amber-300 space-y-0.5">
          {data.warnings.map((w, i) => <div key={i}>⚠️ {w}</div>)}
        </div>
      )}

      {!loading && data?.liquidity && <LiquidityBlock liq={data.liquidity} />}
      {!loading && data?.best_time && <BestTimeBlock best={data.best_time} />}
    </div>
  )
}

function LiquidityBlock({ liq }: { liq: MarketLiquidity }) {
  const lv = LEVEL_STYLE[liq.level_code] ?? LEVEL_STYLE.LOW
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <span className="text-sm font-semibold text-slate-200">Ликвидность</span>
        <span className={`px-1.5 py-0.5 rounded text-xs ${lv.cls}`}>{lv.label}</span>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-sm">
        <Cell label="Сделок" value={String(liq.deals)} />
        <Cell label="Продаж/день" value={liq.units_per_day.toFixed(1)} />
        <Cell label="Оборот/день" value={fmtPrice(liq.rub_per_day)} />
        <Cell label="Спред" value={liq.spread_pct != null ? `${liq.spread_pct.toFixed(1)}%` : '—'} />
        <Cell label="Активных лотов" value={String(liq.active_lots)} />
        <Cell label="Мин. лот" value={fmtPrice(liq.min_unit)} />
        <Cell label="Медиана продаж" value={fmtPrice(liq.median_sold)} />
        <Cell label="Разгрести стакан" value={liq.days_to_sell != null ? `${liq.days_to_sell.toFixed(1)} дн` : '—'} />
      </div>
    </div>
  )
}

function BestTimeBlock({ best }: { best: { by_hour: BestTimeBucket[]; by_weekday: BestTimeBucket[]; by_day: BestTimeBucket[]; overall_median: number } }) {
  return (
    <div className="space-y-3">
      <div className="text-sm font-semibold text-slate-200">Лучшее время</div>
      <BucketTable
        title="По часам"
        rows={best.by_hour.map(b => ({ key: `${b.hour ?? 0}:00`, ...b }))}
      />
      <BucketTable
        title="По дням недели"
        rows={best.by_weekday.map(b => ({ key: WEEKDAYS[b.weekday ?? 0] ?? String(b.weekday), ...b }))}
      />
      <DayHistogram rows={best.by_day} />
    </div>
  )
}

function BucketTable({ title, rows }: { title: string; rows: (BestTimeBucket & { key: string })[] }) {
  if (rows.length === 0) return null
  return (
    <div>
      <div className="text-xs text-slate-500 uppercase tracking-wider mb-1">{title}</div>
      <div className="rounded border border-slate-800 overflow-hidden">
        <table className="w-full text-xs">
          <thead className="bg-slate-900 text-slate-500">
            <tr>
              <th className="text-left px-2 py-1">Группа</th>
              <th className="text-right px-2 py-1">Медиана</th>
              <th className="text-right px-2 py-1">Δ</th>
              <th className="text-right px-2 py-1">N</th>
              <th className="text-left px-2 py-1"></th>
            </tr>
          </thead>
          <tbody>
            {rows.map(r => (
              <tr key={r.key} className="border-t border-slate-800">
                <td className="px-2 py-0.5 text-slate-300">{r.key}</td>
                <td className="px-2 py-0.5 text-right font-mono">{fmtPrice(r.median)}</td>
                <td className={`px-2 py-0.5 text-right font-mono ${(r.dev_pct ?? 0) > 0 ? 'text-rose-400' : 'text-emerald-400'}`}>
                  {r.dev_pct != null ? `${r.dev_pct > 0 ? '+' : ''}${r.dev_pct.toFixed(1)}%` : '—'}
                </td>
                <td className="px-2 py-0.5 text-right text-slate-500">{r.n}</td>
                <td className="px-2 py-0.5 text-slate-400">
                  {r.action === 'buy' && '← купить'}
                  {r.action === 'sell' && '← продать'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function DayHistogram({ rows }: { rows: BestTimeBucket[] }) {
  if (rows.length === 0) return null
  const max = Math.max(...rows.map(r => r.median), 1)
  return (
    <div>
      <div className="text-xs text-slate-500 uppercase tracking-wider mb-1">Тренд по дням</div>
      <div className="space-y-0.5 text-xs font-mono">
        {rows.map(r => {
          const width = Math.round((r.median / max) * 30)
          return (
            <div key={r.date} className="flex gap-2">
              <span className="w-20 text-slate-500 shrink-0">{r.date}</span>
              <span className="text-emerald-400">{'█'.repeat(Math.max(1, width))}</span>
              <span className="text-slate-400 ml-auto">{fmtPrice(r.median)}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function Cell({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md bg-slate-900/60 border border-slate-800 px-2 py-1.5">
      <div className="text-[10px] text-slate-500 uppercase tracking-wide">{label}</div>
      <div className="font-mono font-semibold text-slate-200">{value}</div>
    </div>
  )
}