import { CheckOutlined, PlusOutlined, TrophyFilled } from '@ant-design/icons'
import { Button, Card, Col, DatePicker, Drawer, Empty, Flex, Form, Input, InputNumber, Row, Segmented, Select, Skeleton, Space, Switch, Table, Tabs, Tag, Typography } from 'antd'
import dayjs, { type Dayjs } from 'dayjs'
import { useState } from 'react'

import { can, fmtDate, moneyShort, postJson, putJson, useAction, useDryDocks, useVendors, useVessels, ymd, type DockItem, type DryDockRow, type User } from '../api'
import { STATUS } from '../brand'
import Documents from '../components/Documents'
import { ErrorAlert, StateTag } from '../components/Tags'
import { FormModal, PageHead, RUPEES, VesselLink } from '../components/ui'

const CATEGORIES: Record<DockItem['category'], string> = {
  HULL: 'Hull',
  MACHINERY: 'Machinery',
  CLASS: 'Class survey',
  ELECTRICAL: 'Electrical',
  SAFETY: 'Safety',
  DIVING: 'Diving system',
  OTHER: 'Other',
}
const TONE: Record<DryDockRow['status'], string> = { PLANNING: STATUS.info, CONTRACTED: STATUS.info, IN_DOCK: STATUS.warn, COMPLETED: STATUS.ok }

function Spend({ budget, actual }: { budget: number; actual: number }) {
  const share = budget ? Math.min(actual / budget, 1.5) : 0
  const over = actual > budget
  return (
    <div>
      <Flex justify="space-between" className="muted">
        <span>Spent {moneyShort(actual)}</span>
        <span>budget {moneyShort(budget)}</span>
      </Flex>
      <div className="bar">
        <i style={{ width: `${Math.min(share, 1) * 100}%`, background: over ? STATUS.bad : STATUS.ok }} />
      </div>
    </div>
  )
}

function ProjectCard({ p, onOpen }: { p: DryDockRow; onOpen: () => void }) {
  return (
    <Card size="small" className="project-card" style={{ ['--status' as string]: TONE[p.status] }} onClick={onOpen}>
      <Flex justify="space-between" align="start" gap={8}>
        <div>
          <Typography.Text strong style={{ fontSize: 15 }}>{p.vessel_name}</Typography.Text>
          <div className="muted">{p.title}</div>
        </div>
        <StateTag kind="drydock" value={p.status} />
      </Flex>
      <span>
        {fmtDate(p.actual_start ?? p.planned_start)} – {fmtDate(p.actual_end ?? p.planned_end)}
        <span className="muted"> · {p.yard ?? `${p.quotes.length} quote${p.quotes.length === 1 ? '' : 's'}, no yard chosen`}</span>
      </span>
      <Spend budget={p.budget} actual={p.actual} />
      <span className="muted">{p.items_done} of {p.items.length} work items done{p.items_open ? `, ${p.items_open} open` : ''}</span>
    </Card>
  )
}

type ItemValues = Omit<DockItem, 'id'>

function WorkList({ p, editable }: { p: DryDockRow; editable: boolean }) {
  const [editing, setEditing] = useState<DockItem | null | 'new'>(null)
  const current = editing === 'new' ? null : editing
  const save = useAction((v: ItemValues) => (current ? putJson(`/drydock/items/${current.id}`, v) : postJson(`/drydock/${p.id}/items`, v)), 'Work item saved', () => setEditing(null))
  return (
    <>
      <Table<DockItem>
        size="small"
        rowKey="id"
        pagination={false}
        dataSource={p.items}
        title={() => editable && <Button icon={<PlusOutlined />} onClick={() => setEditing('new')}>Add work item</Button>}
        onRow={(i) => ({ onClick: () => editable && setEditing(i), style: editable ? { cursor: 'pointer' } : undefined })}
        columns={[
          { title: 'Work', dataIndex: 'description', render: (d, i) => <>{d}<div className="muted">{CATEGORIES[i.category]}</div></> },
          { title: 'Budget', dataIndex: 'budget', align: 'right', render: moneyShort },
          { title: 'Actual', dataIndex: 'actual', align: 'right', render: (a, i) => (i.status === 'OPEN' && !a ? <span className="muted">—</span> : <Typography.Text type={a > i.budget ? 'danger' : undefined}>{moneyShort(a)}</Typography.Text>) },
          { title: 'Status', dataIndex: 'status', render: (s) => <StateTag kind="dockitem" value={s} /> },
        ]}
        summary={(rows) => {
          const live = rows.filter((i) => i.status !== 'DEFERRED')
          return (
            <Table.Summary.Row>
              <Table.Summary.Cell index={0}><b>Total (excluding deferred)</b></Table.Summary.Cell>
              <Table.Summary.Cell index={1} align="right"><b>{moneyShort(live.reduce((s, i) => s + i.budget, 0))}</b></Table.Summary.Cell>
              <Table.Summary.Cell index={2} align="right"><b>{moneyShort(live.reduce((s, i) => s + i.actual, 0))}</b></Table.Summary.Cell>
              <Table.Summary.Cell index={3} />
            </Table.Summary.Row>
          )
        }}
      />
      <FormModal<ItemValues>
        open={editing !== null}
        title={current ? 'Edit work item' : 'New work item'}
        okText="Save"
        initial={current ?? { category: 'HULL', budget: 0, actual: 0, status: 'OPEN' }}
        pending={save.isPending}
        error={save.error}
        onSubmit={save.mutate}
        onClose={() => setEditing(null)}
      >
        <Form.Item name="description" label="Work" rules={[{ required: true, min: 2 }]}><Input /></Form.Item>
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item name="category" label="Category"><Select options={Object.entries(CATEGORIES).map(([value, label]) => ({ value, label }))} /></Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="status" label="Status"><Select options={[{ value: 'OPEN', label: 'Open' }, { value: 'DONE', label: 'Done' }, { value: 'DEFERRED', label: 'Deferred to next docking' }]} /></Form.Item>
          </Col>
          <Col span={12}><Form.Item name="budget" label="Budget"><InputNumber {...RUPEES} /></Form.Item></Col>
          <Col span={12}><Form.Item name="actual" label="Actual"><InputNumber {...RUPEES} /></Form.Item></Col>
        </Row>
      </FormModal>
    </>
  )
}

function Quotes({ p, editable }: { p: DryDockRow; editable: boolean }) {
  const vendors = useVendors()
  const [adding, setAdding] = useState(false)
  const add = useAction((v: { vendor_id: number; price: number; days: number; deviation_cost: number; note?: string }) => postJson(`/drydock/${p.id}/quotes`, v), 'Quote added', () => setAdding(false))
  const choose = useAction((quote: number) => postJson(`/drydock/${p.id}/select/${quote}`), 'Yard chosen')
  return (
    <>
      <Typography.Paragraph type="secondary">
        Ranked on full cost: the yard's price, getting there and back, and the vessel's running cost for every day in dock. The cheapest price is not always the cheapest docking.
      </Typography.Paragraph>
      <Table
        size="small"
        rowKey="id"
        pagination={false}
        dataSource={p.quotes}
        title={() => editable && p.status !== 'IN_DOCK' && <Button icon={<PlusOutlined />} onClick={() => setAdding(true)}>Add quote</Button>}
        columns={[
          { title: '', dataIndex: 'rank', width: 40, render: (r) => (r === 1 ? <TrophyFilled style={{ color: STATUS.ok }} aria-label="Lowest full cost" /> : r) },
          { title: 'Yard', dataIndex: 'yard', render: (y, q) => <>{y} {q.chosen && <Tag color="success">Chosen</Tag>}{q.note && <div className="muted">{q.note}</div>}</> },
          { title: 'Price', dataIndex: 'price', align: 'right', render: moneyShort },
          { title: 'Days', dataIndex: 'days', align: 'right' },
          { title: 'Time cost', dataIndex: 'time_cost', align: 'right', render: moneyShort },
          { title: 'Deviation', dataIndex: 'deviation_cost', align: 'right', render: moneyShort },
          { title: 'Full cost', dataIndex: 'evaluated', align: 'right', render: (e) => <b>{moneyShort(e)}</b> },
          { title: '', key: 'act', render: (_, q) => editable && !q.chosen && p.status !== 'IN_DOCK' && <Button size="small" icon={<CheckOutlined />} onClick={() => choose.mutate(q.id)}>Choose</Button> },
        ]}
      />
      <FormModal<{ vendor_id: number; price: number; days: number; deviation_cost: number; note?: string }>
        open={adding}
        title="Yard quote"
        okText="Add quote"
        initial={{ deviation_cost: 0 }}
        pending={add.isPending}
        error={add.error}
        onSubmit={add.mutate}
        onClose={() => setAdding(false)}
      >
        <Form.Item name="vendor_id" label="Yard" rules={[{ required: true }]} extra="Shipyards come from the vendor list (type Shipyard).">
          <Select options={vendors.data?.filter((v) => v.category === 'YARD').map((v) => ({ value: v.id, label: v.name }))} />
        </Form.Item>
        <Row gutter={16}>
          <Col span={12}><Form.Item name="price" label="Price" rules={[{ required: true }]}><InputNumber {...RUPEES} /></Form.Item></Col>
          <Col span={12}><Form.Item name="days" label="Days in dock" rules={[{ required: true }]}><InputNumber min={1} max={365} style={{ width: '100%' }} /></Form.Item></Col>
          <Col span={24}><Form.Item name="deviation_cost" label="Deviation cost" tooltip="Steaming there and back: fuel, extra port costs."><InputNumber {...RUPEES} /></Form.Item></Col>
        </Row>
        <Form.Item name="note" label="Note"><Input maxLength={500} /></Form.Item>
      </FormModal>
    </>
  )
}

function Project({ p, me, onClose }: { p: DryDockRow | null; me: User; onClose: () => void }) {
  const [stepping, setStepping] = useState<'start' | 'complete' | null>(null)
  const step = useAction((v: { on: Dayjs }) => postJson(`/drydock/${p!.id}/${stepping}`, { on: ymd(v.on) }), stepping === 'start' ? 'Vessel is in dock' : 'Dry dock completed', () => setStepping(null))
  const editable = !!p && p.status !== 'COMPLETED' && can.manage(me)
  return (
    <Drawer
      open={!!p}
      onClose={onClose}
      width={860}
      destroyOnHidden
      title={p && <>{p.vessel_name} · {p.title}</>}
      extra={
        p && (
          <Space>
            <Documents entity="drydock" entityKey={String(p.id)} title={p.title} canUpload={can.manage(me)} defaultKind="QUOTE" />
            {editable && p.status === 'CONTRACTED' && <Button type="primary" onClick={() => setStepping('start')}>Vessel in dock</Button>}
            {editable && p.status === 'IN_DOCK' && <Button type="primary" onClick={() => setStepping('complete')}>Complete docking</Button>}
            <StateTag kind="drydock" value={p.status} />
          </Space>
        )
      }
    >
      {p && (
        <>
          <Flex gap={32} wrap style={{ marginBottom: 16 }}>
            <span>Vessel <VesselLink id={p.vessel_id} name={p.vessel_name} /></span>
            <span>Planned {fmtDate(p.planned_start)} – {fmtDate(p.planned_end)}</span>
            {p.actual_start && <span>In dock from {fmtDate(p.actual_start)}{p.actual_end && ` to ${fmtDate(p.actual_end)}`}</span>}
            <span>Yard {p.yard ?? <span className="muted">not chosen</span>}</span>
          </Flex>
          <div style={{ maxWidth: 420, marginBottom: 16 }}>
            <Spend budget={p.budget} actual={p.actual} />
          </div>
          <Tabs
            items={[
              { key: 'work', label: `Work list (${p.items.length})`, children: <WorkList p={p} editable={editable} /> },
              { key: 'yards', label: `Yard quotes (${p.quotes.length})`, children: <Quotes p={p} editable={editable} /> },
            ]}
          />
        </>
      )}
      <FormModal<{ on: Dayjs }>
        open={!!stepping}
        title={stepping === 'start' ? 'The vessel went into dock on' : 'The vessel came out of dock on'}
        okText="Save"
        initial={{ on: dayjs() }}
        pending={step.isPending}
        error={step.error}
        onSubmit={step.mutate}
        onClose={() => setStepping(null)}
      >
        {stepping === 'complete' && (
          <Typography.Paragraph type="secondary">
            Every work item must be done or deferred. The vessel goes back to available (or on hire), {p?.bottom_survey ? 'the bottom survey is recorded on this date, ' : ''}and the actual cost is booked to it.
          </Typography.Paragraph>
        )}
        <Form.Item name="on" label="Date" rules={[{ required: true }]}>
          <DatePicker style={{ width: '100%' }} disabledDate={(d) => d.isAfter(dayjs(), 'day')} />
        </Form.Item>
      </FormModal>
    </Drawer>
  )
}

/** Each docking as a project: the work list with budget against actual, yard quotes compared on full cost, and the dates. */
export default function DryDock({ me }: { me: User }) {
  const projects = useDryDocks()
  const vessels = useVessels()
  const [view, setView] = useState<'open' | 'done'>('open')
  const [openId, setOpenId] = useState<number | null>(null)
  const [adding, setAdding] = useState(false)
  const create = useAction(
    ({ dates, ...v }: { vessel_id: string; title: string; dates: [Dayjs, Dayjs]; bottom_survey: boolean }) => postJson('/drydock', { ...v, planned_start: ymd(dates[0]), planned_end: ymd(dates[1]) }),
    'Dry dock project started',
    () => setAdding(false),
  )
  const stage = { IN_DOCK: 0, CONTRACTED: 1, PLANNING: 2, COMPLETED: 3 }
  const rows = (projects.data ?? [])
    .filter((p) => (view === 'open' ? p.status !== 'COMPLETED' : p.status === 'COMPLETED'))
    .sort((a, b) => stage[a.status] - stage[b.status] || a.planned_start.localeCompare(b.planned_start))

  return (
    <>
      <PageHead
        title="Dry dock"
        sub="Dockings planned and in hand: work list, yard choice, budget against actual."
        actions={can.manage(me) && <Button type="primary" icon={<PlusOutlined />} onClick={() => setAdding(true)}>New dry dock</Button>}
      />
      <ErrorAlert error={projects.error} />
      <Segmented style={{ marginBottom: 16 }} value={view} onChange={setView} options={[{ value: 'open', label: 'In hand' }, { value: 'done', label: 'Completed' }]} />
      <Skeleton loading={projects.isPending} active>
        {rows.length ? (
          <Row gutter={[16, 16]}>
            {rows.map((p) => (
              <Col key={p.id} xs={24} md={12} xl={8}>
                <ProjectCard p={p} onOpen={() => setOpenId(p.id)} />
              </Col>
            ))}
          </Row>
        ) : (
          <Card><Empty description={view === 'open' ? 'No dockings in hand' : 'None completed yet'} /></Card>
        )}
      </Skeleton>
      <Project p={(projects.data ?? []).find((p) => p.id === openId) ?? null} me={me} onClose={() => setOpenId(null)} />
      <FormModal<{ vessel_id: string; title: string; dates: [Dayjs, Dayjs]; bottom_survey: boolean }>
        open={adding}
        title="New dry dock"
        okText="Create"
        initial={{ bottom_survey: true, title: 'Bottom survey docking' }}
        pending={create.isPending}
        error={create.error}
        onSubmit={create.mutate}
        onClose={() => setAdding(false)}
      >
        <Form.Item name="vessel_id" label="Vessel" rules={[{ required: true }]}>
          <Select options={vessels.data?.map((v) => ({ value: v.vessel_id, label: v.name }))} />
        </Form.Item>
        <Form.Item name="title" label="Title" rules={[{ required: true, min: 3 }]}><Input /></Form.Item>
        <Form.Item name="dates" label="Planned in dock" rules={[{ required: true }]}><DatePicker.RangePicker style={{ width: '100%' }} /></Form.Item>
        <Form.Item name="bottom_survey" label="Includes the bottom survey" valuePropName="checked" extra="Completing the docking then records the survey date (the 36-month limit restarts).">
          <Switch />
        </Form.Item>
      </FormModal>
    </>
  )
}
