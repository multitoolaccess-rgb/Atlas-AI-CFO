'use client'

import { useEffect, useRef, useState, Children, cloneElement, isValidElement } from 'react'
import { useReducedMotion } from '@/lib/useReducedMotion'

/**
 * AnimatedSection
 * ----------------
 * Reusable entrance-animation wrapper.
 *
 * - Uses IntersectionObserver so sections animate only when they scroll
 *   into view (avoids animating off-screen content).
 * - Respects `prefers-reduced-motion` by skipping transforms entirely.
 * - Supports staggered children via CSS custom properties.
 *
 * Usage:
 *   <AnimatedSection animation="slideUp" delay={100}>
 *     <SomeCard />
 *   </AnimatedSection>
 *
 * Note on stagger: children are cloned and injected with the
 * `stagger-item` class. Children that are valid React elements should
 * forward `className`; otherwise they are wrapped in a <span>.
 */

export type EntranceAnimation =
  | 'fadeIn'
  | 'slideUp'
  | 'slideDown'
  | 'slideInLeft'
  | 'slideInRight'
  | 'scaleIn'

export interface AnimatedSectionProps {
  children: React.ReactNode
  animation?: EntranceAnimation
  delay?: number
  duration?: number
  threshold?: number
  rootMargin?: string
  className?: string
  /** When true, children are rendered with stagger delay variables. */
  stagger?: boolean
  staggerDelay?: number
}

export default function AnimatedSection({
  children,
  animation = 'fadeIn',
  delay = 0,
  duration = 500,
  threshold = 0.1,
  rootMargin = '0px 0px -50px 0px',
  className = '',
  stagger = false,
  staggerDelay = 75,
}: AnimatedSectionProps) {
  const ref = useRef<HTMLDivElement>(null)
  const [inView, setInView] = useState(false)
  const reducedMotion = useReducedMotion()

  useEffect(() => {
    if (reducedMotion) {
      setInView(true)
      return
    }

    const el = ref.current
    if (!el) return

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setInView(true)
          observer.disconnect()
        }
      },
      { threshold, rootMargin },
    )

    observer.observe(el)
    return () => observer.disconnect()
  }, [reducedMotion, threshold, rootMargin])

  const style: React.CSSProperties = {
    '--animation-delay': `${delay}ms`,
    '--animation-duration': `${duration}ms`,
    '--stagger-delay': `${staggerDelay}ms`,
  } as React.CSSProperties

  const animationClass = reducedMotion
    ? ''
    : `animate-section-${animation}`

  const staggerClass = stagger && !reducedMotion ? 'stagger-children' : ''

  const renderedChildren =
    stagger && !reducedMotion
      ? Children.map(children, (child, index) =>
          isValidElement(child) ? (
            cloneElement(child as React.ReactElement<{ className?: string }>, {
              className: `stagger-item ${(child.props as { className?: string }).className ?? ''}`.trim(),
            })
          ) : (
            <span key={index} className="stagger-item">
              {child}
            </span>
          ),
        )
      : children

  return (
    <div
      ref={ref}
      className={`${animationClass} ${staggerClass} ${className}`.trim()}
      style={style}
      data-animate={inView ? 'true' : 'false'}
    >
      {renderedChildren}
    </div>
  )
}
