import { UserSwitchOutlined } from '@ant-design/icons'
import { Alert, Button, Card, DatePicker, Form, Modal, Popconfirm, Select, Table, Tabs, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import dayjs, { type Dayjs } from 'dayjs'
import { useState } from 'react'

import { can, fmtDate, postJson, useAction, useCrew, useCrewOnBoard, useVessels, type CrewOnBoard, type CrewPerson, type User } from '../api'
import { ErrorAlert } from '../components/Tags'
import { PageHead, VesselLink } from '../components/ui'

const LEVEL_COLOUR = { BLOCK: 'error', WARN: 'warning', INFO: 'processing' } as const

function AssignDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const crew = useCrew()
  const vessels = useVessels()
  const [form] = Form.useForm<{ crew_id: number; vessel_id: string; dates: [Dayjs, Dayjs] }>()
  const assign = useAction(
    ({ dates, ...v }: { crew_id: number; vessel_id: string; dates: [Dayjs, Dayjs] }) =>
      postJson('/crew/assignments', { ...v, sign_on: dates[0].format('YYYY-MM-DD'), relief_due: dates[1].format('YYYY-MM-DD') }),
    'Crew member assigned',
    () => {
      form.resetFields()
      onClose()
    },
  )
  const ashore = (crew.data ?? []).filter((p) => !p.on_board)
  return (
    <Modal open={open} title="Assign crew" okText="Assign" confirmLoading={assign.isPending} onOk={() => form.submit()} onCancel={onClose} destroyOnHidden>
      <ErrorAlert error={assign.error} />
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="MARIS refuses a trip past the 11-month MLC limit, or one during which any of the person's certificates would lapse."
      />
      <Form form={form} layout="vertical" requiredMark={false} onFinish={assign.mutate}>
        <Form.Item name="crew_id" label="Person (ashore)" rules={[{ required: true }]}>
          <Select
            showSearch
            optionFilterProp="label"
            options={ashore.map((p) => ({ value: p.id, label: `${p.name}: ${p.rank}` }))}
          />
        </Form.Item>
        <Form.Item name="vessel_id" label="Vessel" rules={[{ required: true }]}>
          <Select options={(vessels.data ?? []).map((v) => ({ value: v.vessel_id, label: v.name }))} />
        </Form.Item>
        <Form.Item name="dates" label="Sign on and planned relief" rules={[{ required: true }]}>
          <DatePicker.RangePicker style={{ width: '100%' }} />
        </Form.Item>
      </Form>
    </Modal>
  )
}

/** Who is on board each vessel, what needs doing about them, and who is free to send as a relief. */
export default function Crew({ me }: { me: User }) {
  const onboard = useCrewOnBoard()
  const crew = useCrew()
  const vessels = useVessels()
  const names = Object.fromEntries((vessels.data ?? []).map((v) => [v.vessel_id, v.name]))
  const [assigning, setAssigning] = useState(false)
  const signOff = useAction((id: number) => postJson(`/crew/assignments/${id}/sign-off`, { on: dayjs().format('YYYY-MM-DD') }), 'Signed off today')
  const manager = can.assignCrew(me)

  const columns: ColumnsType<CrewOnBoard> = [
    { title: 'Vessel', dataIndex: 'vessel_id', filters: Object.entries(names).map(([value, text]) => ({ value, text })), onFilter: (v, r) => r.vessel_id === v, render: (id) => <VesselLink id={id} name={names[id]} /> },
    { title: 'Name', dataIndex: 'name', render: (n, r) => <>{n}<div className="muted">{r.rank}</div></> },
    { title: 'On board', key: 'ob', render: (_, r) => <>{r.days_on_board} days<div className="muted">since {fmtDate(r.sign_on)} · MLC limit {fmtDate(r.mlc_limit)}</div></> },
    { title: 'Relief due', dataIndex: 'relief_due', render: fmtDate, sorter: (a, b) => a.relief_due.localeCompare(b.relief_due) },
    {
      title: 'Alerts',
      dataIndex: 'alerts',
      render: (alerts: CrewOnBoard['alerts']) =>
        alerts.length ? alerts.map((a) => <Tag key={a.text} color={LEVEL_COLOUR[a.level]} style={{ whiteSpace: 'normal', marginBottom: 2 }}>{a.text}</Tag>) : <span className="muted">None</span>,
    },
    ...(manager
      ? [
          {
            title: '',
            key: 'off',
            render: (_: unknown, r: CrewOnBoard) => (
              <Popconfirm title={`Sign off ${r.name} today?`} onConfirm={() => signOff.mutate(r.assignment_id)}>
                <Button size="small">Sign off</Button>
              </Popconfirm>
            ),
          },
        ]
      : []),
  ]

  const gaps = Object.entries(onboard.data?.gaps ?? {})
  return (
    <>
      <PageHead
        title="Crew"
        sub="Crew on board, reliefs and certificates. Limits used: 11 months on board without leave (MLC 2006); certificate validity as issued (for example diver medical up to 12 months under IMCA D 014, STCW medical up to 2 years)."
        actions={
          manager && (
            <Button type="primary" icon={<UserSwitchOutlined />} onClick={() => setAssigning(true)}>
              Assign
            </Button>
          )
        }
      />
      <ErrorAlert error={onboard.error ?? crew.error} />
      {gaps.length > 0 && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          message="Below minimum crew"
          description={gaps.map(([vid, g]) => `${names[vid] ?? vid}: ${g.map((x) => `${x.rank} ${x.on_board}/${x.required}`).join(', ')}`).join(' · ')}
        />
      )}
      <Card>
        <Tabs
          items={[
            { key: 'onboard', label: 'On board', children: <Table size="small" rowKey="assignment_id" columns={columns} dataSource={onboard.data?.crew} loading={onboard.isPending} pagination={{ pageSize: 25 }} /> },
            {
              key: 'pool',
              label: 'All crew',
              children: (
                <Table<CrewPerson>
                  size="small"
                  rowKey="id"
                  dataSource={crew.data}
                  pagination={{ pageSize: 25 }}
                  columns={[
                    { title: 'Name', dataIndex: 'name' },
                    { title: 'Rank', dataIndex: 'rank', filters: [...new Set((crew.data ?? []).map((p) => p.rank))].map((r) => ({ value: r, text: r })), onFilter: (v, p) => p.rank === v },
                    { title: 'Where', dataIndex: 'on_board', render: (vid) => (vid ? names[vid] : <Tag>Ashore</Tag>) },
                    {
                      title: 'Certificates',
                      dataIndex: 'certificates',
                      render: (certs: CrewPerson['certificates']) =>
                        certs.map((c) => (
                          <div key={c.name} className="muted" style={c.expires_on < dayjs().format('YYYY-MM-DD') ? { color: '#c62828' } : undefined}>
                            {c.name}: {fmtDate(c.expires_on)}
                          </div>
                        )),
                    },
                  ]}
                />
              ),
            },
          ]}
        />
      </Card>
      <AssignDialog open={assigning} onClose={() => setAssigning(false)} />
    </>
  )
}
