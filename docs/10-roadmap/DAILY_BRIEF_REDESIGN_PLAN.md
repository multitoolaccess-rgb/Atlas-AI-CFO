# Daily Investment Brief Redesign Plan

**Status:** Plan Mode  
**Requested By:** User (Atlas AI CFO owner)  
**Goal:** Redesign Daily Investment Brief with Robinhood/Fidelity/Bloomberg-style UI  

---

## Problem Statement

### Current Issues

1. **Too Much Data** - 10 sections dumped on one page with overwhelming detail
2. **Rate Limit Errors** - Finnhub free tier (~48 calls/min) exceeded with just 5+ holdings
3. **Poor Organization** - All data equally prominent, no hierarchy
4. **Not Actionable** - Users can't quickly see what's important
5. **Visual Clutter** - Text-heavy, no visual hierarchy, Bloomberg terminal vibes missing

### User Requirements

1. **Show Portfolio Changes/Updates** - What moved, how much, why
2. **Show News** - Material news only, not every headline
3. **Robinhood/Fidelity Style** - Clean, visual, scannable
4. **Bloomberg Style** - Professional, data-rich but organized
5. **No Rate Limits** - Must work reliably with free-tier providers
6. **Materiality Focus** - Only show what's important

---

## Design Inspiration

### Robinhood App (Consumer)
- **Hero:** Today's portfolio change (green/red, big number)
- **News:** 3-5 most important stories with thumbnails
- **Visual:** Cards, color-coded, minimal text
- **Navigation:** Swipeable sections

### Fidelity (Professional Consumer)
- **Hero:** Day's gain/loss with YTD context
- **News:** Categorized (earnings, upgrades/downgrades, insider)
- **Research:** Analyst ratings, price targets
- **Visual:** Clean tables, summary boxes

### Bloomberg Terminal (Professional)
- **Hero:** Real-time portfolio P&L
- **News:** Ticker-specific, rank by materiality
- **Alerts:** What's moving, what's material
- **Visual:** Dense but organized, keyboard-friendly

### Our Target: "Atlas Daily Brief"
Best of all three:
- **Hero:** Today's net change + key movers
- **Visual:** Color-coded cards, icons, minimal text
- **News:** Top 3-5 stories with why they matter
- **Structure:** Scannable sections, drill-down for details
- **Performance:** Cached, rate-limit resistant

---

## Proposed Architecture

### Frontend Architecture

```
ui/app/investments/brief/
├── page.tsx                    # Main brief page (Hero + sections)
├── components/
│   ├── BriefHero.tsx           # Today's net change, top movers
│   ├── MarketPulse.tsx         # Market overview (SPY, QQQ, etc.)
│   ├── PortfolioChanges.tsx    # Holdings with significant changes
│   ├── TopNews.tsx             # 3-5 material news stories
│   ├── EarningsCalendar.tsx    # Upcoming earnings this week
│   ├── WatchlistAlerts.tsx     # Price alerts, target breaches
│   └── QuickActions.tsx        # Add to watchlist, research more
├── hooks/
│   ├── useBriefData.ts         # Cached data fetching
│   └── useBriefConfig.ts       # User preferences
└── types/
    └── brief.ts                # Brief data types
```

### Backend Architecture

```
services/rules-service/app/routes/investment_brief.py
├── GET /api/v1/investments/brief/summary    # Lightweight, cached
├── GET /api/v1/investments/brief/news       # News only
├── GET /api/v1/investments/brief/earnings   # Earnings this week
└── POST /api/v1/investments/brief/refresh   # Force refresh
```

### New Data Pipeline

1. **Pre-compute nightly** - Generate brief once per day at 6 AM
2. **Aggressive caching** - 24-hour cache, invalidate on new data
3. **Rate-limit budgeting** - Max 10 calls per brief generation
4. **Prioritization** - Quote → News → Earnings (skip enrichment)
5. **Fallback to cached** - Serve stale brief rather than error

---

## UI Design

### Page Layout (Mobile-First, Desktop Expanded)

```
┌─────────────────────────────────────────────────────────────┐
│  ATLAS AI CFO          Search...           Settings  Profile │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  TODAY'S BRIEF                                        │    │
│  │  +$2,847.32 (+1.24%)                                 │    │
│  │  SPY ▲ 0.89%  •  QQQ ▲ 1.12%  •  VTI ▲ 0.67%         │    │
│  │  Last updated: 6:00 AM EST                           │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌──────────────────┐  ┌──────────────────┐                 │
│  │ TOP MOVERS       │  │ YOUR NEWS        │                 │
│  │                  │  │                  │                 │
│  │ NVDA  ▲ 4.2%     │  │ AAPL Earnings    │                 │
│  │ MSFT  ▲ 2.1%     │  │ Tomorrow 5pm ET  │                 │
│  │ GOOGL ▲ 1.8%     │  │ Est. $1.25/sh    │                 │
│  │ TSLA  ▼ 2.3%     │  │                  │                 │
│  │ META  ▼ 1.5%     │  │ INTC Upgrade     │                 │
│  │                  │  │ Buy: MS  (prev   │                 │
│  │ [View All →]     │  │ Sell)            │                 │
│  └──────────────────┘  │                  │                 │
│                        │  [2 more stories]│                 │
│                        └──────────────────┘                 │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  EARNINGS THIS WEEK                                   │    │
│  │                                                      │    │
│  │  TOMORROW   AAPL  EPS: $1.25  ━━━━●━━━━  High chance │    │
│  │  TOMORROW   MSFT  EPS: $2.10  ━●━━━━━●━━  Med chance  │    │
│  │  WED      GOOGL  EPS: $1.85   ●━━━━━━━●━  Low chance  │    │
│  │  FRI       NVDA  EPS: $0.95   ●●●●━━━━━━  Whisper     │    │
│  │                                                      │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  WATCHLIST ALERTS                                     │    │
│  │                                                      │    │
│  │  🔔 NVDA hit $150 price target                        │    │
│  │  🔔 AAPL crossed 50-day moving average                │    │
│  │  🔔 MSFT earnings tomorrow                            │    │
│  │  🔔 GOOGL volume spike (2x avg)                       │    │
│  │                                                      │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Component Specifications

#### 1. BriefHero (Hero Section)
- **Data:** Today's P&L, YTD return, day change
- **Visual:** Large green/red number, percentage
- **Context:** Market context (SPY/QQQ performance)
- **Cache:** 24 hours, updated 6 AM EST

#### 2. MarketPulse (Market Overview)
- **Data:** SPY, QQQ, VTI daily change
- **Visual:** Small ticker cards with percentage
- **Source:** Single API call (free, no rate limit)

#### 3. PortfolioChanges (Top Movers)
- **Data:** Top 5 gainers, top 5 losers (by % and $)
- **Visual:** Card per holding with change
- **Interactions:** Tap for details, long-press for actions
- **Limit:** 10 holdings total displayed

#### 4. TopNews (Material News)
- **Data:** 3-5 most material stories
- **Visual:** Card with headline, source, relevance score
- **Content:** Why it matters (1-line summary)
- **Ranking:** By holding materiality + news recency

#### 5. EarningsCalendar (This Week)
- **Data:** Holdings with earnings in next 7 days
- **Visual:** Timeline view with confidence indicator
- **Fields:** Date, Symbol, EPS estimate, whisper vs consensus
- **Limit:** 5 upcoming earnings

#### 6. WatchlistAlerts (Action Items)
- **Data:** Price targets hit, moving average crossovers, volume spikes
- **Visual:** Notification-style cards with icons
- **Priority:** Critical → High → Medium
- **Limit:** 5 active alerts

---

## API Redesign

### New Endpoints

```python
@router.get("/investments/brief/summary")
async def get_brief_summary(
    user_id: int = Depends(require_user),
) -> BriefSummary:
    """
    Lightweight brief summary - 1 API call, 24-hour cache.
    
    Returns:
    - Today's P&L
    - Top 3 gainers/losers
    - Market context (SPY/QQQ)
    - Last updated timestamp
    """
```

```python
@router.get("/investments/brief/news")
async def get_brief_news(
    limit: int = Query(default=5, le=10),
    user_id: int = Depends(require_user),
) -> List[NewsItem]:
    """
    Material news only - 1 API call per symbol, cached 4 hours.
    
    Returns:
    - Top 3-5 news stories ranked by materiality
    - Why it matters (1-line)
    - Source and timestamp
    """
```

```python
@router.get("/investments/brief/earnings")
async def get_brief_earnings(
    days: int = Query(default=7, le=14),
    user_id: int = Depends(require_user),
) -> List[EarningsEvent]:
    """
    Upcoming earnings - cached 1 hour.
    
    Returns:
    - Holdings with earnings in next N days
    - Date, EPS estimate, whisper vs consensus
    - Probability indicator (high/med/low)
    """
```

### Rate Limit Budget

| Operation | Calls | Cache TTL | Priority |
|-----------|-------|-----------|----------|
| Quote (portfolio) | 1 | 5 min | Required |
| Quote (market) | 1 | 5 min | Required |
| News (top 3) | 3 | 4 hours | High |
| Earnings | 5 | 1 hour | Medium |
| SEC Filings | 5 | 24 hours | Low |
| Profile/Analyst | 0 | - | **Removed** |

**Total: 15 calls max per brief** (vs 45+ before)

---

## Data Flow

### Request Flow

```
User opens Brief Page
         │
         ▼
┌─────────────────────┐
│ GET /summary        │  ← 1 call (cached 24h)
│ • Today's P&L       │
│ • Top movers        │
│ • Market context    │
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│ GET /news (limit=5) │  ← 1 call (cached 4h)
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│ GET /earnings (7d)  │  ← 1 call (cached 1h)
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│ Return cached       │  ← Serve from cache if rate limited
│ alerts/watchlist    │
└─────────────────────┘
```

### Cache Strategy

```python
# Cache TTLs (aggressive to avoid rate limits)
BRIEF_SUMMARY_CACHE = 24 * 60 * 60      # 24 hours
BRIEF_NEWS_CACHE = 4 * 60 * 60          # 4 hours  
BRIEF_EARNINGS_CACHE = 60 * 60          # 1 hour
BRIEF_QUOTE_CACHE = 5 * 60              # 5 minutes

# Stale-while-revalidate
# Serve stale data immediately, refresh in background
```

---

## Implementation Plan

### Phase 1: Foundation (Week 1)

**Backend:**
- [ ] Create new `/brief/summary` endpoint
- [ ] Implement 24-hour caching
- [ ] Rate-limit budget to 15 calls max
- [ ] Remove enrichment pass (analyst targets, dividends)

**Frontend:**
- [ ] Create BriefHero component
- [ ] Create BriefSummary type
- [ ] Connect to new API
- [ ] Implement loading states

**Deliverable:** Simple hero with P&L and top movers

### Phase 2: Core Features (Week 2)

**Backend:**
- [ ] Create `/brief/news` endpoint
- [ ] Implement news ranking by materiality
- [ ] Add "why it matters" field

**Frontend:**
- [ ] Create TopNews component
- [ ] Create MarketPulse component
- [ ] Implement news card UI

**Deliverable:** Hero + News + Market context

### Phase 3: Completeness (Week 3)

**Backend:**
- [ ] Create `/brief/earnings` endpoint
- [ ] Add earnings probability calculation
- [ ] Create `/brief/alerts` endpoint

**Frontend:**
- [ ] Create EarningsCalendar component
- [ ] Create WatchlistAlerts component
- [ ] Add pull-to-refresh

**Deliverable:** Complete brief with all sections

### Phase 4: Polish (Week 4)

**Frontend:**
- [ ] Add animations (Framer Motion)
- [ ] Implement skeleton loading states
- [ ] Add keyboard shortcuts
- [ ] Mobile responsiveness refinement
- [ ] Accessibility (ARIA, focus states)

**Backend:**
- [ ] Add background refresh (6 AM EST)
- [ ] Implement stale-while-revalidate
- [ ] Add error boundaries

**Deliverable:** Production-ready, polished brief

---

## Migration Strategy

### Backward Compatibility

1. **Old endpoint** (`/api/v1/market-briefs/generate`) stays for 90 days
2. **New endpoints** (`/api/v1/investments/brief/*`) are additive
3. **Gradual rollout:** New users get new brief, existing users can opt-in

### Data Migration

- Existing briefs cached for 7 days
- New brief structure doesn't affect stored data
- No database schema changes needed

---

## Error Handling

### Rate Limit Fallback

```python
async def get_brief_summary(user_id: int) -> BriefSummary:
    try:
        return await compute_brief_summary(user_id)
    except RateLimitExceeded:
        # Serve cached brief or minimal fallback
        cached = await get_cached_brief(user_id)
        if cached:
            return cached.with_warning("Showing cached data - live data rate limited")
        return BriefSummary.zero_with_warning()
```

### Graceful Degradation

| Scenario | Behavior |
|----------|----------|
| Rate limited | Serve cached, show warning banner |
| API timeout (5s) | Skip non-critical sections |
| No holdings | Show empty state with CTA |
| Market closed | Show last close data |

---

## Success Metrics

### Performance
- [ ] Page load < 500ms (cached)
- [ ] Time to interactive < 1s
- [ ] Zero rate limit errors in 30 days

### Engagement
- [ ] Open daily brief > 3x/week
- [ ] Click-through on news stories > 50%
- [ ] Action taken on alerts > 20%

### Quality
- [ ] User satisfaction > 4/5
- [ ] "Too much data" complaints = 0
- [ ] "Rate limit errors" = 0

---

## Files to Create/Modify

### New Files

```
ui/app/investments/brief/
├── components/
│   ├── BriefHero.tsx           # NEW
│   ├── MarketPulse.tsx         # NEW
│   ├── PortfolioChanges.tsx    # NEW
│   ├── TopNews.tsx             # NEW
│   ├── EarningsCalendar.tsx    # NEW
│   └── WatchlistAlerts.tsx     # NEW
├── hooks/
│   ├── useBriefSummary.ts      # NEW
│   ├── useBriefNews.ts         # NEW
│   └── useBriefEarnings.ts     # NEW
├── page.tsx                    # MODIFY (redesign)
└── types/
    └── brief.ts                # NEW

services/rules-service/app/routes/
├── investment_brief.py         # NEW (lightweight endpoints)
└── market_briefs.py            # MODIFY (keep legacy for migration)

services/rules-service/app/market_intelligence/
├── brief_composer.py           # NEW (lightweight composer)
├── brief_ranker.py             # NEW (news ranking)
└── brief_cache.py              # NEW (aggressive caching)
```

### Deprecated Files (After 90-day migration)

```
services/rules-service/app/routes/
├── market_briefs.py            # Keep for migration, deprecate later

services/rules-service/app/market_intelligence/
├── composition.py              # Keep but not used by new brief
├── briefing.py                 # Keep but not used by new brief
├── adapters.py                 # Keep, still used by other features
└── contracts.py                # Keep, type definitions
```

---

## Testing Strategy

### Unit Tests
```python
test_brief_summary_calculates_pnl()
test_brief_news_ranks_by_materiality()
test_brief_earnings_sorts_by_date()
test_rate_limit_budget_enforcement()
test_cache_ttl_respected()
test_graceful_degradation_on_rate_limit()
```

### Integration Tests
```python
test_brief_page_loads_under_500ms()
test_brief_displays_all_sections()
test_pull_to_refresh_updates_data()
test_error_banner_shown_on_rate_limit()
test_mobile_layout_responsive()
```

### E2E Tests
```python
test_user_opens_brief_sees_hero()
test_user_clicks_news_story_opens_detail()
test_user_pulls_to_refresh()
test_user_on_mobile_sees_stacked_layout()
```

---

## Rollout Plan

### Week 1-2: Backend
1. Create new lightweight endpoints
2. Implement aggressive caching
3. Test rate limit budget enforcement
4. Deploy to staging

### Week 3: Frontend MVP
1. Create BriefHero + summary display
2. Connect to new API
3. Deploy to staging

### Week 4: Full Feature
1. Add news, earnings, alerts
2. Implement all UI components
3. Performance optimization
4. Deploy to production (opt-in)

### Week 5-6: Polish & Migration
1. Add animations, skeleton states
2. Accessibility audit
3. Migrate all users to new brief
4. Deprecate old endpoints

---

## Summary

### What Changes

| Aspect | Current | New |
|--------|---------|-----|
| Data Volume | 10 sections, all data | 5 sections, material only |
| Organization | Flat, text-heavy | Hierarchical, visual cards |
| Rate Limits | 45+ calls, frequent errors | 15 calls, 0 errors |
| Caching | 5-15 min TTL | 1-24 hour TTL |
| UX | Bloomberg terminal | Robinhood app |
| Updates | On-demand, slow | Pre-computed, fast |

### Benefits

✅ **No more rate limit errors** (aggressive caching + budget)  
✅ **Clean, scannable UI** (Robinhood/Fidelity style)  
✅ **Material information only** (ranked by importance)  
✅ **Fast page loads** (pre-computed, cached)  
✅ **Mobile-friendly** (card-based, responsive)  
✅ **Professional** (Bloomberg-inspired data density)  

### Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Data freshness | Background refresh at 6 AM EST |
| Missing data | Serve cached with warning banner |
| Migration complexity | 90-day overlap period |
| Performance | Aggressive caching, CDN |

---

**Plan Status:** Ready for Approval  
**Estimated Duration:** 6 weeks  
**Team Size:** 1 developer (existing)  
**Dependencies:** None (uses existing Finnhub)  

---

## Next Steps

1. **Approve this plan** → Begin Phase 1 implementation
2. **Review UI mocks** → Refine visual design
3. **Set up tracking** → Monitor rate limits and errors
4. **Define success metrics** → Establish baselines

**Ready to proceed with implementation?**