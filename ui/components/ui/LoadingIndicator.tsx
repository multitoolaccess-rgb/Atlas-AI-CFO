'use client'

import { Loader2, RefreshCw, Loader } from 'lucide-react'

interface LoadingIndicatorProps {
  type: 'initial' | 'refresh' | 'action'
  size?: 'sm' | 'md' | 'lg'
  message?: string
  showIcon?: boolean
}

/**
 * Standardized loading indicators to distinguish between:
 * - Initial load (full page skeleton/spinner)
 * - Refresh (small spinner with "Refreshing..." label)
 * - Action (button loading state)
 * 
 * Addresses UI/UX Audit Issue: "Loading states don't distinguish initial load from refresh"
 */
export default function LoadingIndicator({
  type = 'initial',
  size = 'md',
  message,
  showIcon = true
}: LoadingIndicatorProps) {
  const iconSize = size === 'sm' ? 'w-4 h-4' : size === 'lg' ? 'w-8 h-8' : 'w-6 h-6'
  const textSize = size === 'sm' ? 'text-xs' : size === 'lg' ? 'text-lg' : 'text-sm'
  
  let Icon = Loader2
  let defaultMessage = ''
  
  switch (type) {
    case 'initial':
      Icon = Loader2
      defaultMessage = 'Loading...'
      break
    case 'refresh':
      Icon = RefreshCw
      defaultMessage = 'Refreshing...'
      break
    case 'action':
      Icon = Loader
      defaultMessage = 'Processing...'
      break
  }
  
  return (
    <div className={`flex items-center gap-2 ${type === 'initial' ? 'p-8 justify-center' : ''}`}>
      {showIcon && (
        <Icon className={`animate-spin ${iconSize} ${type === 'refresh' ? 'opacity-60' : ''}`} />
      )}
      <span className={`${textSize} ${type === 'refresh' ? 'opacity-70' : ''}`}>
        {message || defaultMessage}
      </span>
    </div>
  )
}
