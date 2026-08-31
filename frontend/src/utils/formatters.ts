export function formatMoney(amount: string | number, currency = 'TWD') {
  const value = Number(amount)
  if (!Number.isFinite(value)) return '—'
  return `${currency} ${value.toLocaleString('zh-TW', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  })}`
}

export function formatQuantity(quantity: string | number, unit = '') {
  const value = Number(quantity)
  if (!Number.isFinite(value)) return '—'
  const formatted = value.toLocaleString('zh-TW', { maximumFractionDigits: 3 })
  return unit ? `${formatted} ${unit}` : formatted
}

export function formatDateTime(value: string | null | undefined) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return new Intl.DateTimeFormat('zh-TW', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}
