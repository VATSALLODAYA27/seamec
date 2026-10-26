import { CompassOutlined, LockOutlined, UserOutlined } from '@ant-design/icons'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Card, Flex, Form, Input, Typography } from 'antd'

import { postJson, type User } from '../api'
import { APP_NAME } from '../brand'
import { ModeButton } from '../components/ui'

export default function SignIn() {
  const queryClient = useQueryClient()
  const login = useMutation({
    mutationFn: (v: { username: string; password: string }) => postJson<User>('/auth/login', v),
    onSuccess: (user) => queryClient.setQueryData(['me'], user),
  })
  return (
    <div className="signin">
      <Card className="signin-card">
        <Flex justify="space-between" align="center">
          <Typography.Title level={3} style={{ margin: 0, letterSpacing: '0.12em' }}>
            <CompassOutlined /> {APP_NAME}
          </Typography.Title>
          <ModeButton />
        </Flex>
        <Typography.Paragraph type="secondary" style={{ margin: '4px 0 24px' }}>
          Fleet, contracts, daily reports and charter-hire billing for SEAMEC.
        </Typography.Paragraph>
        {login.error && <Alert type="error" showIcon message={login.error.message} style={{ marginBottom: 16 }} />}
        <Form layout="vertical" requiredMark={false} onFinish={login.mutate}>
          <Form.Item name="username" label="Username" rules={[{ required: true, message: 'Enter your username' }]}>
            <Input prefix={<UserOutlined />} autoFocus autoComplete="username" />
          </Form.Item>
          <Form.Item name="password" label="Password" rules={[{ required: true, message: 'Enter your password' }]}>
            <Input.Password prefix={<LockOutlined />} autoComplete="current-password" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block size="large" loading={login.isPending}>
            Sign in
          </Button>
        </Form>
        <Typography.Paragraph type="secondary" style={{ marginTop: 16, marginBottom: 0, fontSize: 12 }}>
          Accounts are created by an administrator. All data shown is representative.
        </Typography.Paragraph>
      </Card>
    </div>
  )
}
