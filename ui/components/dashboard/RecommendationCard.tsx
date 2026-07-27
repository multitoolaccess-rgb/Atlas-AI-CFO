'use client';

import React, { useState } from 'react';
import { Sparkles, X, ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui';

interface RecommendationCardProps {
 title: string;
 description: string;
 impact?: string;
 priority?: 'high' | 'medium' | 'low';
 onApprove?: () => void;
 onDeny?: () => void;
 onViewDetails?: () => void;
}

interface PriorityStyle {
 border: string;
 bg: string;
 badge: string;
 badgeBg: string;
 badgeText: string;
}

const priorityStyles: Record<NonNullable<RecommendationCardProps['priority']>, PriorityStyle> = {
 high: {
 border: 'border-danger-200',
 bg: 'bg-danger-50',
 badge: 'badge-danger',
 badgeBg: 'bg-danger-100',
 badgeText: 'text-danger-700',
 },
 medium: {
 border: 'border-warning-200',
 bg: 'bg-warning-50',
 badge: 'badge-warning',
 badgeBg: 'bg-warning-100',
 badgeText: 'text-warning-700',
 },
 low: {
 border: 'border-info-200',
 bg: 'bg-info-50',
 badge: 'badge-neutral',
 badgeBg: 'bg-slate-100',
 badgeText: 'text-slate-700',
 },
};

const RecommendationCard: React.FC<RecommendationCardProps> = ({
 title,
 description,
 impact,
 priority = 'medium',
 onApprove,
 onDeny,
 onViewDetails,
}) => {
 const [dismissed, setDismissed] = useState(false);

 if (dismissed) return null;

 const style = priorityStyles[priority];

 return (
 <div
 className={`card p-6 border-2 ${style.bg} ${style.border} animate-slideUp`}
 role="article"
 aria-label={`Recommendation: ${title}`}
 >
 {/* Header with title and dismiss */}
 <div className="flex-between mb-4">
 <div className="flex items-center gap-3">
 <Sparkles className="w-5 h-5 text-primary-500" aria-hidden="true" />
 <div>
 <div className="text-xs font-bold uppercase tracking-wider text-primary-500">
 AI Insight
 </div>
 <h3 className="text-xl font-semibold text-primary mt-1">{title}</h3>
 </div>
 </div>
 <Button
 variant="tertiary"
 size="sm"
 className="p-1 hover:bg-black/5 rounded-md focus-ring"
 onClick={() => setDismissed(true)}
 ariaLabel="Dismiss recommendation"
 >
 <X className="w-4 h-4" aria-hidden="true" />
 </Button>
 </div>

 {/* Description */}
 <p className="text-base text-secondary mb-4 leading-relaxed">{description}</p>

 {/* Impact if provided */}
 {impact && (
 <div className="bg-white/60 px-4 py-3 rounded-lg mb-4 border border-border-subtle">
 <p className="text-xs font-bold uppercase tracking-wider text-tertiary mb-1">
 Potential Impact
 </p>
 <p className="text-sm text-primary font-semibold">{impact}</p>
 </div>
 )}

 {/* Actions */} <div className="flex gap-3 pt-4 border-t border-border-subtle">
 {onApprove && (
 <Button
 variant="primary"
 size="md"
 className="flex-1"
 onClick={onApprove}
 icon={<ArrowRight className="w-4 h-4" />}
 iconPosition="right"
 >
 Approve
 </Button>
 )}
 {onViewDetails && (
 <Button
 variant="tertiary"
 size="md"
 className="flex-1"
 onClick={onViewDetails}
 >
 View Details
 </Button>
 )}
 {onDeny && (
 <Button
 variant="tertiary"
 size="sm"
 className="px-3"
 onClick={onDeny}
 ariaLabel="Deny recommendation"
 >
 <X className="w-4 h-4" aria-hidden="true" />
 </Button>
 )}
 </div>
 </div>
 );
};

export default RecommendationCard;
