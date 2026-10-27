import { CheckOutlined, CompassOutlined, ExclamationOutlined, LogoutOutlined } from '@ant-design/icons'
import { useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Card, DatePicker, Descriptions, Empty, Flex, Form, Input, InputNumber, Modal, Select, Table, Typography } from 'antd'
import dayjs, { type Dayjs } from 'dayjs'
import { useState } from 'react'

import { CLAIM_KINDS, fmtDate, money, num, postJson, useAction, useClientClaims, useClientContracts, useTimesheet, type User } from '../api'
import { APP_NAME } from '../brand'
import { ErrorAlert, StateTag } from '../components/Tags'
import { forgetAll } from '../offline'
import { FormModal, ModeButton, RUPEES } from '../components/ui'

type ClaimValues = { contract_no: string; kind: string; month: Dayjs; description: string; amount_claimed: number }

/** The charterer's performance claims on its own contracts, and a way to raise one. */
function ClientClaims({ contracts }: { contracts: { value: string; label: string }[] }) {
  const claims = useClientClaims()
  const [raising, setRaising] = useState(false)
  const raise = useAction(
    (v: ClaimValues) => postJson('/client/claims', { contract_no: v.contract_no, kind: v.kind, period: v.month.format('YYYY-MM'), description: v.description, amount_claimed: v.amount_claimed }),
    'Claim sent to SEAMEC',
    () => setRaising(false),
  )
  return (
    <Card title="Performance claims" style={{ marginTop: 24 }} extra={contracts.length > 0 && <Button onClick={() => setRaising(true)}>Raise a claim</Button>}>
      <Table
        size="small"
        rowKey="id"
        loading={claims.isPending}
        dataSource={claims.data}
        pagination={false}
        locale={{ emptyText: 'No claims raised' }}
        columns={[
          { title: 'Claim', dataIndex: 'kind', render: (k, c) => <><b>{CLAIM_KINDS[k as keyof typeof CLAIM_KINDS]}</b><div className="muted">{c.description}</div></> },
          { title: 'Contract', dataIndex: 'contract_no' },
          { title: 'Month', dataIndex: 'period', render: (p) => dayjs(`${p}-01`).format('MMM YYYY') },
          { title: 'Claimed', dataIndex: 'amount_claimed', align: 'right', render: money },
          { title: 'Agreed', dataIndex: 'amount_agreed', align: 'right', render: (a) => (a === null ? '—' : money(a)) },
          { title: 'Status', dataIndex: 'status', render: (s, c) => <><StateTag kind="claim" value={s} />{c.decision_note && <div className="muted">{c.decision_note}</div>}</> },
        ]}
      />
      <FormModal<ClaimValues>
        open={raising}
        title="Raise a performance claim"
        okText="Send claim"
        initial={{ contract_no: contracts[0]?.value, kind: 'EQUIPMENT', month: dayjs() }}
        pending={raise.isPending}
        error={raise.error}
        onSubmit={raise.mutate}
        onClose={() => setRaising(false)}
      >
        <Form.Item name="contract_no" label="Contract" rules={[{ required: true }]}><Select options={contracts} /></Form.Item>
        <Form.Item name="kind" label="About"><Select options={Object.entries(CLAIM_KINDS).map(([value, label]) => ({ value, label }))} /></Form.Item>
        <Form.Item name="month" label="Hire month" rules={[{ required: true }]}><DatePicker picker="month" style={{ width: '100%' }} disabledDate={(d) => d.isAfter(dayjs(), 'month')} /></Form.Item>
        <Form.Item name="description" label="What happened" rules={[{ required: true, min: 5 }]}><Input.TextArea rows={3} maxLength={2000} /></Form.Item>
        <Form.Item name="amount_claimed" label="Amount claimed" rules={[{ required: true }]}><InputNumber {...RUPEES} /></Form.Item>
        <Typography.Text type="secondary">SEAMEC answers within 14 days.</Typography.Text>
      </FormModal>
    </Card>
  )
}

/**
 * What a charterer's representative sees: only their own contracts, the approved daily reports for a month,
 * and a button to sign the month's timesheet or dispute it with a reason.
 */
export default function ClientPortal({ me }: { me: User }) {
  const queryClient = useQueryClient()
  const contracts = useClientContracts()
  const [contractNo, setContractNo] = useState<string>()
  const [month, setMonth] = useState<Dayjs>(dayjs().subtract(1, 'month'))
  const period = month.format('YYYY-MM')
  const chosen = contractNo ?? contracts.data?.[0]?.contract_no
  const sheet = useTimesheet(chosen, period)
  const [disputing, setDisputing] = useState(false)
  const [note, setNote] = useState('')
  const decide = useAction(
    ({ decision, note }: { decision: 'SIGNED' | 'DISPUTED'; note?: string }) => postJson('/client/timesheet', { contract_no: chosen, period, decision, note: note ?? '' }),
    'Recorded. SEAMEC has been notified.',
    () => {
      setDisputing(false)
      setNote('')
    },
  )
  const signOut = async () => {
    await postJson('/auth/logout').catch(() => undefined)
    forgetAll()
    queryClient.removeQueries({ predicate: (q) => q.queryKey[0] !== 'me' })
    queryClient.setQueryData(['me'], null)
  }
  const s = sheet.data
  const ended = period < dayjs().format('YYYY-MM')

  return (
    <div style={{ minHeight: '100vh', background: 'var(--page)' }}>
      <header className="client-bar">
        <span className="wordmark">
          <CompassOutlined /> {APP_NAME} <small>client portal · SEAMEC</small>
        </span>
        <span style={{ flex: 1 }} />
        <span>{me.name}</span>
        <ModeButton light />
        <Button type="text" icon={<LogoutOutlined />} style={{ color: '#fff' }} onClick={signOut} aria-label="Sign out" />
      </header>
      <main className="main" style={{ maxWidth: 1100, margin: '0 auto' }}>
        <Typography.Title level={2}>Monthly timesheet</Typography.Title>
        <Typography.Paragraph type="secondary">
          The vessel's approved daily reports for the month. Sign the timesheet if it is right, or dispute it saying what is wrong. SEAMEC invoices only after it is signed.
        </Typography.Paragraph>
        <ErrorAlert error={contracts.error ?? sheet.error ?? decide.error} />
        <Flex gap={12} wrap style={{ marginBottom: 16 }}>
          <Select
            style={{ minWidth: 320 }}
            value={chosen}
            onChange={setContractNo}
            options={(contracts.data ?? []).map((c) => ({ value: c.contract_no, label: `${c.contract_no} · ${c.vessel_name}` }))}
            aria-label="Contract"
          />
          <DatePicker picker="month" value={month} onChange={(m) => m && setMonth(m)} allowClear={false} disabledDate={(d) => d.isAfter(dayjs(), 'month')} aria-label="Month" />
        </Flex>
        {!contracts.isPending && !contracts.data?.length && <Empty description="No contracts are linked to your account." />}
        {s && (
          <Card
            title={`${s.contract_no} · ${dayjs(`${s.period}-01`).format('MMMM YYYY')}`}
            extra={
              s.signoff ? (
                <StateTag kind="signoff" value={s.signoff.status} />
              ) : ended ? (
                <Flex gap={8}>
                  <Button danger icon={<ExclamationOutlined />} onClick={() => setDisputing(true)}>
                    Dispute
                  </Button>
                  <Button type="primary" icon={<CheckOutlined />} loading={decide.isPending} disabled={s.pending_dates.length > 0} onClick={() => decide.mutate({ decision: 'SIGNED' })}>
                    Sign timesheet
                  </Button>
                </Flex>
              ) : (
                <span className="muted">Can be signed once the month has ended</span>
              )
            }
          >
            {s.signoff && (
              <Alert
                type={s.signoff.status === 'SIGNED' ? 'success' : 'warning'}
                showIcon
                style={{ marginBottom: 16 }}
                message={`${s.signoff.status === 'SIGNED' ? 'Signed' : 'Disputed'} by ${s.signoff.by} on ${fmtDate(s.signoff.at)}`}
                description={s.signoff.note || undefined}
                action={
                  s.signoff.status === 'DISPUTED' && (
                    <Button size="small" type="primary" onClick={() => decide.mutate({ decision: 'SIGNED' })}>
                      Sign now
                    </Button>
                  )
                }
              />
            )}
            {s.pending_dates.length > 0 && <Alert type="info" showIcon style={{ marginBottom: 16 }} message={`SEAMEC is still checking the reports for ${s.pending_dates.map(fmtDate).join(', ')}.`} />}
            <Descriptions size="small" column={{ xs: 2, md: 4 }} style={{ marginBottom: 12 }}>
              <Descriptions.Item label="Operating h">{num(s.hours.operating)}</Descriptions.Item>
              <Descriptions.Item label="Standby h">{num(s.hours.standby)}</Descriptions.Item>
              <Descriptions.Item label="Paid maintenance h">{num(s.hours.breakdown_paid)}</Descriptions.Item>
              <Descriptions.Item label="Off hire h">{num(s.hours.off_hire)}</Descriptions.Item>
              <Descriptions.Item label="Hire before tax">{money(s.amount)}</Descriptions.Item>
              <Descriptions.Item label="Days not reported">{s.missing_dates.length}</Descriptions.Item>
            </Descriptions>
            <Table
              size="small"
              rowKey="on_date"
              pagination={false}
              dataSource={s.rows}
              scroll={{ x: 900 }}
              columns={[
                { title: 'Date', dataIndex: 'on_date', render: fmtDate, width: 110 },
                { title: 'Op', dataIndex: 'operating_hrs', align: 'right', width: 55 },
                { title: 'Stby', dataIndex: 'standby_hrs', align: 'right', width: 55 },
                { title: 'Wx', dataIndex: 'weather_hrs', align: 'right', width: 55 },
                { title: 'Bkdn', dataIndex: 'breakdown_hrs', align: 'right', width: 60 },
                { title: 'Transit', dataIndex: 'transit_hrs', align: 'right', width: 65 },
                { title: 'Dive h', dataIndex: 'dive_hrs', align: 'right', width: 65, render: num },
                { title: 'Location', dataIndex: 'location', ellipsis: true },
                { title: 'Work done', dataIndex: 'work_done', ellipsis: true },
              ]}
            />
          </Card>
        )}
        <ClientClaims contracts={(contracts.data ?? []).map((c) => ({ value: c.contract_no, label: `${c.contract_no} · ${c.vessel_name}` }))} />
      </main>
      <Modal
        open={disputing}
        title="Dispute the timesheet"
        okText="Send dispute"
        okButtonProps={{ danger: true, disabled: !note.trim() }}
        confirmLoading={decide.isPending}
        onOk={() => decide.mutate({ decision: 'DISPUTED', note: note.trim() })}
        onCancel={() => setDisputing(false)}
      >
        <Typography.Paragraph type="secondary">Say which days and hours are wrong. SEAMEC will correct the reports and ask you again.</Typography.Paragraph>
        <Input.TextArea rows={4} value={note} onChange={(e) => setNote(e.target.value)} maxLength={1000} aria-label="What is disputed" />
      </Modal>
    </div>
  )
}
