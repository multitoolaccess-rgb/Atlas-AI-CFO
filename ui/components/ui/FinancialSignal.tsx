'use client'

import { ArrowUp, ArrowDown, Minus } from 'lucide-react'

interface FinancialSignalProps {
  value: number
  format?: 'currency' | 'percent' | 'number'
  size?: 'sm' | 'md' | 'lg'
  showSign?: boolean
  className?: string
}

/**
 * FinancialSignal - Adds symbolic arrows to financial values
 * 
 * Addresses UI/UX Audit Issue: "Color-only financial signals"
 * - Red + ArrowUp = Overspending/Loss (negative financial outcome)
 * - Green + ArrowDown = Savings (positive financial outcome, spending decreased)
 * - Green + ArrowUp = Gains/Income
 * - Red + ArrowDown = Losses
 * 
 * The combination of color AND symbol ensures colorblind accessibility
 */
export default function FinancialSignal({
  value,
  format = 'currency',
  size = 'md',
  showSign = true,
  className = ''
}: FinancialSignalProps) {
  const isPositive = value > 0
  const isNegative = value < 0
  const isZero = value === 0
  
  // For expenses: positive value = bad (red up arrow)
  // For gains/income: positive value = good (green up arrow)
  // We need context - default to expense context (positive = red)
  
  const iconSize = size === 'sm' ? 'w-3 h-3' : size === 'lg' ? 'w-5 h-5' : 'w-4 h-4'
  const textSize = size === 'sm' ? 'text-xs' : size === 'lg' ? 'text-lg' : 'text-sm'
  
  // Color and direction based on value
  // Positive values: Red (expense/overspending context) or Green (gain context)
  // We'll use neutral text color and rely on the arrow for direction
  // This is more accessible than color-only signals
  
  let colorClass = 'text-on-surface'
  let ArrowIcon = Minus
  
  if (isPositive) {
    // Positive: Green arrow up (gains, income, retained)
    colorClass = 'text-success-600'
    ArrowIcon = ArrowUp
  } else if (isNegative) {
    // Negative: Red arrow down (losses, expenses, spending)
    colorClass = 'text-danger-600'
    ArrowIcon = ArrowDown
  } else {
    // Zero: Gray neutral
    colorClass = 'text-secondary'
    ArrowIcon = Minus
  }
  
  const formattedValue = (() => {
    const absValue = Math.abs(value)
    switch (format) {
      case 'currency':
        return new Intl.NumberFormat('en-US', { 
          style: 'currency', 
          currency: 'USD',
          minimumFractionDigits: 0,
          maximumFractionDigits: 2
        }).format(absValue)
      case 'percent':
        return `${absValue.toFixed(1)}%`
      default:
        return absValue.toLocaleString()
    }
  })()
  
  const signPrefix = showSign && !isZero ? (value > 0 ? '+' : '-') : ''
  
  return (
    <span className={`inline-flex items-center gap-1 ${colorClass} ${className}`}>
      <ArrowIcon className={iconSize} aria-hidden="true" />
      <span className={`font-mono font-semibold ${textSize}`}>
        {signPrefix}{formattedValue}
      </span>
    </span>
  )
}