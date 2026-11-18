import type {
  BatchReq, BatchResp, Category, HistoryReq, HistoryResp,
  Item, ItemDetails, ItemVariantsResp, MarketAnalysisResp,
  RecipeReq, RecipeResp,
} from '../types/api'

// Tauri предоставляет глобальный API только в desktop-сборке.
// В web-режиме запросы продолжают идти через HTTP API.
declare global {
  interface Window {
    __TAURI__?: {
      core?: {
        invoke?: (command: string, args?: Record<string, unknown>) => Promise<unknown>
      }
    }
  }
}

const RAW = import.meta.env.VITE_API_URL || '/api'
const BASE = RAW.endsWith('/') ? RAW.slice(0, -1) : RAW

function isDesktop(): boolean {
  return typeof window !== 'undefined' && typeof window.__TAURI__?.core?.invoke === 'function'
}

async function invokeDesktop<T>(command: string, args?: Record<string, unknown>): Promise<T> {
  const invoke = window.__TAURI__?.core?.invoke
  if (!invoke) throw new Error('Desktop IPC недоступен. Запустите приложение через Tauri.')
  return await invoke(command, args) as T
}

async function desktopRequest<T>(action: string, payload: Record<string, unknown> = {}): Promise<T> {
  return invokeDesktop<T>('desktop_request', { action, payload })
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let r: Response
  try {
    r = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    })
  } catch (e) {
    throw new Error(
      `Не удалось связаться с API по адресу ${BASE}. ` +
      `Проверьте, что backend запущен и доступен. ` +
      `(${(e as Error).message})`
    )
  }
  if (!r.ok) {
    let msg = `${r.status} ${r.statusText}`
    try {
      const j = await r.json()
      if (j?.error) msg = j.error
      else if (j?.detail) msg = j.detail
    } catch {}
    throw new Error(msg)
  }
  return r.json() as Promise<T>
}

export const api = {
  baseUrl: BASE,
  desktop: isDesktop(),

  health: () => isDesktop()
    ? desktopRequest<{ ok: boolean }>('health')
    : request<{ ok: boolean }>('/health'),

  items: (q?: string, craftable?: boolean) => {
    const params = new URLSearchParams()
    if (q) params.append('q', q)
    if (craftable) params.append('craftable', 'true')
    const qs = params.toString()
    return isDesktop()
      ? desktopRequest<Item[]>('items', { q, craftable })
      : request<Item[]>(`/items${qs ? `?${qs}` : ''}`)
  },

  categories: () => isDesktop()
    ? desktopRequest<Category[]>('categories')
    : request<Category[]>('/categories'),

  itemDetails: (itemId: string) => isDesktop()
    ? desktopRequest<ItemDetails>('item_details', { item_id: itemId })
    : request<ItemDetails>(`/item-details/${encodeURIComponent(itemId)}`),

  itemVariants: (itemId: string) => isDesktop()
    ? desktopRequest<ItemVariantsResp>('item_variants', { item_id: itemId })
    : request<ItemVariantsResp>(`/item-details/${encodeURIComponent(itemId)}/variants`),

  recipe: (body: RecipeReq) => isDesktop()
    ? desktopRequest<RecipeResp>('recipe', body as unknown as Record<string, unknown>)
    : request<RecipeResp>('/recipe', {
        method: 'POST',
        body: JSON.stringify(body),
      }),

  batch: (body: BatchReq) => isDesktop()
    ? desktopRequest<BatchResp>('batch', body as unknown as Record<string, unknown>)
    : request<BatchResp>('/batch', {
        method: 'POST',
        body: JSON.stringify(body),
      }),

  history: (body: HistoryReq) => isDesktop()
    ? desktopRequest<HistoryResp>('history', body as unknown as Record<string, unknown>)
    : request<HistoryResp>('/history', {
        method: 'POST',
        body: JSON.stringify(body),
      }),

  marketAnalysis: (itemId: string, days = 7) => isDesktop()
    ? desktopRequest<MarketAnalysisResp>('market_analysis', { item_id: itemId, days })
    : request<MarketAnalysisResp>(
        `/market-analysis/${encodeURIComponent(itemId)}?days=${days}`,
      ),

  character: (body: { name: string; region?: string }) =>
    isDesktop()
      ? invokeDesktop<Record<string, unknown>>('search_character', body)
      : request<Record<string, unknown>>('/character', {
          method: 'POST',
          body: JSON.stringify(body),
        }),

  statsMetadata: () =>
    isDesktop()
      ? invokeDesktop<Record<string, unknown>[]>('get_stats_metadata')
      : request<Record<string, unknown>[]>('/stats-metadata'),
}
