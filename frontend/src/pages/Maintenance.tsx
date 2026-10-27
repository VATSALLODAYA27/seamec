import { InboxOutlined, WarningOutlined } from '@ant-design/icons'
import { Button, Card, Dropdown, Form, Input, InputNumber, Modal, Select, Space, Table, Tabs, Tag, Tooltip, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { fmtDate, num, postJson, useAction, useEquipment, useMaintenance, useParts, useStock, useVessels, type EquipmentItem, type Job } from '../api'
import { ErrorAlert, StateTag, stateOptions } from '../components/Tags'
import { FormModal, PageHead, VesselLink } from '../components/ui'

const due = (j: Job) => {
  if (j.kind === 'DEFECT') return j.state === 'OPEN' ? `Raised ${fmtDate(j.raised_on)} · ${j.downtime_hrs} h down` : `Closed ${fmtDate(j.closed_on)}`
  const parts = []
  if (j.due_on) parts.push(`${fmtDate(j.due_on)} (${j.days_left} d)`)
  if (j.hours_left !== null) parts.push(`${num(j.hours_left)} running h left`)
  return parts.join(' or ') || '—'
}

/** Planned jobs and defects for every vessel. Breakdowns in daily reports arrive here as defects. */
export default function Maintenance() {
  const [params, setParams] = useSearchParams()
  const vessel = params.get('vessel') ?? undefined
  const vessels = useVessels()
  const jobs = useMaintenance(vessel)
  const equipment = useEquipment(vessel)
  const names = Object.fromEntries((vessels.data ?? []).map((v) => [v.vessel_id, v.name]))
  const [closing, setClosing] = useState<Job | null>(null)
  const [note, setNote] = useState('')
  const [hoursFor, setHoursFor] = useState<EquipmentItem | null>(null)
  const [hours, setHours] = useState<number | null>(null)

  const done = useAction((id: number) => postJson(`/maintenance/jobs/${id}/done`, { on: dayjs().format('YYYY-MM-DD') }), 'Job recorded as done today')
  const close = useAction(({ id, note }: { id: number; note: string }) => postJson(`/maintenance/jobs/${id}/close`, { note }), 'Defect closed', () => {
    setClosing(null)
    setNote('')
  })
  const record = useAction(({ id, hours }: { id: number; hours: number }) => postJson(`/equipment/${id}/hours`, { hours }), 'Running hours recorded', () => setHoursFor(null))
  const [spareFor, setSpareFor] = useState<Job | null>(null)
  const parts = useParts()
  const stock = useStock()
  const onBoard = (partId: number, vesselId: string) => stock.data?.find((s) => s.part_id === partId && s.location === vesselId)?.qty ?? 0
  const takeSpare = useAction(
    ({ id, part_id, qty }: { id: number; part_id: number; qty: number }) => postJson<{ status: string; shore_qty: number }>(`/maintenance/jobs/${id}/spares`, { part_id, qty }),
    (out) => (out.status === 'ISSUED' ? 'Spare issued from stock on board' : `Not on board: the job now waits for it${out.shore_qty ? ` (${out.shore_qty} at the shore warehouse; send them from Supply)` : ''}`),
    () => setSpareFor(null),
  )
  const order = useAction((requestId: number) => postJson<{ po_no: string }>(`/maintenance/spares/${requestId}/order`), (out) => `Order ${out.po_no} drafted; approve it in Supply`)
  const cancelSpare = useAction((requestId: number) => postJson(`/maintenance/spares/${requestId}/cancel`), 'Spare request cancelled')

  const columns: ColumnsType<Job> = [
    { title: 'Vessel', dataIndex: 'vessel_id', render: (id) => <VesselLink id={id} name={names[id]} /> },
    {
      title: 'Equipment',
      dataIndex: 'equipment',
      render: (e, j) => (
        <>
          {e} {j.critical && <Tag color="red">Critical</Tag>}
          {j.repeat_failure && (
            <Tooltip title="3 or more defects in 60 days: look for the root cause">
              <Tag color="volcano" icon={<WarningOutlined />}>
                Repeat failure
              </Tag>
            </Tooltip>
          )}
          <div className="muted">{j.system}</div>
        </>
      ),
    },
    { title: 'Job', dataIndex: 'title', render: (t, j) => <>{t}<div className="muted">{j.kind === 'PLANNED' ? [j.interval_days && `every ${j.interval_days} d`, j.interval_hours && `every ${j.interval_hours} h`].filter(Boolean).join(' or ') : 'Defect'}</div></> },
    { title: 'Due / status', key: 'due', render: (_, j) => <span className="muted">{due(j)}</span> },
    {
      title: 'State',
      dataIndex: 'state',
      filters: [...stateOptions('job'), { value: 'AWAITING', text: 'Waiting for a spare', label: 'Waiting for a spare' }],
      onFilter: (v, j) => (v === 'AWAITING' ? j.awaiting_spares.length > 0 : j.state === v),
      render: (s, j) => (
        <>
          <StateTag kind="job" value={s} />
          {j.awaiting_spares.length > 0 && (
            <Tooltip title={j.awaiting_spares.map((a) => `${a.part} × ${a.qty}${a.po_no ? ` (on order ${a.po_no})` : ' (not ordered yet)'}`).join('; ')}>
              <Tag color="purple" icon={<InboxOutlined />} style={{ marginTop: 4 }}>
                Waiting for spare
              </Tag>
            </Tooltip>
          )}
        </>
      ),
    },
    {
      title: '',
      key: 'act',
      render: (_, j) => {
        const waiting = j.awaiting_spares.filter((a) => !a.po_no)
        return (
          <Space size={4}>
            {j.kind === 'DEFECT' ? (
              j.state === 'OPEN' && (
                <Button size="small" onClick={() => setClosing(j)}>
                  Close
                </Button>
              )
            ) : (
              <Button size="small" loading={done.isPending && done.variables === j.id} onClick={() => done.mutate(j.id)}>
                Done today
              </Button>
            )}
            {j.state !== 'CLOSED' && (
              <Dropdown
                trigger={['click']}
                menu={{
                  items: [
                    { key: 'take', label: 'Take a spare…' },
                    ...waiting.map((a) => ({ key: `order:${a.request_id}`, label: `Order ${a.part}` })),
                    ...j.awaiting_spares.map((a) => ({ key: `cancel:${a.request_id}`, label: `Stop waiting for ${a.part}`, danger: true })),
                  ],
                  onClick: ({ key }) => {
                    const [what, id] = key.split(':')
                    if (what === 'take') setSpareFor(j)
                    else if (what === 'order') order.mutate(Number(id))
                    else cancelSpare.mutate(Number(id))
                  },
                }}
              >
                <Button size="small" icon={<InboxOutlined />} aria-label="Spares for this job" />
              </Dropdown>
            )}
          </Space>
        )
      },
    },
  ]

  return (
    <>
      <PageHead
        title="Maintenance"
        sub="Planned jobs and defects. An open defect or overdue job on critical equipment (ISM 10.3) stops the vessel going on hire; a job can wait for a spare."
        actions={
          <Select
            allowClear
            placeholder="All vessels"
            style={{ width: 220 }}
            value={vessel}
            onChange={(v) => setParams(v ? { vessel: v } : {})}
            options={(vessels.data ?? []).map((v) => ({ value: v.vessel_id, label: v.name }))}
          />
        }
      />
      <ErrorAlert error={jobs.error ?? equipment.error} />
      <Card>
        <Tabs
          items={[
            {
              key: 'jobs',
              label: 'Jobs and defects',
              children: <Table size="small" rowKey="id" columns={columns} dataSource={jobs.data?.filter((j) => j.state !== 'CLOSED')} loading={jobs.isPending} pagination={{ pageSize: 25 }} />,
            },
            {
              key: 'history',
              label: 'Closed defects',
              children: <Table size="small" rowKey="id" columns={columns.slice(0, 4)} dataSource={jobs.data?.filter((j) => j.state === 'CLOSED')} pagination={{ pageSize: 25 }} expandable={{ expandedRowRender: (j) => j.note || 'No note' }} />,
            },
            {
              key: 'equipment',
              label: 'Equipment',
              children: (
                <Table<EquipmentItem>
                  size="small"
                  rowKey="id"
                  dataSource={equipment.data}
                  pagination={{ pageSize: 25 }}
                  columns={[
                    { title: 'Vessel', dataIndex: 'vessel_id', render: (id) => names[id] ?? id },
                    { title: 'Equipment', dataIndex: 'name', render: (n, e) => <>{n} {e.critical && <Tag color="red">Critical</Tag>}</> },
                    { title: 'System', dataIndex: 'system' },
                    { title: 'Running hours', dataIndex: 'running_hours', align: 'right', render: (h, e) => <>{num(h)}<div className="muted">read {fmtDate(e.hours_updated_on)}</div></> },
                    { title: '', key: 'h', render: (_, e) => <Button size="small" onClick={() => { setHoursFor(e); setHours(e.running_hours) }}>Hours</Button> },
                  ]}
                />
              ),
            },
          ]}
        />
      </Card>
      <Modal
        open={!!closing}
        title={`Close defect: ${closing?.equipment}`}
        okText="Close defect"
        okButtonProps={{ disabled: note.trim().length < 3 }}
        confirmLoading={close.isPending}
        onOk={() => close.mutate({ id: closing!.id, note: note.trim() })}
        onCancel={() => setClosing(null)}
      >
        <Typography.Paragraph type="secondary">What was found and what was done (kept as the repair record).</Typography.Paragraph>
        <Input.TextArea rows={3} value={note} onChange={(e) => setNote(e.target.value)} maxLength={1000} aria-label="Repair note" />
      </Modal>
      <FormModal<{ part_id: number; qty: number }>
        open={!!spareFor}
        title={`Spare for: ${spareFor?.equipment}`}
        okText="Take spare"
        initial={{ qty: 1 }}
        pending={takeSpare.isPending}
        error={takeSpare.error}
        onSubmit={(v) => takeSpare.mutate({ id: spareFor!.id, ...v })}
        onClose={() => setSpareFor(null)}
      >
        <Typography.Paragraph type="secondary">If the vessel has it, it is issued now. If not, the job waits for it and shows as waiting for a spare until it arrives on board.</Typography.Paragraph>
        <Form.Item name="part_id" label="Part" rules={[{ required: true }]}>
          <Select
            showSearch
            optionFilterProp="label"
            options={parts.data?.map((p) => ({ value: p.id, label: `${p.name} (${p.part_no}) · ${onBoard(p.id, spareFor?.vessel_id ?? '')} on board` }))}
          />
        </Form.Item>
        <Form.Item name="qty" label="Quantity" rules={[{ required: true }]}>
          <InputNumber min={0.001} style={{ width: '100%' }} />
        </Form.Item>
      </FormModal>
      <Modal
        open={!!hoursFor}
        title={`Running hours: ${hoursFor?.name}`}
        okText="Save reading"
        confirmLoading={record.isPending}
        okButtonProps={{ disabled: hours === null || (hoursFor !== null && hours < hoursFor.running_hours) }}
        onOk={() => record.mutate({ id: hoursFor!.id, hours: hours! })}
        onCancel={() => setHoursFor(null)}
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <Typography.Text type="secondary">Counter reading; it can only go up (last {num(hoursFor?.running_hours)} h).</Typography.Text>
          <InputNumber style={{ width: '100%' }} min={hoursFor?.running_hours ?? 0} value={hours} onChange={setHours} aria-label="Running hours" />
        </Space>
      </Modal>
    </>
  )
}
