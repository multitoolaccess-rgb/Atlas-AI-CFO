'use client'

import { useMemo } from 'react'
import ChartLine from '@/components/charts/ChartLine'
import { formatMonthLabel } from '@/lib/format'
import type { TrendDataPoint } from '@/lib/api'

interface SpendingTrendChartProps {
  data: TrendDataPoint[]
  className?: string
  height?: number
}

export default function SpendingTrendChart({
  data,
  className = '',
  height = 320,
}: SpendingTrendChartProps) {
  const chartData = useMemo(() => {
    return data.map((point) => ({
      month: formatMonthLabel(point.month),
      spend: Math.abs(point.spend),
      income: point.income,
      retained: point.retained,
    }))
  }, [data])

  return (
    <div className={`card p-6 ${className}`}>
      <h3 className="text-xs font-bold uppercase tracking-wider text-[var(--text-primary)] mb-4">
        6-Month Spending Trend
      </h3>
      <ChartLine
        data={chartData}
        xKey="month"
        series={[
          {
            key: 'income',
            name: 'Income',
            color: 'var(--success-500)',
          },
          {
            key: 'spend',
            name: 'Spending',
            color: 'var(--danger-500)',
          },
          {
            key: 'retained',
            name: 'Retained',
            color: 'var(--primary-500)',
            strokeDasharray: '5 5',
          },
        ]}
        height={height}
        currency
        showGrid
      />
    </div>
  )
}
