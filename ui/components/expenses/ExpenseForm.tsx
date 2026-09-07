'use client'

import { useState, useCallback } from 'react'
import { AlertTriangle, Check, X } from 'lucide-react'
import { rulesService, type Category } from '@/lib/api'
import Input from '@/components/ui/Input'
import Select from '@/components/ui/Select'
import Button from '@/components/ui/Button'
import { formatCurrency } from '@/lib/format'

interface ExpenseFormProps {
  categories: Category[]
  accounts?: Array<{ id: number; name: string }>
  onSuccess?: () => void
  onCancel?: () => void
  className?: string
}

export default function ExpenseForm({
  categories,
  accounts,
  onSuccess,
  onCancel,
  className = '',
}: ExpenseFormProps) {
  const [description, setDescription] = useState('')
  const [amount, setAmount] = useState('')
  const [categoryId, setCategoryId] = useState('')
  const [accountId, setAccountId] = useState('')
  const [date, setDate] = useState(new Date().toISOString().split('T')[0])
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(false)
  const [success, setSuccess] = useState(false)

  const validate = useCallback(() => {
    const errs: Record<string, string> = {}
    if (!description.trim()) errs.description = 'Description required'
    if (!amount) errs.amount = 'Amount required'
    else if (Number(amount) <= 0) errs.amount = 'Amount must be > 0'
    else if (Number(amount) > 999999999) errs.amount = 'Amount too large'
    if (!categoryId) errs.category = 'Category required'
    if (!date) errs.date = 'Date required'
    setErrors(errs)
    return Object.keys(errs).length === 0
  }, [description, amount, categoryId, date])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!validate()) return

    try {
      setLoading(true)
      await rulesService.createTransaction({
        description: description.trim(),
        amount: -Math.abs(Number(amount)),
        transaction_date: date,
        category_id: Number(categoryId),
        account_id: accountId ? Number(accountId) : undefined,
      })
      setSuccess(true)
      setTimeout(() => {
        setDescription('')
        setAmount('')
        setCategoryId('')
        setAccountId('')
        setDate(new Date().toISOString().split('T')[0])
        setSuccess(false)
        onSuccess?.()
      }, 1500)
    } catch (err) {
      setErrors({
        submit: err instanceof Error ? err.message : 'Failed to save',
      })
    } finally {
      setLoading(false)
    }
  }

  if (success) {
    return (
      <div className={`card p-8 flex flex-col items-center justify-center ${className}`}>
        <div className="w-12 h-12 rounded-full bg-[var(--success-100)] flex items-center justify-center mb-4">
          <Check className="w-6 h-6 text-[var(--success-600)]" />
        </div>
        <p className="text-lg font-semibold text-[var(--text-primary)]">
          Expense saved
        </p>
        <p className="text-sm text-[var(--text-secondary)] mt-1">
          {formatCurrency(Math.abs(Number(amount)))} added to {categories.find((c) => c.id === Number(categoryId))?.name}
        </p>
      </div>
    )
  }

  return (
    <form onSubmit={handleSubmit} className={`card p-6 space-y-4 ${className}`}>
      <h3 className="headline-md text-primary">Add Expense</h3>

      {errors.submit && (
        <div className="flex items-center gap-2 p-3 rounded-lg bg-[var(--danger-50)] border border-[var(--danger-200)]">
          <AlertTriangle className="w-5 h-5 text-[var(--danger-500)] shrink-0" />
          <p className="text-sm text-[var(--danger-700)]">{errors.submit}</p>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Input
          label="Description"
          placeholder="Groceries, gas, etc."
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          error={errors.description}
          disabled={loading}
        />

        <Input
          label="Amount"
          type="number"
          placeholder="0.00"
          min="0"
          step="0.01"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          error={errors.amount}
          disabled={loading}
        />

        <Select
          label="Category"
          options={categories.map((c) => ({
            value: String(c.id),
            label: c.name,
          }))}
          value={categoryId}
          onChange={(e) => setCategoryId(e.target.value)}
          error={errors.category}
          disabled={loading}
          placeholder="Select a category"
        />

        <Input
          label="Date"
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
          error={errors.date}
          disabled={loading}
        />

        {accounts && accounts.length > 0 && (
          <Select
            label="Account (optional)"
            options={accounts.map((a) => ({
              value: String(a.id),
              label: a.name,
            }))}
            value={accountId}
            onChange={(e) => setAccountId(e.target.value)}
            disabled={loading}
            placeholder="Select account"
          />
        )}
      </div>

      <div className="flex justify-end gap-2 pt-4 border-t border-[var(--border-subtle)]">
        <Button
          variant="tertiary"
          onClick={onCancel}
          disabled={loading}
        >
          <X className="w-4 h-4" />
          Cancel
        </Button>
        <Button disabled={loading}>
          {loading ? 'Saving...' : 'Save Expense'}
          <Check className="w-4 h-4" />
        </Button>
      </div>
    </form>
  )
}
