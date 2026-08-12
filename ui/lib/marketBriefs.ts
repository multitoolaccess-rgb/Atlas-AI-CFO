import api from './api'

export type BriefIndex = { brief_id: string; generated_at: string; report_window: string }
export type Citation = { provider: string; source_url: string; freshness: 'fresh' | 'stale' | 'unknown' }
export type BriefSection = { name: string; content: string[]; citations: Citation[] }
export type ActionToReview = { action: string; why: string; goal_linkage: string; evidence: string[]; expected_impact: string; risks: string[]; alternatives: string[]; confidence: 'low' | 'medium' | 'high'; approval_requirement: string }
export type MarketBrief = { sections: BriefSection[]; warnings: string[]; generated_at: string; actions?: ActionToReview[] }

export async function listMarketBriefs(): Promise<BriefIndex[]> {
  return (await api.get<{ briefs: BriefIndex[] }>('/api/v1/market-briefs')).data.briefs
}

export async function getMarketBrief(id: string): Promise<MarketBrief> {
  return (await api.get<{ brief: MarketBrief }>(`/api/v1/market-briefs/${encodeURIComponent(id)}`)).data.brief
}

/** Sends only the bounded report-window control; financial facts remain server-owned. */
export async function generateMarketBrief(): Promise<{ brief_id: string; replayed: boolean; brief: MarketBrief }> {
  return (await api.post<{ brief_id: string; replayed: boolean; brief: MarketBrief }>('/api/v1/market-briefs/generate', { report_window: 'latest' })).data
}
