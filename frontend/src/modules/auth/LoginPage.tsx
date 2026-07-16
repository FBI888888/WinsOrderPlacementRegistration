import { LockOutlined, MailOutlined, ShopOutlined, UserOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Form, Input, Segmented, Typography } from 'antd'
import { useState } from 'react'
import { Navigate } from 'react-router-dom'
import { errorMessage } from '../../shared/api'
import { useAuth } from '../../shared/auth-context'

export function LoginPage() {
  const { me, loading, login, register } = useAuth()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  if (!loading && me) return <Navigate to="/" replace />

  const submit = async (values: Record<string, string>) => {
    setSubmitting(true)
    setError('')
    try {
      if (mode === 'login') await login(values.email, values.password)
      else {
        await register({
          tenant_name: values.tenant_name,
          name: values.name,
          email: values.email,
          password: values.password,
        })
      }
    } catch (requestError) {
      setError(errorMessage(requestError, mode === 'login' ? '登录失败' : '创建账套失败'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-intro">
        <div className="auth-brand"><span>账</span>做单账本</div>
        <div>
          <Typography.Title>订单、垫资与利润，<br />在一本账里说清楚。</Typography.Title>
          <Typography.Paragraph>
            面向做单业务的独立账套。费率按日期留痕，成功订单自动入账，结算后锁定历史。
          </Typography.Paragraph>
        </div>
        <div className="auth-points">
          <span>多成员协作</span><span>账套数据隔离</span><span>可追溯结算</span>
        </div>
      </section>
      <section className="auth-form-wrap">
        <Card className="auth-card" bordered={false}>
          <Typography.Title level={2}>{mode === 'login' ? '登录账套' : '创建新账套'}</Typography.Title>
          <Typography.Paragraph type="secondary">
            {mode === 'login' ? '继续处理今天的订单和账务。' : '负责人账号将拥有当前账套的全部权限。'}
          </Typography.Paragraph>
          <Segmented
            block
            value={mode}
            options={[{ label: '登录', value: 'login' }, { label: '创建账套', value: 'register' }]}
            onChange={(value) => { setMode(value as 'login' | 'register'); setError('') }}
          />
          {error && <Alert type="error" showIcon message={error} />}
          <Form layout="vertical" size="large" onFinish={submit} requiredMark={false}>
            {mode === 'register' && (
              <>
                <Form.Item name="tenant_name" label="账套名称" rules={[{ required: true, min: 2 }]}>
                  <Input prefix={<ShopOutlined />} placeholder="例如：星河做单工作室" />
                </Form.Item>
                <Form.Item name="name" label="负责人姓名" rules={[{ required: true, min: 2 }]}>
                  <Input prefix={<UserOutlined />} placeholder="你的姓名" />
                </Form.Item>
              </>
            )}
            <Form.Item name="email" label="邮箱" rules={[{ required: true, type: 'email' }]}>
              <Input prefix={<MailOutlined />} placeholder="name@example.com" />
            </Form.Item>
            <Form.Item name="password" label="密码" rules={[{ required: true, min: 8 }]}>
              <Input.Password prefix={<LockOutlined />} placeholder="至少 8 位" />
            </Form.Item>
            <Button type="primary" htmlType="submit" block loading={submitting}>
              {mode === 'login' ? '登录' : '创建并进入'}
            </Button>
          </Form>
        </Card>
      </section>
    </main>
  )
}