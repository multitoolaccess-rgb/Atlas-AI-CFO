import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render } from '@testing-library/react'
import AnimatedSection from '../AnimatedSection'

/**
 * AnimatedSection tests
 * ---------------------
 * Covers reduced-motion bypass, intersection-triggered animation,
 * and stagger rendering.
 */

describe('AnimatedSection', () => {
  let originalMatchMedia: typeof window.matchMedia
  let originalIntersectionObserver: typeof window.IntersectionObserver

  function mockMatchMedia(reduced: boolean) {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: query === '(prefers-reduced-motion: reduce)' ? reduced : false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })) as unknown as typeof window.matchMedia
  }

  beforeEach(() => {
    originalMatchMedia = window.matchMedia
    originalIntersectionObserver = window.IntersectionObserver

    window.IntersectionObserver = vi.fn().mockImplementation((callback) => ({
      observe: vi.fn(() => {
        // Immediately trigger intersection so data-animate becomes true
        callback([{ isIntersecting: true } as IntersectionObserverEntry])
      }),
      disconnect: vi.fn(),
      unobserve: vi.fn(),
      root: null,
      rootMargin: '',
      thresholds: [],
    })) as unknown as typeof window.IntersectionObserver
  })

  afterEach(() => {
    window.matchMedia = originalMatchMedia
    window.IntersectionObserver = originalIntersectionObserver
  })

  it('renders children', () => {
    mockMatchMedia(false)
    const { getByTestId } = render(
      <AnimatedSection animation="slideUp" delay={0}>
        <div data-testid="child">Hello</div>
      </AnimatedSection>,
    )
    expect(getByTestId('child')).toHaveTextContent('Hello')
  })

  it('sets data-animate to true when reduced motion is preferred', () => {
    mockMatchMedia(true)

    const { container } = render(
      <AnimatedSection animation="slideUp" delay={0}>
        <div>Child</div>
      </AnimatedSection>,
    )

    expect(container.firstChild).toHaveAttribute('data-animate', 'true')
  })

  it('sets data-animate to false before intersection', () => {
    window.IntersectionObserver = vi.fn().mockImplementation(() => ({
      observe: vi.fn(),
      disconnect: vi.fn(),
      unobserve: vi.fn(),
      root: null,
      rootMargin: '',
      thresholds: [],
    })) as unknown as typeof window.IntersectionObserver

    mockMatchMedia(false)

    const { container } = render(
      <AnimatedSection animation="slideUp" delay={0}>
        <div>Child</div>
      </AnimatedSection>,
    )

    expect(container.firstChild).toHaveAttribute('data-animate', 'false')
  })

  it('injects stagger-item class into children when stagger is enabled', () => {
    mockMatchMedia(false)

    const { container } = render(
      <AnimatedSection animation="slideUp" delay={0} stagger>
        <div data-testid="a">A</div>
        <div data-testid="b">B</div>
      </AnimatedSection>,
    )

    const wrapper = container.firstChild
    expect(wrapper).toHaveClass('stagger-children')
    expect(wrapper?.childNodes).toHaveLength(2)
    expect(wrapper?.firstChild).toHaveClass('stagger-item')
  })
})
