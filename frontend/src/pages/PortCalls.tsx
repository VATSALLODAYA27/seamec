import { MinusCircleOutlined, PlusOutlined } from '@ant-design/icons'
import { AutoComplete, Button, Card, Col, DatePicker, Drawer, Flex, Form, Input, InputNumber, Popconfirm, Row, Select, Space, Table, Tag, Typography } from 'antd'
import dayjs, { type Dayjs } from 'dayjs'
import { useState } from 'react'

import { can, fmtDate, money, moneyShort, postJson, putJson, useAction, usePortCalls, useVendors, useVessels, ymd, type DaLine, type PortCallRow, type User } from '../api'
import Documents from '../components/Documents'
import { ErrorAlert, StateTag } from '../components/Tags'
import { FormModal, Metric, PageHead, RUPEES, VesselLink } from '../components/ui'

const TYPICAL = ['Port dues', 'Pilotage', 'Towage', 'Berth hire', 'Agency fee', 'Launch hire', 'Crew transport', 'Immigration and customs']

/** PDA and FDA side by side, line by line; editable until the call is closed. */
function Account({ call, onClose, me }: { call: PortCallRow | null; onClose: () => void; me: User }) {
  const [form] = Form.useForm<{ lines: DaLine[]; advance_paid: number }>()
  const save = useAction((v: { lines: DaLine[]; advance_paid: number }) => putJson(`/port-calls/${call!.id}/account`, v), 'Account saved')
  const close = useAction(() => postJson(`/port-calls/${call!.id}/close`), 'Final account approved; port cost booked to the vessel', onClose)
  const editable = call && call.status !== 'CLOSED'
  return (
    <Drawer
      open={!!call}
      onClose={onClose}
      width={720}
      destroyOnHidden
      title={call && `${call.vessel_name} · ${call.port}`}
      extra={call && <StateTag kind="port" value={call.status} />}
      footer={
        editable && (
          <Flex justify="space-between">
            <Button type="primary" loading={save.isPending} onClick={() => form.submit()}>Save account</Button>
            {call.status === 'SAILED' && can.manage(me) && (
              <Popconfirm title="Approve the final account? Its total is booked to the vessel as a port cost." onConfirm={() => close.mutate(undefined)}>
                <Button loading={close.isPending}>Approve FDA and close</Button>
              </Popconfirm>
            )}
          </Flex>
        )
      }
    >
      {call && (
        <Form form={form} layout="vertical" requiredMark={false} disabled={!editable} initialValues={{ lines: call.lines, advance_paid: call.advance_paid }} onFinish={save.mutate}>
          <Typography.Paragraph type="secondary">
            {call.purpose}. Agent: {call.agent_name ?? 'not appointed'}. Enter the agent's estimate (PDA) before arrival and the final figures (FDA) after sailing. A line more than 10% over its estimate is flagged for a query.
          </Typography.Paragraph>
          <Row gutter={8} className="muted" style={{ marginBottom: 4 }}>
            <Col span={10}>Item</Col>
            <Col span={6}>PDA (estimate)</Col>
            <Col span={6}>FDA (final)</Col>
          </Row>
          <Form.List name="lines">
            {(fields, { add, remove }) => (
              <>
                {fields.map((f) => {
                  const line = call.lines[f.name]
                  return (
                    <Row key={f.key} gutter={8}>
                      <Form.Item name={[f.name, 'id']} hidden><Input /></Form.Item>
                      <Col span={10}>
                        <Form.Item name={[f.name, 'item']} rules={[{ required: true, message: 'Item' }]}>
                          <AutoComplete options={TYPICAL.map((t) => ({ value: t }))} filterOption />
                        </Form.Item>
                      </Col>
                      <Col span={6}>
                        <Form.Item name={[f.name, 'pda']}><InputNumber {...RUPEES} step={1000} /></Form.Item>
                      </Col>
                      <Col span={6}>
                        <Form.Item name={[f.name, 'fda']} validateStatus={line?.over ? 'warning' : undefined} help={line?.over ? 'Over estimate by more than 10%' : undefined}>
                          <InputNumber {...RUPEES} step={1000} />
                        </Form.Item>
                      </Col>
                      <Col span={2}>{editable && <Button type="text" icon={<MinusCircleOutlined />} onClick={() => remove(f.name)} aria-label="Remove line" />}</Col>
                    </Row>
                  )
                })}
                {editable && <Button type="dashed" icon={<PlusOutlined />} onClick={() => add({ id: null, item: '', pda: 0, fda: null })}>Add line</Button>}
              </>
            )}
          </Form.List>
          <Form.Item name="advance_paid" label="Advance paid to the agent" style={{ marginTop: 16, maxWidth: 260 }}>
            <InputNumber {...RUPEES} step={1000} />
          </Form.Item>
          <Space size={24} wrap>
            <span>PDA <b>{money(call.pda_total)}</b></span>
            <span>FDA <b>{money(call.fda_total)}</b>{call.variance_pct !== null && <span className="muted"> ({call.variance_pct > 0 ? '+' : ''}{call.variance_pct}%)</span>}</span>
            {call.balance !== null && <span>{call.balance >= 0 ? 'Owed to agent' : 'Refund due from agent'} <b>{money(Math.abs(call.balance))}</b></span>}
          </Space>
        </Form>
      )}
    </Drawer>
  )
}

type NewCall = { vessel_id: string; port: string; purpose: string; dates: [Dayjs, Dayjs]; agent_id?: number; lines: { item: string; pda: number }[] }

/** Port calls with the agent appointed and the disbursement account, from estimate to final. */
export default function PortCalls({ me }: { me: User }) {
  const calls = usePortCalls()
  const vessels = useVessels()
  const vendors = useVendors()
  const [adding, setAdding] = useState(false)
  const [openId, setOpenId] = useState<number | null>(null)
  const [stepping, setStepping] = useState<{ call: PortCallRow; action: 'arrived' | 'sailed' } | null>(null)
  const create = useAction(({ dates, ...v }: NewCall) => postJson('/port-calls', { ...v, eta: ymd(dates[0]), etd: ymd(dates[1]), lines: v.lines ?? [] }), 'Port call added', () => setAdding(false))
  const step = useAction(({ id, action, on }: { id: number; action: string; on: Dayjs }) => postJson(`/port-calls/${id}/${action}`, { on: ymd(on) }), 'Port call updated', () => setStepping(null))
  const appoint = useAction(({ id, agent }: { id: number; agent: number }) => postJson(`/port-calls/${id}/appoint?agent_id=${agent}`), 'Agent appointed')
  const agents = (vendors.data ?? []).filter((v) => v.category === 'AGENT' && v.approved).map((v) => ({ value: v.id, label: v.name }))
  const rows = calls.data ?? []
  const soon = rows.filter((c) => c.status === 'PLANNED' && dayjs(c.eta).diff(dayjs(), 'day') <= 30)
  const closed = rows.filter((c) => c.status === 'CLOSED' && c.variance_pct !== null)

  return (
    <>
      <PageHead title="Port calls" sub="Agents, estimated and final disbursement accounts." actions={<Button type="primary" icon={<PlusOutlined />} onClick={() => setAdding(true)}>New port call</Button>} />
      <ErrorAlert error={calls.error} />
      <div className="metrics page-figures">
        <Metric label="Calls in the next 30 days" value={soon.length} note={soon.filter((c) => !c.agent_id).length ? `${soon.filter((c) => !c.agent_id).length} without an agent` : 'agents appointed'} alert={soon.some((c) => !c.agent_id)} />
        <Metric label="In port now" value={rows.filter((c) => c.status === 'ARRIVED').length} />
        <Metric label="Waiting for the final account" value={rows.filter((c) => c.status === 'SAILED').length} />
        <Metric label="Final against estimate" value={closed.length ? `${(closed.reduce((s, c) => s + c.variance_pct!, 0) / closed.length).toFixed(1)}%` : '—'} note="average, closed calls" />
      </div>
      <Card>
        <Table<PortCallRow>
          size="small"
          rowKey="id"
          loading={calls.isPending}
          dataSource={rows}
          pagination={{ pageSize: 20 }}
          scroll={{ x: 1000 }}
          onRow={(c) => ({ onDoubleClick: () => setOpenId(c.id) })}
          columns={[
            { title: 'Vessel', dataIndex: 'vessel_id', render: (id, c) => <VesselLink id={id} name={c.vessel_name} /> },
            { title: 'Port', dataIndex: 'port', render: (p, c) => <><b>{p}</b><div className="muted">{c.purpose}</div></> },
            {
              title: 'Dates',
              key: 'd',
              render: (_, c) => (
                <>
                  {fmtDate(c.ata ?? c.eta)}
                  {(c.atd ?? c.etd) !== (c.ata ?? c.eta) && ` – ${fmtDate(c.atd ?? c.etd)}`}
                  <div className="muted">{c.ata ? 'actual' : 'expected'}</div>
                </>
              ),
            },
            {
              title: 'Agent',
              dataIndex: 'agent_name',
              render: (a, c) =>
                a ?? (
                  <Select size="small" placeholder="Appoint…" style={{ width: 170 }} options={agents} onChange={(agent) => appoint.mutate({ id: c.id, agent })} aria-label="Appoint agent" />
                ),
            },
            { title: 'PDA', dataIndex: 'pda_total', align: 'right', render: moneyShort },
            {
              title: 'FDA',
              dataIndex: 'fda_total',
              align: 'right',
              render: (f, c) =>
                f === null ? (
                  <span className="muted">—</span>
                ) : (
                  <>
                    {moneyShort(f)}
                    {c.variance_pct !== null && <div>{c.variance_pct > 10 ? <Tag color="warning">+{c.variance_pct}%</Tag> : <span className="muted">{c.variance_pct > 0 ? '+' : ''}{c.variance_pct}%</span>}</div>}
                  </>
                ),
            },
            { title: 'Status', dataIndex: 'status', render: (s) => <StateTag kind="port" value={s} /> },
            {
              title: '',
              key: 'act',
              width: 200,
              render: (_, c) => (
                <Space size={4}>
                  <Documents entity="port_call" entityKey={String(c.id)} title={`${c.vessel_name} at ${c.port}`} canUpload={can.manage(me)} defaultKind="INVOICE" />
                  <Button size="small" onClick={() => setOpenId(c.id)}>Account</Button>
                  {c.status === 'PLANNED' && <Button size="small" onClick={() => setStepping({ call: c, action: 'arrived' })}>Arrived</Button>}
                  {c.status === 'ARRIVED' && <Button size="small" onClick={() => setStepping({ call: c, action: 'sailed' })}>Sailed</Button>}
                </Space>
              ),
            },
          ]}
        />
      </Card>

      <Account call={rows.find((c) => c.id === openId) ?? null} onClose={() => setOpenId(null)} me={me} />
      <FormModal<NewCall>
        open={adding}
        title="New port call"
        okText="Add port call"
        width={680}
        initial={{ lines: [{ item: 'Port dues', pda: 0 }, { item: 'Agency fee', pda: 0 }] }}
        pending={create.isPending}
        error={create.error}
        onSubmit={create.mutate}
        onClose={() => setAdding(false)}
      >
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item name="vessel_id" label="Vessel" rules={[{ required: true }]}>
              <Select options={vessels.data?.map((v) => ({ value: v.vessel_id, label: v.name }))} />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="port" label="Port" rules={[{ required: true, min: 2 }]}>
              <Input />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="purpose" label="Purpose" rules={[{ required: true, min: 2 }]}>
              <Input placeholder="Crew change, bunkers, stores…" />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="dates" label="Expected arrival and departure" rules={[{ required: true }]}>
              <DatePicker.RangePicker style={{ width: '100%' }} />
            </Form.Item>
          </Col>
          <Col span={24}>
            <Form.Item name="agent_id" label="Agent">
              <Select allowClear options={agents} />
            </Form.Item>
          </Col>
        </Row>
        <Typography.Text strong>Estimate (PDA)</Typography.Text>
        <Form.List name="lines">
          {(fields, { add, remove }) => (
            <>
              {fields.map((f) => (
                <Row key={f.key} gutter={8} style={{ marginTop: 8 }}>
                  <Col span={14}>
                    <Form.Item name={[f.name, 'item']} rules={[{ required: true, message: 'Item' }]} style={{ marginBottom: 0 }}>
                      <AutoComplete options={TYPICAL.map((t) => ({ value: t }))} filterOption />
                    </Form.Item>
                  </Col>
                  <Col span={8}>
                    <Form.Item name={[f.name, 'pda']} style={{ marginBottom: 0 }}>
                      <InputNumber {...RUPEES} step={1000} />
                    </Form.Item>
                  </Col>
                  <Col span={2}>
                    <Button type="text" icon={<MinusCircleOutlined />} onClick={() => remove(f.name)} aria-label="Remove line" />
                  </Col>
                </Row>
              ))}
              <Button type="dashed" icon={<PlusOutlined />} onClick={() => add({ item: '', pda: 0 })} style={{ marginTop: 8 }}>Add line</Button>
            </>
          )}
        </Form.List>
      </FormModal>
      <FormModal<{ on: Dayjs }>
        open={!!stepping}
        title={stepping?.action === 'arrived' ? `${stepping.call.vessel_name} arrived at ${stepping.call.port}` : `${stepping?.call.vessel_name} sailed from ${stepping?.call.port}`}
        okText="Save"
        initial={{ on: dayjs() }}
        pending={step.isPending}
        error={step.error}
        onSubmit={(v) => step.mutate({ id: stepping!.call.id, action: stepping!.action, on: v.on })}
        onClose={() => setStepping(null)}
      >
        <Form.Item name="on" label="Date" rules={[{ required: true }]}>
          <DatePicker style={{ width: '100%' }} disabledDate={(d) => d.isAfter(dayjs(), 'day')} />
        </Form.Item>
      </FormModal>
    </>
  )
}
