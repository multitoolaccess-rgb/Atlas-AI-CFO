import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import CategoryMovers from '../CategoryMovers';
import type { InsightItem } from '@/lib/api';

const mockInsights: InsightItem[] = [
  {
    type: 'warning',
    category: 'Dining',
    message: 'Dining spend up 45% vs last month',
    current: 450,
    previous: 310,
    change_pct: 45.2,
  },
  {
    type: 'success',
    category: 'Groceries',
    message: 'Groceries spend down 32% vs last month',
    current: 280,
    previous: 410,
    change_pct: -31.7,
  },
  {
    type: 'info',
    category: 'Subscriptions',
    message: 'Subscriptions: new spending this month ($45)',
    current: 45,
    previous: 0,
    change_pct: 100,
  },
];

describe('CategoryMovers', () => {
  it('renders loading skeleton when loading', () => {
    const { container } = render(<CategoryMovers insights={[]} loading />);
    expect(screen.getByText('Category Movers')).toBeDefined();
    expect(container.querySelectorAll('.skeleton').length).toBeGreaterThan(0);
  });

  it('renders empty state when no insights', () => {
    render(<CategoryMovers insights={[]} />);
    expect(screen.getByText('No significant category changes detected')).toBeDefined();
  });

  it('renders category names from insights', () => {
    render(<CategoryMovers insights={mockInsights} />);
    expect(screen.getByText('Dining')).toBeDefined();
    expect(screen.getByText('Groceries')).toBeDefined();
    expect(screen.getByText('Subscriptions')).toBeDefined();
  });

  it('renders change percentages', () => {
    render(<CategoryMovers insights={mockInsights} />);
    expect(screen.getByText(/45%/)).toBeDefined();
    expect(screen.getByText(/32%/)).toBeDefined();
  });

  it('has proper ARIA attributes', () => {
    render(<CategoryMovers insights={mockInsights} />);
    expect(screen.getByRole('list')).toBeDefined();
    expect(screen.getAllByRole('listitem').length).toBe(3);
  });

  it('limits display to 8 items', () => {
    const manyInsights: InsightItem[] = Array.from({ length: 12 }, (_, i) => ({
      type: 'warning' as const,
      category: `Category ${i}`,
      message: `Category ${i} changed`,
      current: 100 + i * 10,
      previous: 100,
      change_pct: i * 10,
    }));
    render(<CategoryMovers insights={manyInsights} />);
    expect(screen.getByText('Showing top 8 of 12 changes')).toBeDefined();
  });

  it('applies className prop', () => {
    const { container } = render(<CategoryMovers insights={[]} className="custom-class" />);
    expect(container.querySelector('.custom-class')).toBeDefined();
  });

  it('renders horizontal pill row strip when variant="strip"', () => {
    render(<CategoryMovers insights={mockInsights} variant="strip" />);
    // Strip variant exposes a stable test-id so page.tsx can locate it.
    expect(screen.getByTestId('category-movers-strip')).toBeDefined();
    // Pills are list items, but rendered horizontally (overflow-x-auto).
    const items = screen.getAllByRole('listitem');
    expect(items.length).toBe(3);
    // Each pill encodes the absolute % so a glanceable read works.
    expect(screen.getByText(/45%/)).toBeDefined();
    expect(screen.getByText(/32%/)).toBeDefined();
  });

  it('strip variant renders one asymmetric card (no nested cards)', () => {
    const { container } = render(<CategoryMovers insights={mockInsights} variant="strip" />);
    // One outer .card container; the strip variant never nests cards.
    const outerCards = container.querySelectorAll('[data-testid="category-movers-strip"]');
    expect(outerCards.length).toBe(1);
    // Inner pills are rounded-full spans — not nested card surfaces.
    const nestedCards = container.querySelectorAll(
      '[data-testid="category-movers-strip"] > .card',
    );
    expect(nestedCards.length).toBe(0);
  });
});
