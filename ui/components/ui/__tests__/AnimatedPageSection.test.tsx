import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import React from 'react'
import type * as framerMotion from 'framer-motion'
import AnimatedPageSection from '../AnimatedPageSection'

const reducedMotionMock = vi.fn(() => false)
let capturedMotionProps: Record<string, unknown> = {}

vi.mock('@/lib/useReducedMotion', () => ({
  useReducedMotion: () => reducedMotionMock(),
}))

vi.mock('framer-motion', async (importOriginal) => {
  const actual = (await importOriginal()) as typeof framerMotion

  // Stand-in for motion.div that preserves refs and data-* props so
  // we can inspect the props that AnimatedPageSection passes through.
  const FakeMotionDiv = React.forwardRef<
    HTMLDivElement,
    React.HTMLAttributes<HTMLDivElement>
  >((props, ref) => {
    const { children, ...rest } = props
    return (
      <div ref={ref} {...rest}>
        {children}
      </div>
    )
  })
  FakeMotionDiv.displayName = 'FakeMotionDiv'

  const MotionDiv = React.forwardRef<HTMLDivElement, Record<string, unknown>>(
    (props, ref) => {
      capturedMotionProps = props
      return (
        <FakeMotionDiv
          ref={ref}
          {...(props as React.HTMLAttributes<HTMLDivElement>)}
        />
      )
    },
  )
  MotionDiv.displayName = 'MotionDiv'

  return {
    ...actual,
    motion: {
      ...actual.motion,
      div: MotionDiv,
    },
  }
})

describe('AnimatedPageSection', () => {
  beforeEach(() => {
    capturedMotionProps = {}
    reducedMotionMock.mockReturnValue(false)
  })

  it('renders its children', () => {
    render(
      <AnimatedPageSection>
        <div data-testid="child">Hello</div>
      </AnimatedPageSection>,
    )
    expect(screen.getByTestId('child')).toHaveTextContent('Hello')
  })

  it('forwards refs and extra props', () => {
    const ref = { current: null as HTMLDivElement | null }
    render(
      <AnimatedPageSection
        ref={(el) => {
          ref.current = el
        }}
        data-testid="wrapper"
      >
        <div>content</div>
      </AnimatedPageSection>,
    )
    const wrapper = screen.getByTestId('wrapper')
    expect(wrapper).toBeInTheDocument()
    expect(ref.current).toBe(wrapper)
  })

  it('uses the default entrance transition when reduced motion is off', () => {
    const initial = { opacity: 0, y: 16 }
    const animate = { opacity: 1, y: 0 }
    render(
      <AnimatedPageSection initial={initial} animate={animate}>
        <div>content</div>
      </AnimatedPageSection>,
    )
    expect(capturedMotionProps.initial).toEqual(initial)
    expect(capturedMotionProps.animate).toEqual(animate)
    expect(
      (capturedMotionProps.transition as { duration: number }).duration,
    ).toBe(0.4)
  })

  it('jumps to the final state immediately when reduced motion is preferred', () => {
    reducedMotionMock.mockReturnValueOnce(true)
    render(
      <AnimatedPageSection
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <div>content</div>
      </AnimatedPageSection>,
    )
    expect(screen.getByText('content')).toBeInTheDocument()
  })

  it('suppresses animation by setting initial to the final state when reduced motion is preferred', () => {
    reducedMotionMock.mockReturnValueOnce(true)
    const animate = { opacity: 1, y: 0 }
    render(
      <AnimatedPageSection initial={{ opacity: 0, y: 16 }} animate={animate}>
        <div>content</div>
      </AnimatedPageSection>,
    )
    expect(capturedMotionProps.initial).toEqual(animate)
    expect(
      (capturedMotionProps.transition as { duration: number }).duration,
    ).toBe(0)
  })
})
