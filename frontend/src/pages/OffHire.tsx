import { PlusOutlined, WarningOutlined } from '@ant-design/icons'
import { Button, Card, DatePicker, Form, Input, InputNumber, Popconfirm, Radio, Select, Table, Tabs, Tag, Tooltip, Typography } from 'antd'
import dayjs, { type Dayjs } from 'dayjs'
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { can, CLAIM_KINDS, fmtDate, money, moneyShort, postJson, useAction, useClaims, useContracts, useOffHire, useVessels, type Claim, type OffHire as Event, type User } from '../api'
import { ErrorAlert, StateTag } from '../components/Tags'
import { FormModal, Metric, PageHead, RUPEES, VesselLink } from '../components/ui'

export const REASONS: Record<Event['reason'], string> = {
  BREAKDOWN: 'Breakdown',
  MAINTENANCE: 'Maintenance',
  CREW: 'Crew shortage',
  DOCUMENTS: 'Documents / certificates',
  OTHER: 'Other deficiency',
}
const minute = (d: Dayjs) => d.format('YYYY-MM-DDTHH:mm')
const when = (at: string) => dayjs(at).format('D MMM, HH:mm')

function Events({ me }: { me: User }) {
  const events = useOffHire()
  const vessels = useVessels()
  const [logging, setLogging] = useState(false)
  const [ending, setEnding] = useState<Event | null>(null)
  const log = useAction(
    (v: { vessel_id: string; start: Dayjs; end?: Dayjs; reason: string; description: string }) =>
      postJson('/off-hire', { vessel_id: v.vessel_id, start_at: minute(v.start), end_at: v.end ? minute(v.end) : null, reason: v.reason, description: v.description }),
    'Off hire logged',
    () => setLogging(false),
  )
  const end = useAction(({ id, at }: { id: number; at: Dayjs }) => postJson(`/off-hire/${id}/end`, { end_at: minute(at) }), 'Back on hire', () => setEnding(null))
  const agree = useAction((id: number) => postJson(`/off-hire/${id}/agree`), 'Recorded as agreed by the charterer')

  return (
    <>
      <Table<Event>
        size="small"
        rowKey="id"
        loading={events.isPending}
        dataSource={events.data}
        pagination={{ pageSize: 20 }}
        scroll={{ x: 1000 }}
        title={() => (
          <Button icon={<PlusOutlined />} onClick={() => setLogging(true)}>
            Log off hire
          </Button>
        )}
        columns={[
          { title: 'Vessel', dataIndex: 'vessel_id', render: (id, e) => <><VesselLink id={id} name={e.vessel_name} /><div className="muted">{e.client ?? 'No contract'}</div></> },
          { title: 'Period', key: 'p', render: (_, e) => <>{when(e.start_at)} – {e.end_at ? when(e.end_at) : <b>ongoing</b>}<div className="muted">{e.hours} h</div></> },
          {
            title: 'Reason',
            dataIndex: 'reason',
            render: (r, e) => (
              <>
                {REASONS[r as Event['reason']]}
                <div className="muted">{e.uses_allowance ? 'Uses the maintenance allowance first' : 'Straight off hire'}</div>
              </>
            ),
          },
          { title: 'What happened', dataIndex: 'description', ellipsis: true },
          {
            title: 'Daily reports',
            key: 'rep',
            render: (_, e) =>
              e.mismatch ? (
                <Tooltip title="Daily reports for these days show less breakdown time than this off hire. Correct the reports, or this event.">
                  <Tag color="warning" icon={<WarningOutlined />}>Reports show {e.reported_breakdown_hrs} h</Tag>
                </Tooltip>
              ) : (
                <span className="muted">Match</span>
              ),
          },
          { title: 'Status', dataIndex: 'status', render: (s) => <StateTag kind="offhire" value={s} /> },
          {
            title: '',
            key: 'act',
            render: (_, e) =>
              e.status === 'OPEN' ? (
                <Button size="small" onClick={() => setEnding(e)}>Back on hire</Button>
              ) : (
                e.status === 'ENDED' && can.manage(me) && e.contract_no && (
                  <Popconfirm title="The charterer has accepted this off-hire statement?" onConfirm={() => agree.mutate(e.id)}>
                    <Button size="small">Charterer agreed</Button>
                  </Popconfirm>
                )
              ),
          },
        ]}
      />
      <FormModal<{ vessel_id: string; start: Dayjs; end?: Dayjs; reason: string; description: string }>
        open={logging}
        title="Log off hire"
        okText="Log off hire"
        initial={{ reason: 'BREAKDOWN', start: dayjs().startOf('hour') }}
        pending={log.isPending}
        error={log.error}
        onSubmit={log.mutate}
        onClose={() => setLogging(false)}
      >
        <Form.Item name="vessel_id" label="Vessel" rules={[{ required: true }]}>
          <Select options={vessels.data?.map((v) => ({ value: v.vessel_id, label: v.name }))} />
        </Form.Item>
        <Form.Item name="reason" label="Reason" extra="Breakdown and maintenance use the contract's maintenance allowance first; anything else is off hire straight away.">
          <Select options={Object.entries(REASONS).map(([value, label]) => ({ value, label }))} />
        </Form.Item>
        <Form.Item name="start" label="Off hire from" rules={[{ required: true }]}>
          <DatePicker showTime={{ format: 'HH:mm' }} format="D MMM YYYY HH:mm" style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item name="end" label="Back on hire at" extra="Leave empty while still off hire.">
          <DatePicker showTime={{ format: 'HH:mm' }} format="D MMM YYYY HH:mm" style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item name="description" label="What happened" rules={[{ required: true, min: 3 }]}>
          <Input.TextArea rows={2} maxLength={1000} />
        </Form.Item>
      </FormModal>
      <FormModal<{ at: Dayjs }>
        open={!!ending}
        title={`Back on hire: ${ending?.vessel_name}`}
        okText="Save"
        initial={{ at: dayjs().startOf('hour') }}
        pending={end.isPending}
        onSubmit={(v) => end.mutate({ id: ending!.id, at: v.at })}
        onClose={() => setEnding(null)}
      >
        <Form.Item name="at" label="Back on hire at" rules={[{ required: true }]}>
          <DatePicker showTime={{ format: 'HH:mm' }} format="D MMM YYYY HH:mm" style={{ width: '100%' }} />
        </Form.Item>
      </FormModal>
    </>
  )
}

function Claims({ me }: { me: User }) {
  const claims = useClaims()
  const contracts = useContracts()
  const [adding, setAdding] = useState(false)
  const [deciding, setDeciding] = useState<Claim | null>(null)
  const add = useAction(
    (v: { contract_no: string; kind: string; month: Dayjs; description: string; amount_claimed: number }) =>
      postJson('/claims', { contract_no: v.contract_no, kind: v.kind, period: v.month.format('YYYY-MM'), description: v.description, amount_claimed: v.amount_claimed }),
    'Claim recorded',
    () => setAdding(false),
  )
  const decide = useAction(({ id, ...body }: { id: number; status: string; amount_agreed?: number; note: string }) => postJson(`/claims/${id}/decide`, body), 'Decision recorded', () => setDeciding(null))
  const manage = can.manage(me)

  return (
    <>
      <Table<Claim>
        size="small"
        rowKey="id"
        loading={claims.isPending}
        dataSource={claims.data}
        pagination={{ pageSize: 20 }}
        scroll={{ x: 1000 }}
        title={() => manage && <Button icon={<PlusOutlined />} onClick={() => setAdding(true)}>Record a claim</Button>}
        columns={[
          { title: 'Claim', dataIndex: 'kind', render: (k, c) => <><b>{CLAIM_KINDS[k as Claim['kind']]}</b><div className="muted">{c.description}</div></> },
          { title: 'Contract', dataIndex: 'contract_no', render: (no, c) => <>{no}<div className="muted">{c.client} · {c.vessel_name}</div></> },
          { title: 'Month', dataIndex: 'period', render: (p) => dayjs(`${p}-01`).format('MMM YYYY') },
          { title: 'Claimed', dataIndex: 'amount_claimed', align: 'right', render: money },
          { title: 'Agreed', dataIndex: 'amount_agreed', align: 'right', render: (a) => (a === null ? '—' : money(a)) },
          {
            title: 'Answer by',
            dataIndex: 'response_due',
            render: (d, c) => (c.status !== 'OPEN' ? <span className="muted">{c.decision_note}</span> : c.overdue ? <Tag color="error">Overdue, {fmtDate(d)}</Tag> : fmtDate(d)),
          },
          { title: 'Status', dataIndex: 'status', render: (s) => <StateTag kind="claim" value={s} /> },
          { title: '', key: 'act', render: (_, c) => manage && c.status === 'OPEN' && <Button size="small" onClick={() => setDeciding(c)}>Decide</Button> },
        ]}
      />
      <FormModal<{ contract_no: string; kind: string; month: Dayjs; description: string; amount_claimed: number }>
        open={adding}
        title="Record a charterer's claim"
        okText="Record claim"
        initial={{ kind: 'EQUIPMENT', month: dayjs() }}
        pending={add.isPending}
        error={add.error}
        onSubmit={add.mutate}
        onClose={() => setAdding(false)}
      >
        <Form.Item name="contract_no" label="Contract" rules={[{ required: true }]}>
          <Select options={contracts.data?.map((c) => ({ value: c.contract_no, label: `${c.contract_no} · ${c.client}` }))} />
        </Form.Item>
        <Form.Item name="kind" label="About">
          <Select options={Object.entries(CLAIM_KINDS).map(([value, label]) => ({ value, label }))} />
        </Form.Item>
        <Form.Item name="month" label="Hire month it concerns" rules={[{ required: true }]}>
          <DatePicker picker="month" style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item name="description" label="What the charterer says" rules={[{ required: true, min: 5 }]}>
          <Input.TextArea rows={3} maxLength={2000} />
        </Form.Item>
        <Form.Item name="amount_claimed" label="Amount claimed" rules={[{ required: true }]}>
          <InputNumber {...RUPEES} />
        </Form.Item>
      </FormModal>
      <FormModal<{ status: string; amount_agreed?: number; note: string }>
        open={!!deciding}
        title={`Decide: ${deciding ? CLAIM_KINDS[deciding.kind] : ''} claim, ${money(deciding?.amount_claimed)}`}
        okText="Save decision"
        initial={{ status: 'ACCEPTED', amount_agreed: deciding?.amount_claimed }}
        pending={decide.isPending}
        error={decide.error}
        onSubmit={(v) => decide.mutate({ id: deciding!.id, ...v })}
        onClose={() => setDeciding(null)}
      >
        <Typography.Paragraph type="secondary">{deciding?.description}</Typography.Paragraph>
        <Form.Item name="status">
          <Radio.Group optionType="button" options={[{ value: 'ACCEPTED', label: 'Accept' }, { value: 'REJECTED', label: 'Reject' }]} />
        </Form.Item>
        <Form.Item noStyle dependencies={['status']}>
          {({ getFieldValue }) =>
            getFieldValue('status') === 'ACCEPTED' && (
              <Form.Item name="amount_agreed" label="Amount agreed" extra="Credited to the charterer; it comes off the contract's revenue." rules={[{ required: true }]}>
                <InputNumber {...RUPEES} max={deciding?.amount_claimed} />
              </Form.Item>
            )
          }
        </Form.Item>
        <Form.Item name="note" label="Reason" rules={[{ required: true, min: 3 }]}>
          <Input.TextArea rows={2} maxLength={1000} />
        </Form.Item>
      </FormModal>
    </>
  )
}

/** Off-hire periods with the reason for each, checked against the daily reports, and the charterers' claims. */
export default function OffHire({ me }: { me: User }) {
  const [params, setParams] = useSearchParams()
  const events = useOffHire()
  const claims = useClaims()
  const month = dayjs().format('YYYY-MM')
  const hoursThisMonth = (events.data ?? []).filter((e) => e.start_at.startsWith(month)).reduce((s, e) => s + e.hours, 0)
  const open = (claims.data ?? []).filter((c) => c.status === 'OPEN')
  const agreedYear = (claims.data ?? []).filter((c) => c.status === 'ACCEPTED' && c.period.startsWith(month.slice(0, 4))).reduce((s, c) => s + (c.amount_agreed ?? 0), 0)

  return (
    <>
      <PageHead title="Off hire and claims" sub="Time the vessel was off hire and why, and charterers' performance claims." />
      <ErrorAlert error={events.error ?? claims.error} />
      <div className="metrics page-figures">
        <Metric label="Off hire now" value={(events.data ?? []).filter((e) => e.status === 'OPEN').length} alert={(events.data ?? []).some((e) => e.status === 'OPEN')} />
        <Metric label="Off-hire hours this month" value={Math.round(hoursThisMonth)} />
        <Metric label="Claims awaiting our answer" value={open.length} note={moneyShort(open.reduce((s, c) => s + c.amount_claimed, 0)) + ' claimed'} alert={open.some((c) => c.overdue)} />
        <Metric label="Credits agreed this year" value={moneyShort(agreedYear)} />
      </div>
      <Card>
        <Tabs
          activeKey={params.get('tab') ?? 'events'}
          onChange={(tab) => setParams({ tab })}
          items={[
            { key: 'events', label: 'Off-hire periods', children: <Events me={me} /> },
            { key: 'claims', label: `Charterer claims${open.length ? ` (${open.length})` : ''}`, children: <Claims me={me} /> },
          ]}
        />
      </Card>
    </>
  )
}
