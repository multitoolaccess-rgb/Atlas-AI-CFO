'use client'

import { useReducedMotion } from 'framer-motion'

/** Decorative only. It contains no financial values or chart data. */
export default function BudgetOrbit() {
  const reduced = useReducedMotion()

  return (
    <div
      className={`budget-orbit ${reduced ? 'budget-orbit-static' : ''}`}
      aria-hidden="true"
      data-testid="budget-orbit"
    >
      <span className="budget-orbit-core" />
      <span className="budget-orbit-ring budget-orbit-ring-one" />
      <span className="budget-orbit-ring budget-orbit-ring-two" />
      <span className="budget-orbit-ring budget-orbit-ring-three" />
      <span className="budget-orbit-node budget-orbit-node-one" />
      <span className="budget-orbit-node budget-orbit-node-two" />
      <span className="budget-orbit-node budget-orbit-node-three" />
    </div>
  )
}
