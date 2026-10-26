import { Card, Input, Table, Tag } from 'antd'
import { useState } from 'react'

import { formatTime, useAudit, type AuditEntry } from '../api'
import { ErrorAlert } from '../components/Tags'
import { PageHead } from '../components/ui'

const tone = (action: string) => (action.endsWith('failed') || action.endsWith('rejected') || action.endsWith('switched_off') ? 'error' : action.endsWith('approved') || action.endsWith('paid') ? 'success' : undefined)

export default function Audit() {
  const audit = useAudit()
  const [q, setQ] = useState('')
  const rows = (audit.data ?? []).filter((e) => !q || `${e.username} ${e.action} ${e.target} ${e.detail}`.toLowerCase().includes(q.toLowerCase()))
  return (
    <>
      <PageHead title="Audit log" sub="Every sign-in, approval, renewal and payment, newest first." actions={<Input.Search allowClear placeholder="Search" aria-label="Search the audit log" onChange={(e) => setQ(e.target.value)} style={{ width: 260 }} />} />
      <Card>
        <ErrorAlert error={audit.error} />
        <Table<AuditEntry>
          rowKey="id"
          size="small"
          loading={audit.isPending}
          dataSource={rows}
          pagination={{ pageSize: 25, hideOnSinglePage: true }}
          columns={[
            { title: 'When', dataIndex: 'at', width: 180, render: formatTime },
            { title: 'Who', dataIndex: 'username', width: 120 },
            { title: 'Action', dataIndex: 'action', width: 170, render: (a: string) => <Tag color={tone(a)}>{a}</Tag> },
            { title: 'Record', dataIndex: 'target', width: 200 },
            { title: 'Detail', dataIndex: 'detail' },
          ]}
        />
      </Card>
    </>
  )
}
