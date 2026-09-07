'use client'

import { usePathname } from 'next/navigation'
import Link from 'next/link'
import { ChevronRight, Home } from 'lucide-react'

interface BreadcrumbsProps {
  extraCrumbs?: { label: string; href?: string }[]
}

export default function Breadcrumbs({ extraCrumbs = [] }: BreadcrumbsProps) {
  const pathname = usePathname()
  
  // Skip for root
  if (pathname === '/') return null

  const pathSegments = pathname.split('/').filter(Boolean)
  
  const crumbs = pathSegments.map((segment, index) => {
    const href = '/' + pathSegments.slice(0, index + 1).join('/')
    const label = segment.charAt(0).toUpperCase() + segment.slice(1).replace(/-/g, ' ')
    return { label, href }
  })

  return (
    <nav className="flex items-center text-sm text-secondary mb-6" aria-label="Breadcrumb">
      <Link href="/" className="hover:text-primary transition-colors flex items-center">
        <Home className="w-4 h-4" />
      </Link>
      
      {crumbs.map((crumb, i) => (
        <span key={crumb.href} className="flex items-center">
          <ChevronRight className="w-4 h-4 mx-2 opacity-50" />
          {i === crumbs.length - 1 ? (
            <span className="font-medium text-primary">{crumb.label}</span>
          ) : (
            <Link href={crumb.href} className="hover:text-primary transition-colors">
              {crumb.label}
            </Link>
          )}
        </span>
      ))}

      {extraCrumbs.map((crumb, i) => (
        <span key={`extra-${i}`} className="flex items-center">
          <ChevronRight className="w-4 h-4 mx-2 opacity-50" />
          {crumb.href ? (
            <Link href={crumb.href} className="hover:text-primary transition-colors">
              {crumb.label}
            </Link>
          ) : (
            <span className="font-medium text-primary">{crumb.label}</span>
          )}
        </span>
      ))}
    </nav>
  )
}
