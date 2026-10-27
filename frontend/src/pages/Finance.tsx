import { PlusOutlined } from '@ant-design/icons'
import { Button, Card, Col, DatePicker, Flex, Form, Input, InputNumber, Row, Segmented, Select, Table, Tabs, Tooltip, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import dayjs, { type Dayjs } from 'dayjs'
import { useState } from 'react'

import {
  COST_LINES,
  fmtDate,
  money,
  moneyShort,
  postJson,
  putJson,
  useAction,
  useBudget,
  useCosts,
  useForecast,
  usePnl,
  useVessels,
  ymd,
  type BudgetLine,
  type CostRow,
  type ForecastMonth,
  type PnlFigures,
} from '../api'
import { STATUS } from '../brand'
import { ErrorAlert } from '../components/Tags'
import { FormModal, Metric, PageHead, RUPEES, VesselLink } from '../components/ui'

const LINE_LABEL: Record<string, string> = {
  REVENUE: 'Hire revenue',
  RUNNING: 'Running cost',
  INSURANCE: 'Insurance',
  SPARES: 'Spares and stores',
  PORT: 'Port and agency',
  DRYDOCK: 'Dry dock',
  OTHER: 'Other',
  running: 'Running',
  insurance: 'Insurance',
  spares: 'Spares',
  port: 'Port',
  drydock: 'Dry dock',
  other: 'Other',
}
const Profit = ({ v }: { v: number }) => <Typography.Text strong type={v < 0 ? 'danger' : 'success'}>{moneyShort(v)}</Typography.Text>
const margin = (m: number | null) => (m === null ? <span className="muted">—</span> : <span className="muted">{m}%</span>)

// ---------------- Profit and loss ----------------

function ProfitAndLoss() {
  const [range, setRange] = useState<[Dayjs, Dayjs]>([dayjs().startOf('month'), dayjs().startOf('month')])
  const [by, setBy] = useState<'vessel' | 'contract'>('vessel')
  const pnl = usePnl(range[0].format('YYYY-MM'), range[1].format('YYYY-MM'))
  const t = pnl.data?.totals
  type Row = PnlFigures & { key: string; label: React.ReactNode; sub?: string; idle_cost?: number }
  const rows: Row[] =
    by === 'vessel'
      ? (pnl.data?.vessels ?? []).map((v) => ({ ...v, key: v.vessel_id, label: <VesselLink id={v.vessel_id} name={v.name} />, sub: v.vessel_type }))
      : (pnl.data?.contracts ?? []).map((c) => ({ ...c, key: c.contract_no, label: <b>{c.contract_no}</b>, sub: `${c.client} · ${c.vessel_name}` }))
  const columns: ColumnsType<Row> = [
    { title: by === 'vessel' ? 'Vessel' : 'Contract', dataIndex: 'label', fixed: 'left', render: (l, r) => <>{l}<div className="muted">{r.sub}</div></> },
    {
      title: 'Revenue',
      dataIndex: 'revenue',
      align: 'right',
      sorter: (a, b) => a.revenue - b.revenue,
      render: (v, r) => <>{moneyShort(v)}{r.claims > 0 && <Tooltip title={`Hire ${money(r.hire)} less ${money(r.claims)} credited on claims`}><div className="muted">after {moneyShort(r.claims)} claims</div></Tooltip>}</>,
    },
    ...COST_LINES.map((k) => ({ title: LINE_LABEL[k], dataIndex: k, align: 'right' as const, render: (v: number) => (v ? moneyShort(v) : <span className="muted">—</span>) })),
    { title: 'Total cost', dataIndex: 'cost', align: 'right', render: moneyShort },
    { title: 'Profit', dataIndex: 'profit', align: 'right', sorter: (a, b) => a.profit - b.profit, render: (v, r) => <><Profit v={v} /><div>{margin(r.margin_pct)}</div></> },
    ...(by === 'vessel' ? [{ title: 'Idle cost', dataIndex: 'idle_cost', align: 'right' as const, render: (v: number) => (v ? <Typography.Text type="warning">{moneyShort(v)}</Typography.Text> : <span className="muted">—</span>) }] : []),
  ]
  return (
    <>
      <Flex gap={12} wrap align="center" style={{ marginBottom: 16 }}>
        <DatePicker.RangePicker picker="month" value={range} allowClear={false} onChange={(v) => v?.[0] && v[1] && setRange([v[0], v[1]])} disabledDate={(d) => d.isAfter(dayjs(), 'month')} />
        <Segmented value={by} onChange={setBy} options={[{ value: 'vessel', label: 'By vessel' }, { value: 'contract', label: 'By contract' }]} />
        <Typography.Text type="secondary">To yesterday. Running cost and insurance follow the contract of each day; days off contract are idle cost.</Typography.Text>
      </Flex>
      <ErrorAlert error={pnl.error} />
      {t && (
        <div className="metrics page-figures">
          <Metric label="Revenue" value={moneyShort(t.revenue)} note={t.claims ? `after ${moneyShort(t.claims)} of claims` : 'charter hire'} />
          <Metric label="Cost" value={moneyShort(t.cost)} note={`running ${moneyShort(t.running)}`} />
          <Metric label="Profit" value={moneyShort(t.profit)} alert={t.profit < 0} note={t.margin_pct === null ? undefined : `${t.margin_pct}% margin`} />
          <Metric label="Idle cost" value={moneyShort((pnl.data?.vessels ?? []).reduce((s, v) => s + v.idle_cost, 0))} note="vessels with no contract" />
        </div>
      )}
      <Table<Row>
        size="small"
        rowKey="key"
        loading={pnl.isPending}
        dataSource={rows}
        columns={columns}
        pagination={false}
        scroll={{ x: 1200 }}
        summary={() =>
          t && by === 'vessel' && (
            <Table.Summary fixed>
              <Table.Summary.Row>
                <Table.Summary.Cell index={0}><b>Fleet</b></Table.Summary.Cell>
                <Table.Summary.Cell index={1} align="right"><b>{moneyShort(t.revenue)}</b></Table.Summary.Cell>
                {COST_LINES.map((k, i) => (
                  <Table.Summary.Cell key={k} index={2 + i} align="right">{moneyShort(t[k])}</Table.Summary.Cell>
                ))}
                <Table.Summary.Cell index={8} align="right"><b>{moneyShort(t.cost)}</b></Table.Summary.Cell>
                <Table.Summary.Cell index={9} align="right"><Profit v={t.profit} /></Table.Summary.Cell>
                <Table.Summary.Cell index={10} />
              </Table.Summary.Row>
            </Table.Summary>
          )
        }
      />
    </>
  )
}

// ---------------- Budget against actual ----------------

function Bar({ budget, actual, revenue }: { budget: number; actual: number; revenue: boolean }) {
  if (!budget) return <span className="muted">no budget</span>
  const share = actual / budget
  const good = revenue ? share >= 1 : share <= 1
  return (
    <Tooltip title={`${Math.round(share * 100)}% of budget to date`}>
      <div className="bar" style={{ width: 140 }}>
        <i style={{ width: `${Math.min(share, 1) * 100}%`, background: good ? STATUS.ok : STATUS.warn }} />
      </div>
    </Tooltip>
  )
}

function BudgetTab() {
  const vessels = useVessels()
  const [year, setYear] = useState(dayjs().year())
  const [vessel, setVessel] = useState<string>()
  const [setting, setSetting] = useState(false)
  const budget = useBudget(year, vessel)
  const save = useAction(
    (v: { vessel_ids: string[]; category: string; months: [Dayjs, Dayjs]; amount: number }) => {
      const rows = []
      for (let m = v.months[0].startOf('month'); !m.isAfter(v.months[1], 'month'); m = m.add(1, 'month')) {
        for (const vessel_id of v.vessel_ids) rows.push({ vessel_id, period: m.format('YYYY-MM'), category: v.category, amount: v.amount })
      }
      return putJson<{ saved: number }>('/finance/budget', { rows })
    },
    (out) => `${out.saved} budget lines saved`,
    () => setSetting(false),
  )
  const through = budget.data ? dayjs(`${budget.data.through}-01`).format('MMMM') : ''
  return (
    <>
      <Flex gap={12} wrap align="center" style={{ marginBottom: 16 }}>
        <Select value={year} onChange={setYear} style={{ width: 110 }} options={[-1, 0, 1].map((d) => ({ value: dayjs().year() + d, label: String(dayjs().year() + d) }))} />
        <Select allowClear placeholder="Whole fleet" value={vessel} onChange={setVessel} style={{ width: 220 }} options={vessels.data?.map((v) => ({ value: v.vessel_id, label: v.name }))} />
        <Button icon={<PlusOutlined />} onClick={() => setSetting(true)}>Set budget</Button>
      </Flex>
      <ErrorAlert error={budget.error} />
      <Table<BudgetLine>
        size="small"
        rowKey="category"
        loading={budget.isPending}
        dataSource={budget.data?.lines}
        pagination={false}
        expandable={{
          expandedRowRender: (line) => (
            <Table
              size="small"
              rowKey="period"
              pagination={false}
              dataSource={line.months}
              scroll={{ x: 700 }}
              columns={[
                { title: 'Month', dataIndex: 'period', render: (p) => dayjs(`${p}-01`).format('MMM') },
                { title: 'Budget', dataIndex: 'budget', align: 'right', render: moneyShort },
                { title: 'Actual', dataIndex: 'actual', align: 'right', render: (a) => (a === null ? <span className="muted">—</span> : moneyShort(a)) },
              ]}
            />
          ),
        }}
        columns={[
          { title: 'Line', dataIndex: 'category', render: (c) => <b>{LINE_LABEL[c]}</b> },
          { title: 'Budget for the year', dataIndex: 'budget_year', align: 'right', render: moneyShort },
          { title: `Budget to ${through}`, dataIndex: 'budget_to_date', align: 'right', render: moneyShort },
          { title: `Actual to ${through}`, dataIndex: 'actual_to_date', align: 'right', render: moneyShort },
          { title: '', key: 'bar', render: (_, l) => <Bar budget={l.budget_to_date} actual={l.actual_to_date} revenue={l.category === 'REVENUE'} /> },
          {
            title: 'Variance',
            dataIndex: 'variance',
            align: 'right',
            render: (v) => <Tooltip title={v >= 0 ? 'Better than budget' : 'Worse than budget'}><Typography.Text type={v >= 0 ? 'success' : 'danger'}>{v >= 0 ? '+' : ''}{moneyShort(v)}</Typography.Text></Tooltip>,
          },
        ]}
      />
      <FormModal<{ vessel_ids: string[]; category: string; months: [Dayjs, Dayjs]; amount: number }>
        open={setting}
        title="Set budget"
        okText="Save budget"
        initial={{ category: 'SPARES', months: [dayjs().startOf('year'), dayjs().endOf('year')], vessel_ids: vessel ? [vessel] : [] }}
        pending={save.isPending}
        error={save.error}
        onSubmit={save.mutate}
        onClose={() => setSetting(false)}
      >
        <Typography.Paragraph type="secondary">The same amount for each month and each vessel chosen. It replaces what is there.</Typography.Paragraph>
        <Form.Item name="vessel_ids" label="Vessels" rules={[{ required: true }]}>
          <Select mode="multiple" options={vessels.data?.map((v) => ({ value: v.vessel_id, label: v.name }))} />
        </Form.Item>
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item name="category" label="Line">
              <Select options={['REVENUE', 'RUNNING', 'INSURANCE', 'SPARES', 'PORT', 'DRYDOCK', 'OTHER'].map((c) => ({ value: c, label: LINE_LABEL[c] }))} />
            </Form.Item>
          </Col>
          <Col span={12}><Form.Item name="amount" label="Per month" rules={[{ required: true }]}><InputNumber {...RUPEES} /></Form.Item></Col>
        </Row>
        <Form.Item name="months" label="Months" rules={[{ required: true }]}><DatePicker.RangePicker picker="month" style={{ width: '100%' }} /></Form.Item>
      </FormModal>
    </>
  )
}

// ---------------- Forecast ----------------

function Forecast() {
  const forecast = useForecast()
  const rows = forecast.data?.months ?? []
  const peak = Math.max(1, ...rows.map((r) => Math.max(r.revenue, r.cost)))
  const t = forecast.data?.totals
  return (
    <>
      <ErrorAlert error={forecast.error} />
      {t && (
        <div className="metrics page-figures">
          <Metric label="Contracted hire, 12 months" value={moneyShort(t.contracted)} note="at each contract's recent earning rate" />
          <Metric label="Bids, weighted" value={moneyShort(t.pipeline)} note="open tenders × chance of winning" />
          <Metric label="Cost" value={moneyShort(t.cost)} />
          <Metric label="Profit" value={moneyShort(t.profit)} alert={t.profit < 0} />
        </div>
      )}
      <Table<ForecastMonth>
        size="small"
        rowKey="period"
        loading={forecast.isPending}
        dataSource={rows}
        pagination={false}
        scroll={{ x: 1100 }}
        columns={[
          { title: 'Month', dataIndex: 'period', render: (p, r) => <>{dayjs(`${p}-01`).format('MMM YYYY')}{r.days < dayjs(`${p}-01`).daysInMonth() && <div className="muted">from today</div>}</> },
          {
            title: 'Revenue and cost',
            key: 'chart',
            width: 200,
            render: (_, r) => (
              <div className="forecast-bars">
                <div className="bar"><i style={{ width: `${(100 * r.contracted) / peak}%`, background: STATUS.info }} /></div>
                {r.pipeline > 0 && <div className="bar"><i style={{ width: `${(100 * r.pipeline) / peak}%`, background: '#7D93C9' }} /></div>}
                <div className="bar"><i style={{ width: `${(100 * r.cost) / peak}%`, background: STATUS.warn }} /></div>
              </div>
            ),
          },
          { title: 'Contracted', dataIndex: 'contracted', align: 'right', render: moneyShort },
          { title: 'Bids', dataIndex: 'pipeline', align: 'right', render: (v) => (v ? moneyShort(v) : <span className="muted">—</span>) },
          { title: 'Running + insurance', key: 'ri', align: 'right', render: (_, r) => moneyShort(r.running + r.insurance) },
          { title: 'Dry dock', dataIndex: 'drydock', align: 'right', render: (v) => (v ? <Typography.Text type="warning">{moneyShort(v)}</Typography.Text> : <span className="muted">—</span>) },
          { title: 'Other', dataIndex: 'other', align: 'right', render: moneyShort },
          { title: 'Profit', dataIndex: 'profit', align: 'right', render: (v) => <Profit v={v} /> },
          {
            title: 'Against budget',
            key: 'b',
            align: 'right',
            render: (_, r) => {
              if (!r.budget_revenue && !r.budget_cost) return <span className="muted">no budget</span>
              const diff = r.profit - (r.budget_revenue - r.budget_cost) * (r.days / dayjs(`${r.period}-01`).daysInMonth())
              return <Typography.Text type={diff >= 0 ? 'success' : 'danger'}>{diff >= 0 ? '+' : ''}{moneyShort(diff)}</Typography.Text>
            },
          },
        ]}
      />
      <Flex gap={16} className="muted" style={{ marginTop: 8 }}>
        <span><i className="swatch" style={{ background: STATUS.info }} /> contracted hire</span>
        <span><i className="swatch" style={{ background: '#7D93C9' }} /> bids (weighted)</span>
        <span><i className="swatch" style={{ background: STATUS.warn }} /> cost</span>
      </Flex>
    </>
  )
}

// ---------------- Cost ledger ----------------

function Costs() {
  const vessels = useVessels()
  const [range, setRange] = useState<[Dayjs, Dayjs]>([dayjs().startOf('month'), dayjs().startOf('month')])
  const [vessel, setVessel] = useState<string>()
  const [adding, setAdding] = useState(false)
  const costs = useCosts(range[0].format('YYYY-MM'), range[1].format('YYYY-MM'), vessel)
  const add = useAction((v: { vessel_id: string; on: Dayjs; category: string; amount: number; description: string }) =>
    postJson('/finance/costs', { vessel_id: v.vessel_id, on_date: ymd(v.on), category: v.category, amount: v.amount, description: v.description }), 'Cost booked', () => setAdding(false))
  const SOURCE: Record<string, string> = { PO: 'Purchase order', TRANSFER: 'Shore stock', PORT_CALL: 'Port call', DRYDOCK: 'Dry dock', INSURANCE: 'Insurance', MANUAL: 'Entered' }
  return (
    <>
      <Flex gap={12} wrap align="center" style={{ marginBottom: 16 }}>
        <DatePicker.RangePicker picker="month" value={range} allowClear={false} onChange={(v) => v?.[0] && v[1] && setRange([v[0], v[1]])} />
        <Select allowClear placeholder="Every vessel" value={vessel} onChange={setVessel} style={{ width: 220 }} options={vessels.data?.map((v) => ({ value: v.vessel_id, label: v.name }))} />
        <Button icon={<PlusOutlined />} onClick={() => setAdding(true)}>Book a cost</Button>
        <Typography.Text type="secondary">Total {money((costs.data ?? []).reduce((s, c) => s + c.amount, 0))}</Typography.Text>
      </Flex>
      <Table<CostRow>
        size="small"
        rowKey="id"
        loading={costs.isPending}
        dataSource={costs.data}
        pagination={{ pageSize: 25 }}
        columns={[
          { title: 'Date', dataIndex: 'on_date', render: fmtDate, width: 120 },
          { title: 'Vessel', dataIndex: 'vessel_name', render: (n, c) => <>{n}<div className="muted">{c.contract_no ?? 'off contract'}</div></> },
          { title: 'Line', dataIndex: 'category', render: (c) => LINE_LABEL[c] ?? c },
          { title: 'What', dataIndex: 'description', render: (d, c) => <>{d}<div className="muted">{SOURCE[c.source] ?? c.source}{c.ref && c.ref !== 'history' ? ` · ${c.ref}` : ''}</div></> },
          { title: 'Amount', dataIndex: 'amount', align: 'right', render: (a) => <Typography.Text type={a < 0 ? 'success' : undefined}>{money(a)}</Typography.Text> },
        ]}
      />
      <FormModal<{ vessel_id: string; on: Dayjs; category: string; amount: number; description: string }>
        open={adding}
        title="Book a cost"
        okText="Book cost"
        initial={{ on: dayjs(), category: 'OTHER' }}
        pending={add.isPending}
        error={add.error}
        onSubmit={add.mutate}
        onClose={() => setAdding(false)}
      >
        <Typography.Paragraph type="secondary">For costs not booked automatically. Purchase receipts, spares sent on board, port calls, dry docks and insurance recoveries book themselves.</Typography.Paragraph>
        <Row gutter={16}>
          <Col span={12}><Form.Item name="vessel_id" label="Vessel" rules={[{ required: true }]}><Select options={vessels.data?.map((v) => ({ value: v.vessel_id, label: v.name }))} /></Form.Item></Col>
          <Col span={12}><Form.Item name="on" label="Date" rules={[{ required: true }]}><DatePicker style={{ width: '100%' }} disabledDate={(d) => d.isAfter(dayjs(), 'day')} /></Form.Item></Col>
          <Col span={12}>
            <Form.Item name="category" label="Line">
              <Select options={['SPARES', 'PORT', 'DRYDOCK', 'INSURANCE', 'OTHER'].map((c) => ({ value: c, label: LINE_LABEL[c] }))} />
            </Form.Item>
          </Col>
          <Col span={12}><Form.Item name="amount" label="Amount" rules={[{ required: true }]}><InputNumber {...RUPEES} min={undefined} /></Form.Item></Col>
        </Row>
        <Form.Item name="description" label="What for" rules={[{ required: true, min: 3 }]}><Input /></Form.Item>
      </FormModal>
    </>
  )
}

/** Profit and loss by vessel and contract, the budget, the forecast and the cost ledger. */
export default function Finance() {
  return (
    <>
      <PageHead title="Finance" sub="Profit by vessel and contract, budget against actual, and the year ahead." />
      <Card>
        <Tabs
          destroyOnHidden
          items={[
            { key: 'pnl', label: 'Profit and loss', children: <ProfitAndLoss /> },
            { key: 'budget', label: 'Budget against actual', children: <BudgetTab /> },
            { key: 'forecast', label: 'Forecast', children: <Forecast /> },
            { key: 'costs', label: 'Cost ledger', children: <Costs /> },
          ]}
        />
      </Card>
    </>
  )
}
