import { describe, expect, it } from 'vitest'

import { formatDateTime, formatMoney, formatQuantity } from '../utils/formatters'

describe('顯示格式', () => {
  it('統一格式化金額與三位小數數量', () => {
    expect(formatMoney('1234.50')).toBe('TWD 1,234.5')
    expect(formatQuantity('3.125', 'EA')).toBe('3.125 EA')
  })

  it('空值或無效值顯示橫線', () => {
    expect(formatMoney('invalid')).toBe('—')
    expect(formatDateTime(null)).toBe('—')
  })
})
