import { AimOutlined, CheckOutlined, CloseOutlined, PlusOutlined, WarningOutlined } from '@ant-design/icons'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Alert, App as AntApp, Button, Card, Col, DatePicker, Drawer, Form, Input, InputNumber, List, Modal, Row, Select, Space, Table, Tooltip, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import dayjs, { type Dayjs } from 'dayjs'
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { can, fmtDate, formatTime, num, postJson, useAction, useEquipment, useReports, useVessels, type Report, type User } from '../api'
import { flushOutbox, isOffline, newRef, queueReport, removeQueued, useOutbox } from '../offline'
import { PageHead, VesselLink } from '../components/ui'
import { ErrorAlert, StateTag, stateOptions } from '../components/Tags'

const HOURS = [
  ['operating_hrs', 'Operating'],
  ['standby_hrs', 'Standby (client)'],
  ['weather_hrs', 'Weather'],
  ['breakdown_hrs', 'Breakdown'],
  ['transit_hrs', 'Transit'],
] as const

type FormValues = Omit<Report, 'on_date'> & { on_date: Dayjs }

/** The daily progress report form, as the vessel files it. The five hour boxes must add up to 24. */
function ReportForm({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [form] = Form.useForm<FormValues>()
  const vessels = useVessels()
  const hours = Form.useWatch([], form) ?? {}
  const total = HOURS.reduce((sum, [key]) => sum + (Number(hours[key]) || 0), 0)
  const equipment = useEquipment(hours.vessel_id ?? '')
  const broke = (Number(hours.breakdown_hrs) || 0) > 0
  const { message } = AntApp.useApp()
  const queryClient = useQueryClient()
  // Sent straight away when there is a connection; otherwise kept on this device and sent later.
  const file = useMutation({
    mutationFn: async (v: FormValues) => {
      const body = { ...v, on_date: v.on_date.format('YYYY-MM-DD'), breakdown_equipment_id: broke ? v.breakdown_equipment_id : null, client_ref: newRef() }
      try {
        await postJson('/reports', body)
        return 'sent' as const
      } catch (error) {
        if (!isOffline(error)) throw error
        queueReport(body)
        return 'queued' as const
      }
    },
    onSuccess: (how) => {
      message.success(how === 'sent' ? 'Report filed. It now waits for the ops manager.' : 'No connection: saved on this device. It is sent automatically when the link is back.')
      queryClient.invalidateQueries({ predicate: (q) => q.queryKey[0] !== 'me' })
      form.resetFields()
      onClose()
    },
  })
  const useGps = () => {
    if (!navigator.geolocation) return message.error('This device has no GPS access.')
    navigator.geolocation.getCurrentPosition(
      (p) => form.setFieldsValue({ lat: Number(p.coords.latitude.toFixed(4)), lon: Number(p.coords.longitude.toFixed(4)) }),
      (e) => message.error(`Could not read the position: ${e.message}`),
      { enableHighAccuracy: true, timeout: 15000 },
    )
  }

  return (
    <Drawer
      open={open}
      width={620}
      title="File daily progress report"
      onClose={onClose}
      extra={
        <Button type="primary" loading={file.isPending} onClick={() => form.submit()}>
          File report
        </Button>
      }
    >
      <ErrorAlert error={file.error} />
      <Form
        form={form}
        layout="vertical"
        requiredMark={false}
        onFinish={file.mutate}
        initialValues={{ on_date: dayjs().subtract(1, 'day'), operating_hrs: 24, standby_hrs: 0, weather_hrs: 0, breakdown_hrs: 0, transit_hrs: 0, dive_hrs: 0, rov_hrs: 0, fuel_received: 0 }}
      >
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item name="vessel_id" label="Vessel" rules={[{ required: true, message: 'Choose the vessel' }]}>
              <Select showSearch optionFilterProp="label" options={vessels.data?.map((v) => ({ value: v.vessel_id, label: v.name }))} />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="on_date" label="Report date" rules={[{ required: true }]}>
              <DatePicker style={{ width: '100%' }} disabledDate={(d) => d.isAfter(dayjs(), 'day')} />
            </Form.Item>
          </Col>
          <Col span={24}>
            <Form.Item name="location" label="Location / field" rules={[{ required: true, message: 'Enter the location' }]}>
              <Input />
            </Form.Item>
          </Col>
          <Col span={9}>
            <Form.Item name="lat" label="Latitude" tooltip="Noon position, decimal degrees. North is positive." rules={[{ type: 'number', min: -90, max: 90, message: '-90 to 90' }]}>
              <InputNumber style={{ width: '100%' }} step={0.0001} placeholder="19.4200" />
            </Form.Item>
          </Col>
          <Col span={9}>
            <Form.Item name="lon" label="Longitude" tooltip="Decimal degrees. East is positive." rules={[{ type: 'number', min: -180, max: 180, message: '-180 to 180' }]}>
              <InputNumber style={{ width: '100%' }} step={0.0001} placeholder="71.3300" />
            </Form.Item>
          </Col>
          <Col span={6}>
            <Form.Item label=" " tooltip="Fill the position from this device's GPS (needs location permission).">
              <Button block icon={<AimOutlined />} onClick={useGps}>
                Use GPS
              </Button>
            </Form.Item>
          </Col>
        </Row>
        <Typography.Title level={5}>The 24 hours</Typography.Title>
        <Row gutter={12}>
          {HOURS.map(([key, label]) => (
            <Col key={key} xs={12} sm={8}>
              <Form.Item name={key} label={label}>
                <InputNumber min={0} max={24} step={0.5} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          ))}
        </Row>
        <Alert
          showIcon
          type={Math.abs(total - 24) < 0.01 ? 'success' : 'warning'}
          message={`Total ${num(total)} of 24 hours`}
          description="Breakdown hours are paid only out of the contract's maintenance allowance; the rest is off hire."
          style={{ marginBottom: 16 }}
        />
        {broke && (
          <Form.Item
            name="breakdown_equipment_id"
            label="Which equipment broke down?"
            extra="A defect is raised on it in Maintenance. An open defect on critical equipment makes the vessel not hire-ready."
            rules={[{ required: (equipment.data ?? []).length > 0, message: 'Choose the equipment' }]}
          >
            <Select
              showSearch
              optionFilterProp="label"
              placeholder={hours.vessel_id ? 'Choose equipment' : 'Choose the vessel first'}
              options={(equipment.data ?? []).map((e) => ({ value: e.id, label: `${e.name}${e.critical ? ' (critical)' : ''}` }))}
            />
          </Form.Item>
        )}
        <Form.Item name="work_done" label="Work done" rules={[{ required: true, message: 'Describe the work done' }]}>
          <Input.TextArea rows={3} />
        </Form.Item>
        <Row gutter={12}>
          {(
            [
              ['dive_hrs', 'Dive hours'],
              ['rov_hrs', 'ROV hours'],
              ['pob', 'Persons on board'],
              ['fuel_rob', 'Fuel on board (m³)'],
              ['fuel_received', 'Fuel received (m³)'],
            ] as const
          ).map(([key, label]) => (
            <Col key={key} span={8}>
              <Form.Item name={key} label={label} rules={key === 'fuel_rob' ? [{ required: true, message: 'Enter fuel on board' }] : []}>
                <InputNumber min={0} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          ))}
        </Row>
        <Form.Item name="incidents" label="Incidents / near misses (optional)">
          <Input.TextArea rows={2} />
        </Form.Item>
      </Form>
    </Drawer>
  )
}

/** Reports saved on this device while there was no connection. */
function Outbox() {
  const { items, online } = useOutbox()
  const vessels = useVessels()
  const names = Object.fromEntries((vessels.data ?? []).map((v) => [v.vessel_id, v.name]))
  if (!items.length) return null
  return (
    <Card size="small" title={`Saved on this device (${items.length})`} style={{ marginBottom: 16 }} extra={online && <Button size="small" onClick={() => void flushOutbox()}>Send now</Button>}>
      <List
        size="small"
        dataSource={items}
        renderItem={(q) => (
          <List.Item actions={[<Button key="rm" size="small" danger type="link" onClick={() => removeQueued(q.id)}>Remove</Button>]}>
            <List.Item.Meta
              title={`${names[String(q.body.vessel_id)] ?? q.body.vessel_id} · ${fmtDate(String(q.body.on_date))}`}
              description={q.error ? <Typography.Text type="danger">Not accepted: {q.error}. Remove it and file it again corrected.</Typography.Text> : `Saved ${formatTime(q.savedAt)}, waiting for a connection`}
            />
          </List.Item>
        )}
      />
    </Card>
  )
}

export default function Reports({ me }: { me: User }) {
  const reports = useReports()
  const [params, setParams] = useSearchParams()
  const [rejecting, setRejecting] = useState<Report | null>(null)
  const [reason, setReason] = useState('')
  const vesselFilter = params.get('vessel')
  const statusFilter = params.get('status')
  const approve = useAction((id: number) => postJson(`/reports/${id}/approve`), 'Report approved')
  const reject = useAction(({ id, reason }: { id: number; reason: string }) => postJson(`/reports/${id}/reject`, { reason }), 'Report rejected; the vessel can file it again', () => {
    setRejecting(null)
    setReason('')
  })
  const decider = can.approve(me)

  const columns: ColumnsType<Report> = [
    { title: 'Date', dataIndex: 'on_date', width: 110, render: fmtDate },
    {
      title: 'Vessel',
      dataIndex: 'vessel_name',
      filters: [...new Set((reports.data ?? []).map((r) => r.vessel_id))].map((id) => ({ value: id, text: reports.data!.find((r) => r.vessel_id === id)!.vessel_name })),
      filteredValue: vesselFilter ? [vesselFilter] : null,
      onFilter: (value, r) => r.vessel_id === value,
      render: (name, r) => <VesselLink id={r.vessel_id} name={name} />,
    },
    { title: 'Op', dataIndex: 'operating_hrs', align: 'right', width: 55 },
    { title: 'Stby', dataIndex: 'standby_hrs', align: 'right', width: 55 },
    { title: 'Wx', dataIndex: 'weather_hrs', align: 'right', width: 55 },
    { title: 'Bkdn', dataIndex: 'breakdown_hrs', align: 'right', width: 60, render: (h) => (h ? <Typography.Text type="danger">{h}</Typography.Text> : 0) },
    { title: 'Dive', dataIndex: 'dive_hrs', align: 'right', width: 60, render: num },
    {
      title: 'Fuel used',
      dataIndex: 'fuel_used',
      align: 'right',
      width: 95,
      render: (f, r) =>
        r.fuel_alert ? (
          <Tooltip title="Unusual fuel figure: check the report">
            <Typography.Text type="warning">
              <WarningOutlined /> {num(f)}
            </Typography.Text>
          </Tooltip>
        ) : (
          num(f)
        ),
    },
    { title: 'Work done', dataIndex: 'work_done', ellipsis: true },
    { title: 'Incidents', dataIndex: 'incidents', ellipsis: true, render: (t) => (t ? <Typography.Text type="danger">{t}</Typography.Text> : '—') },
    {
      title: 'Status',
      dataIndex: 'status',
      width: 160,
      filters: stateOptions('report'),
      filteredValue: statusFilter ? [statusFilter] : null,
      onFilter: (value, r) => r.status === value,
      render: (s) => <StateTag kind="report" value={s} />,
    },
    ...(decider
      ? [
          {
            title: '',
            key: 'act',
            width: 90,
            render: (_: unknown, r: Report) =>
              r.status === 'SUBMITTED' && (
                <Space size={4}>
                  <Tooltip title="Approve">
                    <Button size="small" type="primary" icon={<CheckOutlined />} aria-label="Approve" loading={approve.isPending && approve.variables === r.id} onClick={() => approve.mutate(r.id)} />
                  </Tooltip>
                  <Tooltip title="Reject">
                    <Button size="small" danger icon={<CloseOutlined />} aria-label="Reject" onClick={() => setRejecting(r)} />
                  </Tooltip>
                </Space>
              ),
          },
        ]
      : []),
  ]

  return (
    <>
    <PageHead
      title="Daily progress reports"
      sub="Filed by each vessel every day. Approved reports are what the monthly hire invoice is built from."
      actions={
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setParams({ ...Object.fromEntries(params), new: '1' })}>
          File daily report
        </Button>
      }
    />
    <Outbox />
    <Card>
      <ErrorAlert error={reports.error} />
      <Table
        size="small"
        rowKey="id"
        columns={columns}
        dataSource={reports.data}
        loading={reports.isPending}
        pagination={{ pageSize: 25, showSizeChanger: false }}
        scroll={{ x: 1200 }}
        onChange={(_, filters) => {
          const next = new URLSearchParams()
          if (filters.vessel_name?.length === 1) next.set('vessel', String(filters.vessel_name[0]))
          if (filters.status?.length === 1) next.set('status', String(filters.status[0]))
          setParams(next)
        }}
      />
      <ReportForm open={params.get('new') === '1'} onClose={() => { params.delete('new'); setParams(params) }} />
      <Modal
        open={!!rejecting}
        title={`Reject ${rejecting?.vessel_name} report for ${fmtDate(rejecting?.on_date)}`}
        okText="Reject report"
        okButtonProps={{ danger: true, disabled: !reason.trim() }}
        confirmLoading={reject.isPending}
        onOk={() => reject.mutate({ id: rejecting!.id, reason: reason.trim() })}
        onCancel={() => setRejecting(null)}
      >
        <Typography.Paragraph type="secondary">Tell the vessel what to correct. They can file the report again.</Typography.Paragraph>
        <Input.TextArea rows={3} value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} autoFocus aria-label="Reason" />
      </Modal>
    </Card>
    </>
  )
}
