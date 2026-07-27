import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import AlertsPanel from '../AlertsPanel';
import type { AnomalyItem, UpcomingBillItem, InsightItem } from '@/lib/api';

const mockAnomalies: AnomalyItem[] = [
  {
    transaction_id: 1,
    merchant: 'STARBUCKS',
    amount: 85.5,
    median: 12.5,
    multiplier: 6.8,
    date: '2026-07-10',
  },
  {
    transaction_id: 2,
    merchant: 'AMAZON',
    amount: 450,
    median: 75,
    multiplier: 6.0,
    date: '2026-07-09',
  },
];

const mockBills: UpcomingBillItem[] = [
  {
    merchant: 'NETFLIX',
    median_amount: 15.99,
    median_interval_days: 30,
    last_date: '2026-07-01',
    predicted_next_date: '2026-07-31',
    confidence: 0.95,
    hit_count: 6,
  },
  {
    merchant: 'ELECTRIC CO',
    median_amount: 120,
    median_interval_days: 30,
    last_date: '2026-06-15',
    predicted_next_date: new Date(Date.now() + 3 * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
    confidence: 0.88,
    hit_count: 12,
  },
];

const mockWarnings: InsightItem[] = [
  {
    type: 'warning',
    category: 'Dining',
    message: 'Dining spend up 45% vs last month',
    current: 450,
    previous: 310,
    change_pct: 45.2,
  },
];

describe('AlertsPanel', () => {
  it('renders loading skeleton when loading', () => {
    const { container } = render(
      <AlertsPanel anomalies={[]} upcomingBills={[]} insights={[]} loading />,
    );
    expect(screen.getByText('Alerts & Insights')).toBeDefined();
    expect(container.querySelectorAll('.skeleton').length).toBeGreaterThan(0);
  });

  it('renders empty state when no alerts', () => {
    render(<AlertsPanel anomalies={[]} upcomingBills={[]} insights={[]} />);
    expect(screen.getByText('All clear')).toBeDefined();
    expect(screen.getByText('No unusual spending or upcoming bills detected')).toBeDefined();
  });

  it('renders anomaly merchant names', () => {
    render(
      <AlertsPanel anomalies={mockAnomalies} upcomingBills={[]} insights={[]} />,
    );
    expect(screen.getByText('STARBUCKS')).toBeDefined();
    expect(screen.getByText('AMAZON')).toBeDefined();
  });

  it('renders anomaly multiplier info', () => {
    render(
      <AlertsPanel anomalies={mockAnomalies} upcomingBills={[]} insights={[]} />,
    );
    expect(screen.getByText(/6\.8× the usual/)).toBeDefined();
  });

  it('renders upcoming bill merchant names', () => {
    render(
      <AlertsPanel anomalies={[]} upcomingBills={mockBills} insights={[]} />,
    );
    expect(screen.getByText('NETFLIX')).toBeDefined();
    expect(screen.getByText('ELECTRIC CO')).toBeDefined();
  });

  it('renders spending warnings from insights', () => {
    render(
      <AlertsPanel anomalies={[]} upcomingBills={[]} insights={mockWarnings} />,
    );
    expect(screen.getByText('Dining')).toBeDefined();
    expect(screen.getByText('Dining spend up 45% vs last month')).toBeDefined();
  });

  it('shows alert count badge', () => {
    render(
      <AlertsPanel
        anomalies={mockAnomalies}
        upcomingBills={mockBills}
        insights={[]}
      />,
    );
    // 2 anomalies + 2 bills = 4 alerts
    expect(screen.getByText('4')).toBeDefined();
  });

  it('has proper ARIA attributes', () => {
    render(
      <AlertsPanel
        anomalies={mockAnomalies}
        upcomingBills={mockBills}
        insights={[]}
      />,
    );
    expect(screen.getByRole('list')).toBeDefined();
    expect(screen.getAllByRole('listitem').length).toBeGreaterThan(0);
  });

  it('applies className prop', () => {
    const { container } = render(
      <AlertsPanel
        anomalies={[]}
        upcomingBills={[]}
        insights={[]}
        className="custom-class"
      />,
    );
    expect(container.querySelector('.custom-class')).toBeDefined();
  });
});
