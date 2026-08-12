import { beforeEach, describe, expect, it } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import AppearanceSection from '../AppearanceSection'
import AppearanceProvider from '@/components/providers/AppearanceProvider'

beforeEach(() => {
  Object.defineProperty(window, 'localStorage', {
    configurable: true,
    value: {
      getItem: () => null,
      setItem: () => {},
      removeItem: () => {},
      clear: () => {},
    },
  })
  document.documentElement.className = ''
  document.documentElement.dataset.atlasTheme = 'light'
  document.documentElement.dataset.atlasAccent = 'indigo'
})

describe('AppearanceSection', () => {
  it('renders independent mode and accent radio groups', () => {
    render(<AppearanceProvider><AppearanceSection /></AppearanceProvider>)
    expect(screen.getByRole('heading', { name: 'Appearance' })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: /Light/ })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('radio', { name: /Indigo Intelligence/ })).toHaveAttribute('aria-checked', 'true')
  })

  it('switches accent without changing mode and exposes selected state', () => {
    render(<AppearanceProvider><AppearanceSection /></AppearanceProvider>)
    fireEvent.click(screen.getByTestId('appearance-accent-vermilion'))
    expect(document.documentElement.dataset.atlasAccent).toBe('vermilion')
    expect(document.documentElement.dataset.atlasTheme).toBe('light')
    expect(screen.getByRole('radio', { name: /Vermilion Energy/ })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('radio', { name: /Light/ })).toHaveAttribute('aria-checked', 'true')
  })

  it('switches mode without changing accent', () => {
    render(<AppearanceProvider><AppearanceSection /></AppearanceProvider>)
    fireEvent.click(screen.getByTestId('appearance-mode-dark'))
    expect(document.documentElement.classList.contains('dark')).toBe(true)
    expect(document.documentElement.dataset.atlasAccent).toBe('indigo')
    expect(screen.getByRole('radio', { name: /Dark/ })).toHaveAttribute('aria-checked', 'true')
  })

  it('synchronizes a profile change received from another tab', async () => {
    const values: Record<string, string> = { atlas_theme_mode: 'light', atlas_accent_profile: 'ion' }
    Object.defineProperty(window, 'localStorage', {
      configurable: true,
      value: {
        getItem: (key: string) => values[key] ?? null,
        setItem: (key: string, value: string) => { values[key] = value },
        removeItem: () => {},
        clear: () => {},
      },
    })
    render(<AppearanceProvider><AppearanceSection /></AppearanceProvider>)
    await waitFor(() => expect(document.documentElement.dataset.atlasAccent).toBe('ion'))
    values.atlas_accent_profile = 'vermilion'
    window.dispatchEvent(new StorageEvent('storage', { key: 'atlas_accent_profile', newValue: 'vermilion' }))
    await waitFor(() => expect(screen.getByRole('radio', { name: /Vermilion Energy/ })).toHaveAttribute('aria-checked', 'true'))
  })
})
