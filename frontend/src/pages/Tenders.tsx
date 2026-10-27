import { DownOutlined, PlusOutlined, WarningOutlined } from '@ant-design/icons'
import { AutoComplete, Button, Card, Col, DatePicker, Dropdown, Form, Input, InputNumber, Row, Select, Slider, Table, Tabs, Tag, Tooltip, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import dayjs, { type Dayjs } from 'dayjs'
import { useState } from 'react'

import { can, fmtDate, moneyShort, postJson, putJson, useAction, useTenders, useVessels, ymd, type Tender, type User } from '../api'
import Documents from '../components/Documents'
import { ErrorAlert, StateTag, TYPE_LABEL } from '../components/Tags'
import { FormModal, Metric, PageHead, RUPEES, VesselLink } from '../components/ui'

type BidValues = Omit<Tender, 'start_date' | 'end_date' | 'due_on'> & { period: [Dayjs, Dayjs]; due_on: Dayjs }

const pct = (v: number | null | undefined) => (v === null || v === undefined ? '—' : `${v}%`)

/** The same margin model as the server (core/commercial.py), to preview a bid while it is typed. */
function preview(v: Partial<BidValues>, dailyOpex: number) {
  if (!v.period || !v.operating_rate) return null
  const days = v.period[1].diff(v.period[0], 'day') + 1
  const share = v.operating_share ?? 0.85
  const revenue = days * (share * v.operating_rate + (1 - share) * (v.standby_rate ?? 0)) + (v.mob_fee ?? 0) + (v.demob_fee ?? 0)
  const cost = days * (dailyOpex + (v.extra_daily_cost ?? 0)) + (v.mob_cost ?? 0)
  return { days, revenue, cost, margin: revenue - cost, pct: revenue ? Math.round((1000 * (revenue - cost)) / revenue) / 10 : null }
}

function BidForm({ tender, open, onClose }: { tender: Tender | null; open: boolean; onClose: () => void }) {
  const vessels = useVessels()
  const save = useAction(
    ({ period, due_on, ...v }: BidValues) => {
      const body = { ...v, start_date: ymd(period[0]), end_date: ymd(period[1]), due_on: ymd(due_on), vessel_id: v.vessel_id ?? null }
      return tender ? putJson(`/tenders/${tender.id}`, body) : postJson('/tenders', body)
    },
    tender ? 'Bid updated' : 'Bid added',
    onClose,
  )
  const initial: Partial<BidValues> = tender
    ? { ...tender, period: [dayjs(tender.start_date), dayjs(tender.end_date)], due_on: dayjs(tender.due_on) }
    : { vessel_type: 'DSV', operating_share: 0.85, probability: 0.3, mob_fee: 0, demob_fee: 0, mob_cost: 0, extra_daily_cost: 0 }
  return (
    <FormModal<BidValues> open={open} title={tender ? `Edit bid ${tender.ref}` : 'New bid'} okText="Save bid" width={760} initial={initial} pending={save.isPending} error={save.error} onSubmit={save.mutate} onClose={onClose}>
      <Row gutter={16}>
        <Col span={8}>
          <Form.Item name="ref" label="Tender number" rules={[{ required: true }]}>
            <Input placeholder="CLIENT-T-2026-001" />
          </Form.Item>
        </Col>
        <Col span={16}>
          <Form.Item name="client" label="Client" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item name="vessel_type" label="Vessel type">
            <Select options={Object.entries(TYPE_LABEL).map(([value, label]) => ({ value, label }))} />
          </Form.Item>
        </Col>
        <Form.Item noStyle dependencies={['vessel_type']}>
          {({ getFieldValue }) => (
            <Col span={16}>
              <Form.Item name="vessel_id" label="Vessel offered" extra="Leave empty to cost it on the cheapest vessel of the type.">
                <Select allowClear options={vessels.data?.filter((v) => v.vessel_type === getFieldValue('vessel_type')).map((v) => ({ value: v.vessel_id, label: v.name }))} />
              </Form.Item>
            </Col>
          )}
        </Form.Item>
        <Col span={24}>
          <Form.Item name="scope" label="Scope" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item name="period" label="Charter period" rules={[{ required: true }]}>
            <DatePicker.RangePicker style={{ width: '100%' }} />
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item name="due_on" label="Bid due" rules={[{ required: true }]}>
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item name="operating_rate" label="Operating rate / day" rules={[{ required: true }]}>
            <InputNumber {...RUPEES} />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item name="standby_rate" label="Standby rate / day" rules={[{ required: true }]}>
            <InputNumber {...RUPEES} />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item name="operating_share" label="Expected days on operating rate" tooltip="The rest is assumed paid at the standby rate.">
            <Slider min={0} max={1} step={0.05} tooltip={{ formatter: (v) => `${Math.round((v ?? 0) * 100)}%` }} />
          </Form.Item>
        </Col>
        <Col span={6}>
          <Form.Item name="mob_fee" label="Mobilization fee">
            <InputNumber {...RUPEES} />
          </Form.Item>
        </Col>
        <Col span={6}>
          <Form.Item name="demob_fee" label="Demobilization fee">
            <InputNumber {...RUPEES} />
          </Form.Item>
        </Col>
        <Col span={6}>
          <Form.Item name="mob_cost" label="Our mobilization cost">
            <InputNumber {...RUPEES} />
          </Form.Item>
        </Col>
        <Col span={6}>
          <Form.Item name="extra_daily_cost" label="Project cost / day" tooltip="On top of the vessel's running cost: extra crew, hired equipment.">
            <InputNumber {...RUPEES} />
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item name="probability" label="Chance of winning" tooltip="Weights the bid in the forecast.">
            <Slider min={0} max={1} step={0.05} tooltip={{ formatter: (v) => `${Math.round((v ?? 0) * 100)}%` }} />
          </Form.Item>
        </Col>
        <Form.Item noStyle shouldUpdate>
          {({ getFieldsValue }) => {
            const v = getFieldsValue() as Partial<BidValues>
            const vessel = vessels.data?.find((x) => x.vessel_id === v.vessel_id)
            const opex = vessel?.daily_opex ?? Math.min(...(vessels.data ?? []).filter((x) => x.vessel_type === v.vessel_type).map((x) => x.daily_opex), Infinity)
            const m = preview(v, Number.isFinite(opex) ? opex : 0)
            return (
              <Col span={12}>
                <div className="bid-preview">
                  {m ? (
                    <>
                      <span className="muted">{m.days} days · revenue {moneyShort(m.revenue)} · cost {moneyShort(m.cost)}</span>
                      <Typography.Text strong type={m.margin < 0 ? 'danger' : 'success'} style={{ fontSize: 18 }}>
                        Margin {moneyShort(m.margin)} ({pct(m.pct)})
                      </Typography.Text>
                    </>
                  ) : (
                    <span className="muted">Enter the period and rates to see the margin.</span>
                  )}
                </div>
              </Col>
            )
          }}
        </Form.Item>
      </Row>
    </FormModal>
  )
}

export default function Tenders({ me }: { me: User }) {
  const tenders = useTenders()
  const vessels = useVessels()
  const [editing, setEditing] = useState<Tender | null | 'new'>(null)
  const [losing, setLosing] = useState<Tender | null>(null)
  const [contracting, setContracting] = useState<Tender | null>(null)
  const outcome = useAction(({ id, ...body }: { id: number; status: string; note?: string; winning_rate?: number }) => postJson(`/tenders/${id}/outcome`, body), 'Bid updated', () => setLosing(null))
  const toContract = useAction(({ id, ...body }: { id: number; contract_no: string; vessel_id?: string }) => postJson(`/tenders/${id}/contract`, body), 'Contract created from the bid', () => setContracting(null))
  const rows = tenders.data?.tenders ?? []
  const s = tenders.data?.stats
  const manage = can.manage(me)
  const dueSoon = rows.filter((t) => t.status === 'DRAFT' && dayjs(t.due_on).diff(dayjs(), 'day') <= 14)

  const columns: ColumnsType<Tender> = [
    { title: 'Bid', dataIndex: 'ref', render: (ref, t) => <><b>{ref}</b><div className="muted">{t.client} · {t.scope}</div></> },
    {
      title: 'Vessel',
      key: 'v',
      render: (_, t) => (
        <>
          {t.vessel_id ? <VesselLink id={t.vessel_id} name={t.vessel_name} /> : <span className="muted">Any {t.vessel_type}</span>}
          {t.vessel_clash && (
            <Tooltip title={t.vessel_clash}>
              <div>
                <Tag color="warning" icon={<WarningOutlined />}>Not free</Tag>
              </div>
            </Tooltip>
          )}
        </>
      ),
    },
    { title: 'Period', key: 'p', render: (_, t) => <>{fmtDate(t.start_date)} – {fmtDate(t.end_date)}<div className="muted">{t.model.days} days</div></> },
    { title: 'Day rate', key: 'r', align: 'right', render: (_, t) => <>{moneyShort(t.operating_rate)}<div className="muted">standby {moneyShort(t.standby_rate)}</div></> },
    {
      title: 'Margin',
      key: 'm',
      align: 'right',
      render: (_, t) => (
        <>
          <Typography.Text strong type={t.model.margin < 0 ? 'danger' : undefined}>{moneyShort(t.model.margin)}</Typography.Text> <span className="muted">{pct(t.model.margin_pct)}</span>
          <div className="muted">break-even {moneyShort(t.model.breakeven_rate)}/day</div>
        </>
      ),
    },
  ]
  const open: ColumnsType<Tender> = [
    ...columns,
    { title: 'Chance', dataIndex: 'probability', align: 'right', render: (p) => `${Math.round(p * 100)}%` },
    { title: 'Due', dataIndex: 'due_on', render: (d, t) => (t.status === 'DRAFT' && dayjs(d).diff(dayjs(), 'day') <= 7 ? <Tag color="error">{fmtDate(d)}</Tag> : fmtDate(d)) },
    { title: 'Status', dataIndex: 'status', render: (st) => <StateTag kind="tender" value={st} /> },
    {
      title: '',
      key: 'act',
      width: 120,
      render: (_, t) => (
        <span style={{ whiteSpace: 'nowrap' }}>
          <Documents entity="tender" entityKey={String(t.id)} title={t.ref} canUpload={manage} defaultKind="QUOTE" />
          {manage && (
            <Dropdown
              trigger={['click']}
              menu={{
                items: [
                  { key: 'edit', label: 'Edit' },
                  t.status === 'DRAFT' && { key: 'SUBMITTED', label: 'Mark submitted' },
                  t.status === 'SUBMITTED' && { key: 'WON', label: 'Won' },
                  t.status === 'SUBMITTED' && { key: 'LOST', label: 'Lost…' },
                  { key: 'WITHDRAWN', label: 'Withdraw', danger: true },
                ].filter(Boolean) as { key: string; label: string }[],
                onClick: ({ key }) =>
                  key === 'edit' ? setEditing(t) : key === 'LOST' ? setLosing(t) : outcome.mutate({ id: t.id, status: key }),
              }}
            >
              <Button size="small">
                Update <DownOutlined />
              </Button>
            </Dropdown>
          )}
        </span>
      ),
    },
  ]
  const decided: ColumnsType<Tender> = [
    ...columns,
    { title: 'Outcome', dataIndex: 'status', render: (st, t) => <><StateTag kind="tender" value={st} />{t.outcome_note && <div className="muted">{t.outcome_note}</div>}</> },
    { title: 'Winning rate', dataIndex: 'winning_rate', align: 'right', render: (w, t) => (w ? <>{moneyShort(w)}<div className="muted">ours {Math.round((100 * (t.operating_rate - w)) / w)}% higher</div></> : '—') },
    {
      title: '',
      key: 'act',
      render: (_, t) =>
        t.status === 'WON' &&
        (t.contract_no ? <span className="muted">Contract {t.contract_no}</span> : manage && <Button size="small" type="primary" onClick={() => setContracting(t)}>Make contract</Button>),
    },
  ]

  return (
    <>
      <PageHead
        title="Tenders"
        sub="Bids with their modelled margin, and how often we win."
        actions={manage && <Button type="primary" icon={<PlusOutlined />} onClick={() => setEditing('new')}>New bid</Button>}
      />
      <ErrorAlert error={tenders.error} />
      {s && (
        <div className="metrics page-figures">
          <Metric label="Open bids" value={moneyShort(s.pipeline_value)} note={`${moneyShort(s.weighted_pipeline)} weighted by chance`} />
          <Metric label="Win rate" value={pct(s.win_rate)} note={`${s.won} of ${s.decided} decided · ${pct(s.value_win_rate)} by value`} />
          <Metric label="Bids due in 14 days" value={dueSoon.length} alert={dueSoon.some((t) => dayjs(t.due_on).diff(dayjs(), 'day') <= 7)} />
          <Metric label="Price gap on lost bids" value={s.price_gap_pct === null ? '—' : `+${s.price_gap_pct}%`} note="our rate above the winner's" />
        </div>
      )}
      <Card>
        <Tabs
          items={[
            { key: 'open', label: `Open (${rows.filter((t) => ['DRAFT', 'SUBMITTED'].includes(t.status)).length})`, children: <Table size="small" rowKey="id" columns={open} dataSource={rows.filter((t) => ['DRAFT', 'SUBMITTED'].includes(t.status))} loading={tenders.isPending} pagination={false} scroll={{ x: 1100 }} /> },
            { key: 'decided', label: 'Decided', children: <Table size="small" rowKey="id" columns={decided} dataSource={rows.filter((t) => !['DRAFT', 'SUBMITTED'].includes(t.status))} pagination={{ pageSize: 20 }} scroll={{ x: 1100 }} /> },
            {
              key: 'clients',
              label: 'Win-loss by client',
              children: (
                <Table
                  size="small"
                  rowKey="client"
                  pagination={false}
                  dataSource={s?.by_client}
                  columns={[
                    { title: 'Client', dataIndex: 'client' },
                    { title: 'Bids decided', dataIndex: 'bids', align: 'right' },
                    { title: 'Won', dataIndex: 'won', align: 'right' },
                    { title: 'Win rate', dataIndex: 'win_rate', align: 'right', render: pct },
                  ]}
                />
              ),
            },
          ]}
        />
      </Card>

      <BidForm open={editing !== null} tender={editing === 'new' ? null : editing} onClose={() => setEditing(null)} />
      <FormModal<{ note: string; winning_rate?: number }>
        open={!!losing}
        title={`Lost: ${losing?.ref}`}
        okText="Record as lost"
        danger
        pending={outcome.isPending}
        onSubmit={(v) => outcome.mutate({ id: losing!.id, status: 'LOST', ...v })}
        onClose={() => setLosing(null)}
      >
        <Form.Item name="note" label="Why it was lost" rules={[{ required: true, min: 3 }]}>
          <AutoComplete options={['Price', 'Technical', 'Vessel availability', 'Client relationship'].map((r) => ({ value: r }))} placeholder="Price: about 5% above the winner" />
        </Form.Item>
        <Form.Item name="winning_rate" label="Winning operating rate, if known">
          <InputNumber {...RUPEES} />
        </Form.Item>
      </FormModal>
      <FormModal<{ contract_no: string; vessel_id?: string }>
        open={!!contracting}
        title={`Contract from ${contracting?.ref}`}
        okText="Create contract"
        initial={{ vessel_id: contracting?.vessel_id ?? undefined }}
        pending={toContract.isPending}
        error={toContract.error}
        onSubmit={(v) => toContract.mutate({ id: contracting!.id, ...v })}
        onClose={() => setContracting(null)}
      >
        <Typography.Paragraph type="secondary">The bid's client, period, rates and fees carry over. The usual checks apply: no double booking, valid certificates.</Typography.Paragraph>
        <Form.Item name="contract_no" label="Contract number" rules={[{ required: true, min: 3 }]}>
          <Input />
        </Form.Item>
        <Form.Item name="vessel_id" label="Vessel" rules={[{ required: true }]}>
          <Select options={vessels.data?.filter((v) => v.vessel_type === contracting?.vessel_type).map((v) => ({ value: v.vessel_id, label: v.name }))} />
        </Form.Item>
      </FormModal>
    </>
  )
}
