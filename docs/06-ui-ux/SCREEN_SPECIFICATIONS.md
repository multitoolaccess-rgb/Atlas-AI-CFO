# Screen Specifications

## Mission Control

Goal status, forecast delta, priority actions, risks, opportunities, and freshness.

## Goal Detail

Target, probability range, trajectory, drivers, funding, linked decisions, and scenarios.

## Recommendation Detail

Action, rationale, evidence, impact, risks, alternatives, confidence, and decision controls.

## Simulation Lab

Baseline, editable assumptions, comparison, distributions, sensitivities, and save-to-decision.

## Decision Journal

Question, options, recommendation, user choice, execution, outcome, and lessons.

## Data & Permissions

Connections, sync status, ownership, sharing, automation policies, and audit events.

## Market Intelligence — reliability correction design specification

**Scene and direction.** A portfolio owner reviews a trustworthy intelligence
brief at a desk before the US session or after the close. The page uses Atlas's
existing cool-space light/dark tokens, restrained semantic status color, Space
Grotesk for interface text, and JetBrains Mono/tabular numerals for financial
values. It is editorial and evidence-first rather than a decorative dashboard.

**Information architecture and hierarchy.** The page is a semantic `main` with
(1) a compact header containing “Market Intelligence”, description, last
generated time, provider readiness, market-data basis, freshness, and the
primary Generate brief action; (2) an evidence-backed executive summary strip;
(3) a responsive detail surface with the brief sections on the left and a
keyboard-operable archive panel on the right on wide screens; and (4) explicit
coverage/data-quality limitations and review-only action cards. The section
order is portfolio changes, material news, upcoming/recent earnings, SEC
filings, actions to review, and data-quality limitations. Empty sections state
why no evidence is present instead of disappearing without explanation.

**Component hierarchy and reuse.** `MarketBriefArchive` owns loading,
generation, selection, race-safe detail requests, and sanitized error states.
It reuses `Button`, `Badge`, `Card`, Atlas semantic tokens, `focus-visible`
utilities, Lucide icons, existing typography utilities, and the global reduced-
motion override. Archive entries are real buttons with `aria-current`; source
citations are labeled links with provider and observed/retrieved dates.

**Responsive behavior.** At mobile widths the archive becomes a full-width
“Saved briefs” section above the selected detail, with 44px-or-larger controls
and no horizontal scrolling. At tablet widths the summary wraps and detail
sections remain single-column. At desktop widths the page uses a bounded
content grid with a sticky archive panel and a readable detail column; long
headlines and warning text wrap rather than truncate critical meaning.

**State matrix.** The UI distinguishes initial loading skeletons, empty archive,
generating, successful generation, idempotent replay, prior-close mode, partial
coverage, missing configuration, authentication failure, rate limiting, network
unavailable, unsupported holdings, insufficient coverage, and detail-unavailable
states. Every operational error maps from the stable backend reason code to a
safe title, recovery instruction, and retry affordance; raw response text is
never rendered.

**Accessibility.** The page has one h1 and ordered section headings, semantic
landmarks, `role=status` announcements for loading/success and `role=alert`
for failures, visible keyboard focus, non-color status labels, reduced-motion
support, meaningful button/link names, accessible freshness and citation text,
and keyboard archive navigation. Visual checks include axe on the synthetic
brief journey at mobile, tablet, and desktop widths plus light/dark smoke
coverage.

**Skill-driven decisions.** `ui-ux-pro-max` guidance shaped the restrained
semantic palette, evidence-first dashboard hierarchy, 44px touch targets,
responsive archive/detail structure, visible focus, skeleton loading, and
reduced-motion requirements. Its executable `search.py` was unavailable in
this environment, so no generated palette or persisted skill artifact was
used. `impeccable` context, product register, detector, shape, and polish
references shaped the existing-token reuse, state completeness, typography,
spacing, motion restraint, and anti-slop review. `tasteskill` was not installed
and was not installed or modified.

**Rejected alternatives.** A decorative chart-first dashboard was rejected
because the current contract has no safe time series; a dense archive table
was rejected for mobile and keyboard clarity; client-side provider/status
inference was rejected because the server owns freshness and coverage; and
large gradients, glass effects, and generic repeated metric cards were rejected
in favor of Atlas's existing semantic surfaces and evidence hierarchy.
