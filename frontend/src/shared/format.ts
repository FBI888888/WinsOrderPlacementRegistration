import dayjs from 'dayjs'

export const currency = (value: string | number | undefined) =>
  new Intl.NumberFormat('zh-CN', {
    style: 'currency',
    currency: 'CNY',
    minimumFractionDigits: 2,
  }).format(Number(value ?? 0))

export const shortDate = (value: string) => dayjs(value).format('YYYY-MM-DD')
export const dateTime = (value: string) => dayjs(value).format('YYYY-MM-DD HH:mm:ss')

export const statusText: Record<string, string> = {
  DRAFT: '草稿',
  DISPATCHED: '已派单',
  SUCCESS: '成功',
  CANCELLED: '已取消',
  REVERSED: '已冲正',
  CONFIRMED: '已确认',
  SOURCE: '放单结算',
  CONTRACTOR: '做单结算',
  LEADER: '学生头子',
  RETAIL: '散户',
}

export const roleText: Record<string, string> = {
  OWNER: '负责人',
  BOOKKEEPER: '记账员',
  VIEWER: '只读成员',
}