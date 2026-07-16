export interface PreviewInput {
  settlementBasis?: 'ORDER_AMOUNT' | 'AFTER_COUPON'
  discount?: number
  orderAmount?: number
  couponAmount?: number
  actualPaid?: number
  defaultCommission?: number
  settlementIncomeOverride?: number
  commissionOverride?: number
}

export function calculateDefaultActualPaid(
  orderAmount?: number | null,
  couponAmount?: number | null,
) {
  if (orderAmount === undefined || orderAmount === null || couponAmount === undefined || couponAmount === null) {
    return undefined
  }
  const difference = Number(orderAmount) - Number(couponAmount)
  if (!Number.isFinite(difference)) return undefined
  return Math.max(0, Math.round((difference + Number.EPSILON) * 100) / 100)
}

export function calculateOrderPreview(input: PreviewInput) {
  const orderAmount = Number(input.orderAmount ?? 0)
  const couponAmount = Number(input.couponAmount ?? 0)
  const actualPaid = Number(input.actualPaid ?? 0)
  const basisAmount = input.settlementBasis === 'AFTER_COUPON'
    ? orderAmount - couponAmount
    : orderAmount
  const income = input.settlementIncomeOverride ?? basisAmount * Number(input.discount ?? 0)
  const commission = input.commissionOverride ?? Number(input.defaultCommission ?? 0)
  const cost = actualPaid + commission
  return { income, commission, cost, profit: income - cost }
}