'use client';

import React from 'react';
import { Minus, TrendingUp, TrendingDown } from 'lucide-react';
import type { InsightItem } from '@/lib/api';
import { formatNumber } from '@/lib/format';

interface CategoryMoversProps {
 insights: InsightItem[];
 loading?: boolean;
 className?: string;
 /**
 * Phase 3 — the wide sentiment-strip variant renders an
 * asymmetric horizontal pill row (one card, scrollable on
 * mobile), breaking the identical-card-grid reflex the
 * vertical list was creating. Default behaviour preserved. */
 variant?: 'vertical' | 'strip';
}

export default function CategoryMovers({ insights, loading = false, className, variant = 'vertical' }: CategoryMoversProps) {
 if (loading) {
 return (
 <div className={`card ${variant === 'strip' ? 'p-5' : 'p-8'} ${className ?? ''}`} aria-busy="true">
 {variant === 'vertical' && (
 <h3 className="text-xl font-semibold text-primary mb-6">Category Movers</h3>
 )}
 <div className={variant === 'strip' ? 'flex gap-3 overflow-x-auto' : 'space-y-4'}>
 {[0, 1, 2, 3, 4].map((i) => (
 <div key={i} className={`skeleton ${variant === 'strip' ? 'h-16 w-44 flex-shrink-0 rounded-full' : 'h-12 w-full'}`} />
 ))}
 </div>
 </div>
 );
 }

 if (!insights || insights.length === 0) {
 return (
 <div className={`card ${variant === 'strip' ? 'p-5' : 'p-8'} ${className ?? ''}`}>
 <h3 className="text-xl font-semibold text-primary mb-4">Category Movers</h3>
 <div className="flex flex-col items-center justify-center h-32 text-secondary text-sm gap-2">
 <Minus className="w-8 h-8 text-tertiary" aria-hidden="true" />
 <p>No significant category changes detected</p>
 <p className="text-xs text-tertiary">Changes appear when spending shifts &gt;30% vs last month</p>
 </div>
 </div>
 );
 }

 // Show top 8 movers, sorted by absolute change
 const topMovers = insights.slice(0, 8);

 if (variant === 'strip') {
 /* Wide sentiment strip — one asymmetric card spanning 12 cols.
 Each pill encapsulates the category + delta + sign indicator
 (no nested cards per Maestro skill: nested cards are always
 wrong). On mobile, the strip overflows horizontally and the
 user swipes; on desktop all pills fit comfortably. */
 return (
 <div className={`card p-5 ${className ?? ''}`} data-testid="category-movers-strip">
 <div className="flex items-baseline gap-3 mb-3">
 <h3 className="text-base font-semibold text-primary">Category Movers</h3>
 <p className="text-xs text-tertiary">Biggest spending changes vs last month</p>
 </div>
 <div
 className="flex gap-3 overflow-x-auto pb-1"
 role="list"
 aria-label="Category spending changes"
 >
 {topMovers.map((insight) => {
 const isUp = insight.change_pct > 0;
 const absChange = Math.abs(insight.change_pct);
 const tone =
 insight.type === 'warning'
 ? 'border-[var(--danger-200)] bg-[color-mix(in_srgb,var(--danger-500)_8%,transparent)] text-[var(--danger-600)]'
 : insight.type === 'success'
 ? 'border-[var(--success-200)] bg-[color-mix(in_srgb,var(--success-500)_8%,transparent)] text-[var(--success-700)]'
 : /* WCAG AA: text-xs / font-mono on bg-primary card surface — info-600 is
 3.2:1 (passes AA-Large only). Bump to info-700 (#0e7490 ~4.8:1) so the
 strip pill text clears AA-Body at 14px semibold. */
 'border-[var(--info-200)] bg-[color-mix(in_srgb,var(--info-500)_8%,transparent)] text-[var(--info-700)]';
 return (
 <div
 key={insight.category}
 className={`flex-shrink-0 inline-flex items-center gap-2 px-3 py-2 rounded-full border ${tone} transition-colors duration-150 hover:brightness-110`}
 role="listitem"
 >
 {isUp ? (
 <TrendingUp className="w-3.5 h-3.5" aria-hidden="true" />
 ) : (
 <TrendingDown className="w-3.5 h-3.5" aria-hidden="true" />
 )}
 <span className="text-sm font-semibold text-primary">{insight.category}</span>
 <span className="font-mono text-xs tabular-nums">
 {isUp ? '↑' : '↓'} {absChange.toFixed(0)}%
 </span>
 </div>
 );
 })}
 </div>
 </div>
 );
 }

 return (
 <div className={`card p-8 ${className ?? ''}`}>
 <div className="flex-between mb-6">
 <div>
 <h3 className="text-xl font-semibold text-primary">Category Movers</h3>
 <p className="text-xs uppercase tracking-wider text-secondary mt-1">
 Biggest spending changes vs last month
 </p>
 </div>
 </div>

 <div className="space-y-3" role="list" aria-label="Category spending changes">
 {topMovers.map((insight) => {
 const isUp = insight.change_pct > 0;
 const absChange = Math.abs(insight.change_pct);
 const delta = insight.current - insight.previous;

 return (
 <div
 key={insight.category}
 className="flex items-center gap-4 p-3 rounded-xl hover:bg-slate-50/50 transition-colors duration-150"
 role="listitem"
 >
 {/* Category indicator */}
 <div
 className={`w-2 h-10 rounded-full flex-shrink-0 ${
 insight.type === 'warning'
 ? 'bg-[var(--danger-500)]'
 : insight.type === 'success'
 ? 'bg-[var(--success-500)]'
 : 'bg-[var(--info-500)]'
 }`}
 aria-hidden="true"
 />

 {/* Category info */}
 <div className="flex-1 min-w-0">
 <p className="text-sm font-semibold text-primary truncate">{insight.category}</p>
 <p className="text-xs text-secondary">
 {formatNumber(insight.current)} vs {formatNumber(insight.previous)}
 </p>
 </div>

 {/* Change indicator */}
 <div className="flex items-center gap-2 flex-shrink-0">
 <div className="text-right">
 <p
 className={`text-sm font-mono font-bold ${
 isUp ? 'text-[var(--danger-500)]' : 'text-[var(--success-600)]'
 }`}
 >
 {isUp ? '+' : '-'}{formatNumber(Math.abs(delta))}
 </p>
 <p
 className={`text-xs font-mono ${
 isUp ? 'text-[var(--danger-400)]' : 'text-[var(--success-500)]'
 }`}
 >
 {isUp ? '↑' : '↓'} {absChange.toFixed(0)}%
 </p>
 </div>
 {isUp ? (
 <TrendingUp className="w-4 h-4 text-[var(--danger-500)]" aria-hidden="true" />
 ) : (
 <TrendingDown className="w-4 h-4 text-[var(--success-500)]" aria-hidden="true" />
 )}
 </div>
 </div>
 );
 })}
 </div>

 {insights.length > 8 && (
 <p className="text-xs text-tertiary text-center mt-4">
 Showing top 8 of {insights.length} changes
 </p>
 )}
 </div>
 );
}
