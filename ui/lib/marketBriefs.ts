import api from './api'

export type BriefIndex = { brief_id: string; generated_at: string; report_window: string }
export type Citation = { provider: string; source_url: string; freshness: 'fresh' | 'stale' | 'unknown' }
export type BriefSection = { name: string; content: string[]; citations: Citation[] }
export type MarketBrief = { sections: BriefSection[]; warnings: string[]; generated_at: string }

export async function listMarketBriefs(): Promise<BriefIndex[]> {
  return (await api.get<{ briefs: BriefIndex[] }>('/api/v1/market-briefs')).data.briefs
}

export async function getMarketBrief(id: string): Promise<MarketBrief> {
  return (await api.get<{ brief: MarketBrief }>(`/api/v1/market-briefs/${encodeURIComponent(id)}`)).data.brief
}
