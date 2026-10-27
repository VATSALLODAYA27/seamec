import { PlusOutlined } from '@ant-design/icons'
import { Button, Card, Col, DatePicker, Form, Input, InputNumber, Row, Select, Space, Table, Tabs, Tag, Typography } from 'antd'
import dayjs, { type Dayjs } from 'dayjs'
import { useState } from 'react'

import {
  can,
  COVER_LABEL,
  fmtDate,
  moneyShort,
  postJson,
  putJson,
  useAction,
  useInsuranceClaims,
  usePolicies,
  useVessels,
  ymd,
  type InsuranceClaimRow,
  type PolicyRow,
  type User,
} from '../api'
import Documents from '../components/Documents'
import { ErrorAlert, StateTag } from '../components/Tags'
import { FormModal, Metric, PageHead, RUPEES, VesselLink } from '../components/ui'

type PolicyValues = Omit<PolicyRow, 'start_date' | 'end_date' | 'id' | 'state' | 'days_left' | 'open_claims' | 'vessel_name'> & { period: [Dayjs, Dayjs] }

function Policies({ me }: { me: User }) {
  const policies = usePolicies()
  const vessels = useVessels()
  const [editing, setEditing] = useState<PolicyRow | null | 'new'>(null)
  const current = editing === 'new' ? null : editing
  const save = useAction(
    ({ period, ...v }: PolicyValues) => {
      const body = { ...v, vessel_id: v.vessel_id ?? null, start_date: ymd(period[0]), end_date: ymd(period[1]) }
      return current ? putJson(`/insurance/policies/${current.id}`, body) : postJson('/insurance/policies', body)
    },
    'Policy saved',
    () => setEditing(null),
  )
  const manage = can.manage(me)
  return (
    <>
      <Table<PolicyRow>
        size="small"
        rowKey="id"
        loading={policies.isPending}
        dataSource={policies.data}
        pagination={{ pageSize: 25 }}
        scroll={{ x: 1000 }}
        title={() => manage && <Button icon={<PlusOutlined />} onClick={() => setEditing('new')}>New policy</Button>}
        columns={[
          { title: 'Cover', dataIndex: 'kind', filters: Object.entries(COVER_LABEL).map(([value, text]) => ({ value, text })), onFilter: (v, p) => p.kind === v, render: (k, p) => <><b>{COVER_LABEL[k as PolicyRow['kind']]}</b><div className="muted">{p.insurer} · {p.policy_no}</div></> },
          { title: 'Vessel', dataIndex: 'vessel_name', render: (n, p) => (p.vessel_id ? <VesselLink id={p.vessel_id} name={n} /> : <Tag>Whole fleet</Tag>) },
          { title: 'Sum insured', dataIndex: 'sum_insured', align: 'right', render: (v) => (v ? moneyShort(v) : <span className="muted">—</span>) },
          { title: 'Deductible', dataIndex: 'deductible', align: 'right', render: moneyShort },
          { title: 'Premium', dataIndex: 'premium', align: 'right', render: moneyShort },
          { title: 'Period', key: 'p', render: (_, p) => <>{fmtDate(p.start_date)} – {fmtDate(p.end_date)}{p.state !== 'EXPIRED' && <div className="muted">{p.days_left} days left</div>}</> },
          { title: 'State', dataIndex: 'state', render: (s) => <StateTag kind="policy" value={s} /> },
          {
            title: '',
            key: 'act',
            render: (_, p) => (
              <Space size={4}>
                <Documents entity="policy" entityKey={String(p.id)} title={`${COVER_LABEL[p.kind]} ${p.policy_no}`} canUpload={manage} defaultKind="POLICY" />
                {manage && <Button size="small" onClick={() => setEditing(p)}>Edit</Button>}
              </Space>
            ),
          },
        ]}
      />
      <FormModal<PolicyValues>
        open={editing !== null}
        title={current ? `Edit ${current.policy_no}` : 'New policy'}
        okText="Save policy"
        width={680}
        initial={current ? { ...current, period: [dayjs(current.start_date), dayjs(current.end_date)] } : { kind: 'HM', sum_insured: 0, deductible: 0, premium: 0 }}
        pending={save.isPending}
        error={save.error}
        onSubmit={save.mutate}
        onClose={() => setEditing(null)}
      >
        <Row gutter={16}>
          <Col span={8}>
            <Form.Item name="kind" label="Cover"><Select options={Object.entries(COVER_LABEL).map(([value, label]) => ({ value, label }))} /></Form.Item>
          </Col>
          <Col span={16}>
            <Form.Item name="vessel_id" label="Vessel" extra="Leave empty for a policy that covers the whole fleet.">
              <Select allowClear options={vessels.data?.map((v) => ({ value: v.vessel_id, label: v.name }))} />
            </Form.Item>
          </Col>
          <Col span={14}><Form.Item name="insurer" label="Insurer / P&I club" rules={[{ required: true, min: 2 }]}><Input /></Form.Item></Col>
          <Col span={10}><Form.Item name="policy_no" label="Policy number" rules={[{ required: true, min: 2 }]}><Input /></Form.Item></Col>
          <Col span={8}><Form.Item name="sum_insured" label="Sum insured"><InputNumber {...RUPEES} /></Form.Item></Col>
          <Col span={8}><Form.Item name="deductible" label="Deductible"><InputNumber {...RUPEES} /></Form.Item></Col>
          <Col span={8}><Form.Item name="premium" label="Premium for the period"><InputNumber {...RUPEES} /></Form.Item></Col>
          <Col span={24}><Form.Item name="period" label="Period of cover" rules={[{ required: true }]}><DatePicker.RangePicker style={{ width: '100%' }} /></Form.Item></Col>
        </Row>
      </FormModal>
    </>
  )
}

function Claims({ me }: { me: User }) {
  const claims = useInsuranceClaims()
  const policies = usePolicies()
  const vessels = useVessels()
  const [adding, setAdding] = useState(false)
  const [updating, setUpdating] = useState<{ claim: InsuranceClaimRow; status: 'SUBMITTED' | 'SETTLED' | 'REJECTED' } | null>(null)
  const add = useAction((v: { policy_id: number; vessel_id: string; incident: Dayjs; description: string; amount: number }) =>
    postJson('/insurance/claims', { policy_id: v.policy_id, vessel_id: v.vessel_id, incident_on: ymd(v.incident), description: v.description, amount: v.amount }), 'Claim notified', () => setAdding(false))
  const update = useAction((v: { on: Dayjs; recovered?: number }) => postJson(`/insurance/claims/${updating!.claim.id}/status`, { status: updating!.status, on: ymd(v.on), recovered: v.recovered ?? null }), 'Claim updated', () => setUpdating(null))
  const manage = can.manage(me)
  return (
    <>
      <Table<InsuranceClaimRow>
        size="small"
        rowKey="id"
        loading={claims.isPending}
        dataSource={claims.data}
        pagination={{ pageSize: 25 }}
        scroll={{ x: 1000 }}
        title={() => manage && <Button icon={<PlusOutlined />} onClick={() => setAdding(true)}>Notify a claim</Button>}
        columns={[
          { title: 'Vessel', dataIndex: 'vessel_id', render: (id, c) => <VesselLink id={id} name={c.vessel_name} /> },
          { title: 'Incident', dataIndex: 'description', render: (d, c) => <>{d}<div className="muted">{fmtDate(c.incident_on)}</div></> },
          { title: 'Policy', dataIndex: 'policy_no', render: (no, c) => <>{COVER_LABEL[c.kind]}<div className="muted">{c.insurer} · {no}</div></> },
          { title: 'Claimed', dataIndex: 'amount', align: 'right', render: moneyShort },
          { title: 'Deductible', dataIndex: 'deductible', align: 'right', render: moneyShort },
          {
            title: 'Recovery',
            key: 'r',
            align: 'right',
            render: (_, c) => (c.recovered !== null ? <b>{moneyShort(c.recovered)}</b> : <span className="muted">expected {moneyShort(c.expected_recovery)}</span>),
          },
          { title: 'Status', dataIndex: 'status', render: (s) => <StateTag kind="insclaim" value={s} /> },
          {
            title: '',
            key: 'act',
            render: (_, c) =>
              manage && (
                <Space size={4}>
                  {c.status === 'NOTIFIED' && <Button size="small" onClick={() => setUpdating({ claim: c, status: 'SUBMITTED' })}>Submitted</Button>}
                  {c.status === 'SUBMITTED' && <Button size="small" type="primary" onClick={() => setUpdating({ claim: c, status: 'SETTLED' })}>Settled</Button>}
                  {['NOTIFIED', 'SUBMITTED'].includes(c.status) && <Button size="small" type="text" danger onClick={() => setUpdating({ claim: c, status: 'REJECTED' })}>Rejected</Button>}
                </Space>
              ),
          },
        ]}
      />
      <FormModal<{ policy_id: number; vessel_id: string; incident: Dayjs; description: string; amount: number }>
        open={adding}
        title="Notify an insurance claim"
        okText="Notify claim"
        pending={add.isPending}
        error={add.error}
        onSubmit={add.mutate}
        onClose={() => setAdding(false)}
      >
        <Form.Item name="vessel_id" label="Vessel" rules={[{ required: true }]}>
          <Select options={vessels.data?.map((v) => ({ value: v.vessel_id, label: v.name }))} />
        </Form.Item>
        <Form.Item noStyle dependencies={['vessel_id']}>
          {({ getFieldValue }) => (
            <Form.Item name="policy_id" label="Policy" rules={[{ required: true }]}>
              <Select
                options={policies.data
                  ?.filter((p) => !p.vessel_id || p.vessel_id === getFieldValue('vessel_id'))
                  .map((p) => ({ value: p.id, label: `${COVER_LABEL[p.kind]} · ${p.insurer} (deductible ${moneyShort(p.deductible)})` }))}
              />
            </Form.Item>
          )}
        </Form.Item>
        <Form.Item name="incident" label="Date of incident" rules={[{ required: true }]}><DatePicker style={{ width: '100%' }} /></Form.Item>
        <Form.Item name="description" label="What happened" rules={[{ required: true, min: 5 }]}><Input.TextArea rows={2} /></Form.Item>
        <Form.Item name="amount" label="Loss claimed" rules={[{ required: true }]}><InputNumber {...RUPEES} /></Form.Item>
      </FormModal>
      <FormModal<{ on: Dayjs; recovered?: number }>
        open={!!updating}
        title={`${updating?.status === 'SETTLED' ? 'Settled' : updating?.status === 'REJECTED' ? 'Rejected' : 'Submitted to insurer'}: ${updating?.claim.vessel_name}`}
        okText="Save"
        danger={updating?.status === 'REJECTED'}
        initial={{ on: dayjs(), recovered: updating?.claim.expected_recovery }}
        pending={update.isPending}
        error={update.error}
        onSubmit={update.mutate}
        onClose={() => setUpdating(null)}
      >
        <Form.Item name="on" label="Date" rules={[{ required: true }]}><DatePicker style={{ width: '100%' }} /></Form.Item>
        {updating?.status === 'SETTLED' && (
          <Form.Item name="recovered" label="Amount recovered" rules={[{ required: true }]} extra="Booked against the vessel's costs as a recovery.">
            <InputNumber {...RUPEES} max={updating.claim.amount} />
          </Form.Item>
        )}
      </FormModal>
    </>
  )
}

/** Hull and machinery, P&I, crew and loss-of-hire cover for every vessel, and claims on them. */
export default function Insurance({ me }: { me: User }) {
  const policies = usePolicies()
  const claims = useInsuranceClaims()
  const vessels = useVessels()
  const rows = policies.data ?? []
  const live = rows.filter((p) => p.state === 'IN_FORCE' || p.state === 'EXPIRING')
  const covered = (vid: string, kind: string) => live.some((p) => p.kind === kind && (!p.vessel_id || p.vessel_id === vid))
  const uncovered = (vessels.data ?? []).filter((v) => !covered(v.vessel_id, 'HM') || !covered(v.vessel_id, 'PI'))
  const open = (claims.data ?? []).filter((c) => ['NOTIFIED', 'SUBMITTED'].includes(c.status))

  return (
    <>
      <PageHead title="Insurance" sub="Cover in force for each vessel, renewals and claims. Hull and machinery and P&I are needed to go on hire." />
      <ErrorAlert error={policies.error ?? claims.error} />
      <div className="metrics page-figures">
        <Metric label="Policies in force" value={live.length} note={`premium ${moneyShort(live.reduce((s, p) => s + p.premium, 0))}`} />
        <Metric label="Expiring in 45 days" value={rows.filter((p) => p.state === 'EXPIRING').length} alert={rows.some((p) => p.state === 'EXPIRING')} />
        <Metric label="Vessels without H&M or P&I" value={uncovered.length} note={uncovered.map((v) => v.name).join(', ') || 'all covered'} alert={uncovered.length > 0} />
        <Metric label="Open claims" value={open.length} note={`${moneyShort(open.reduce((s, c) => s + c.amount, 0))} claimed`} />
      </div>
      <Card>
        <Tabs items={[{ key: 'policies', label: 'Policies', children: <Policies me={me} /> }, { key: 'claims', label: `Claims${open.length ? ` (${open.length})` : ''}`, children: <Claims me={me} /> }]} />
      </Card>
      <Typography.Paragraph type="secondary" style={{ marginTop: 12 }}>
        Premiums are spread over each policy's days in the vessel's costs; a whole-fleet policy is shared equally.
      </Typography.Paragraph>
    </>
  )
}
