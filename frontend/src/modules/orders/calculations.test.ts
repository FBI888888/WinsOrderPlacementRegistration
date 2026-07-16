import { describe, expect, it } from 'vitest'
import { calculateDefaultActualPaid, calculateOrderPreview } from './calculations'

describe('calculateDefaultActualPaid', () => {
  it('按标价减优惠券计算并保留两位精度', () => {
    expect(calculateDefaultActualPaid(100, 20)).toBe(80)
    expect(calculateDefaultActualPaid(19.99, 0.1)).toBe(19.89)
  })

  it('输入不完整时不生成默认值', () => {
    expect(calculateDefaultActualPaid(undefined, 0)).toBeUndefined()
    expect(calculateDefaultActualPaid(100, undefined)).toBeUndefined()
  })

  it('优惠券超过标价时不生成负数', () => {
    expect(calculateDefaultActualPaid(10, 11)).toBe(0)
  })
})

describe('calculateOrderPreview', () => {
  it('按订单标价和折扣预估利润', () => {
    expect(calculateOrderPreview({
      settlementBasis: 'ORDER_AMOUNT',
      discount: 0.9,
      orderAmount: 100,
      couponAmount: 20,
      actualPaid: 70,
      defaultCommission: 5,
    })).toEqual({ income: 90, commission: 5, cost: 75, profit: 15 })
  })

  it('支持券后口径和人工覆盖', () => {
    expect(calculateOrderPreview({
      settlementBasis: 'AFTER_COUPON',
      discount: 0.9,
      orderAmount: 100,
      couponAmount: 20,
      actualPaid: 70,
      defaultCommission: 5,
      settlementIncomeOverride: 80,
      commissionOverride: 8,
    })).toEqual({ income: 80, commission: 8, cost: 78, profit: 2 })
  })
})