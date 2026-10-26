import { UserAddOutlined } from '@ant-design/icons'
import { Button, Card, Form, Input, Modal, Select, Switch, Table, Typography } from 'antd'
import { useState } from 'react'

import { postJson, useAction, useUsers, type Account, type User } from '../api'
import { ErrorAlert, ROLE_LABEL } from '../components/Tags'
import { PageHead } from '../components/ui'

export default function Users({ me }: { me: User }) {
  const users = useUsers()
  const [adding, setAdding] = useState(false)
  const [form] = Form.useForm()
  const role = Form.useWatch('role', form)
  const create = useAction((v: { username: string; name: string; role: string; password: string; client_name?: string }) => postJson('/users', v), 'User created', () => {
    form.resetFields()
    setAdding(false)
  })
  const toggle = useAction(({ username, active }: { username: string; active: boolean }) => postJson(`/users/${username}/active`, { active }), (u) =>
    (u as Account).active ? 'Account switched on' : 'Account switched off; signed out everywhere',
  )

  return (
    <>
      <PageHead
        title="Users"
        sub="Only an administrator creates accounts."
        actions={
          <Button type="primary" icon={<UserAddOutlined />} onClick={() => setAdding(true)}>
            Add user
          </Button>
        }
      />
      <Card>
        <ErrorAlert error={users.error} />
        <Table<Account>
          rowKey="username"
          size="small"
          pagination={false}
          loading={users.isPending}
          dataSource={users.data}
          columns={[
            { title: 'Username', dataIndex: 'username', render: (u) => <b>{u}</b> },
            { title: 'Name', dataIndex: 'name' },
            { title: 'Role', dataIndex: 'role', render: (r: User['role'], u) => <>{ROLE_LABEL[r]}{u.client_name && <div className="muted">{u.client_name}</div>}</> },
            {
              title: 'Can sign in',
              dataIndex: 'active',
              render: (active: boolean, u) =>
                u.username === me.username ? (
                  <Typography.Text type="secondary">You</Typography.Text>
                ) : (
                  <Switch checked={active} loading={toggle.isPending && toggle.variables?.username === u.username} onChange={(on) => toggle.mutate({ username: u.username, active: on })} />
                ),
            },
          ]}
        />
      </Card>
      <Modal open={adding} title="Add user" okText="Create" confirmLoading={create.isPending} onOk={() => form.submit()} onCancel={() => setAdding(false)}>
        <ErrorAlert error={create.error} />
        <Form form={form} layout="vertical" requiredMark={false} onFinish={create.mutate} initialValues={{ role: 'ops' }}>
          <Form.Item name="username" label="Username" rules={[{ required: true, pattern: /^[a-z0-9_.-]{3,32}$/, message: '3 to 32 lowercase letters, digits, dot, dash or underscore' }]}>
            <Input autoComplete="off" />
          </Form.Item>
          <Form.Item name="name" label="Full name" rules={[{ required: true, whitespace: true }]}>
            <Input />
          </Form.Item>
          <Form.Item
            name="role"
            label="Role"
            extra="Vessel / ops files daily reports. Ops manager approves reports, invoices and crew. Admin can do everything. A client representative only sees the client portal for their own contracts."
          >
            <Select options={Object.entries(ROLE_LABEL).map(([value, label]) => ({ value, label }))} />
          </Form.Item>
          {role === 'client' && (
            <Form.Item name="client_name" label="Client name (exactly as on the contracts)" rules={[{ required: true, whitespace: true }]}>
              <Input />
            </Form.Item>
          )}
          <Form.Item name="password" label="First password" rules={[{ required: true, min: 10, message: 'At least 10 characters' }]}>
            <Input.Password autoComplete="new-password" />
          </Form.Item>
        </Form>
      </Modal>
    </>
  )
}
