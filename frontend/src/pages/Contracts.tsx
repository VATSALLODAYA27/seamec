import { PlusOutlined } from '@ant-design/icons'
import { Button, Card, Col, DatePicker, Form, Input, InputNumber, Modal, Popconfirm, Row, Select, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { Dayjs } from 'dayjs'
import { useState } from 'react'

import { can, fmtDate, money, moneyShort, postJson, useAction, useContracts, useVessels, type Contract, type User } from '../api'
import { PageHead, VesselLink } from '../components/ui'
import { ErrorAlert, StateTag } from '../components/Tags'

type FormValues = Omit<Contract, 'start_date' | 'end_date' | 'bg_expiry'> & { period: [Dayjs, Dayjs]; bg_expiry?: Dayjs }

const rupees = { style: { width: '100%' }, min: 0, step: 100000, formatter: (v?: number | string) => `₹ ${v ?? ''}`.replace(/\B(?=(\d{3})+(?!\d))/g, ','), parser: (v?: string) => Number((v ?? '').replace(/[₹,\s]/g, '')) }

function NewContract({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [form] = Form.useForm<FormValues>()
  const vessels = useVessels()
  const create = useAction(
    ({ period, bg_expiry, ...v }: FormValues) =>
      postJson('/contracts', { ...v, start_date: period[0].format('YYYY-MM-DD'), end_date: period[1].format('YYYY-MM-DD'), bg_expiry: bg_expiry?.format('YYYY-MM-DD') ?? null }),
    'Contract created',
    () => {
      form.resetFields()
      onClose()
    },
  )
  return (
    <Modal open={open} width={720} title="New charter contract" okText="Create contract" confirmLoading={create.isPending} onOk={() => form.submit()} onCancel={onClose}>
      <ErrorAlert error={create.error} />
      <Form form={form} layout="vertical" requiredMark={false} onFinish={create.mutate} initialValues={{ client_signoff_required: false, breakdown_allowance_hrs: 24, allowance_accrues: true, weather_billing: 'STANDBY', tax_label: 'GST', tax_rate: 0.18, payment_terms_days: 30, mob_fee: 0, demob_fee: 0, bg_amount: 0 }}>
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item name="contract_no" label="Contract number" rules={[{ required: true }]}>
              <Input placeholder="CLIENT/DSV/2026/001" />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="client" label="Client" rules={[{ required: true }]}>
              <Input />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="vessel_id" label="Vessel" rules={[{ required: true }]} extra="A vessel with an expired critical certificate or already on contract is refused.">
              <Select options={vessels.data?.map((v) => ({ value: v.vessel_id, label: `${v.name} (${v.status.replace('_', ' ').toLowerCase()})` }))} />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="period" label="Contract period" rules={[{ required: true }]}>
              <DatePicker.RangePicker style={{ width: '100%' }} />
            </Form.Item>
          </Col>
          <Col span={24}>
            <Form.Item name="scope" label="Scope of work" rules={[{ required: true }]}>
              <Input.TextArea rows={2} />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item name="operating_rate" label="Operating rate / day" rules={[{ required: true }]}>
              <InputNumber {...rupees} />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item name="standby_rate" label="Standby rate / day" rules={[{ required: true }]}>
              <InputNumber {...rupees} />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item name="breakdown_allowance_hrs" label="Maintenance allowance h / month" tooltip="BIMCO SUPPLYTIME 2017 uses 24 hours per month, pro rata for part months.">
              <InputNumber style={{ width: '100%' }} min={0} max={744} />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item name="allowance_accrues" label="Unused allowance" tooltip="SUPPLYTIME 2017: unused hours accrue and can be used later.">
              <Select options={[{ value: true, label: 'Carries forward' }, { value: false, label: 'Resets each month' }]} />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item name="weather_billing" label="Weather hours paid at" tooltip="Charters differ: check the contract's weather / waiting clause.">
              <Select options={[{ value: 'STANDBY', label: 'Standby rate' }, { value: 'OPERATING', label: 'Operating rate' }]} />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item name="tax_label" label="Tax" rules={[{ required: true }]} tooltip="The GST rate depends on how the charter is classified; confirm with your tax adviser.">
              <Input placeholder="GST" />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item name="tax_rate" label="Tax rate">
              <Select
                options={[
                  { value: 0.18, label: '18%' },
                  { value: 0.05, label: '5%' },
                  { value: 0, label: '0% (not charged)' },
                ]}
              />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item name="client_signoff_required" label="Client timesheet sign-off" tooltip="The client's representative signs each month's timesheet in the client portal before the invoice can be approved.">
              <Select options={[{ value: false, label: 'Not required' }, { value: true, label: 'Required before invoicing' }]} />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item name="mob_fee" label="Mobilization fee">
              <InputNumber {...rupees} />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item name="demob_fee" label="Demobilization fee">
              <InputNumber {...rupees} />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item name="payment_terms_days" label="Payment terms (days)">
              <InputNumber style={{ width: '100%' }} min={0} max={180} />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="bg_amount" label="Bank guarantee amount">
              <InputNumber {...rupees} />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="bg_expiry" label="Bank guarantee expiry">
              <DatePicker style={{ width: '100%' }} />
            </Form.Item>
          </Col>
        </Row>
      </Form>
    </Modal>
  )
}

export default function Contracts({ me }: { me: User }) {
  const contracts = useContracts()
  const [adding, setAdding] = useState(false)
  const complete = useAction((no: string) => postJson(`/contracts/${encodeURIComponent(no)}/complete`), 'Contract completed')

  const columns: ColumnsType<Contract> = [
    { title: 'Contract', dataIndex: 'contract_no', render: (no, c) => <><b>{no}</b><div className="muted">{c.scope}</div></> },
    { title: 'Client', dataIndex: 'client' },
    { title: 'Vessel', dataIndex: 'vessel_name', render: (name, c) => <VesselLink id={c.vessel_id} name={name} /> },
    { title: 'Period', key: 'p', render: (_, c) => <>{fmtDate(c.start_date)} – {fmtDate(c.end_date)}{c.status === 'ACTIVE' && <div className="muted">{c.days_left} days left</div>}</> },
    { title: 'Operating / standby', key: 'r', align: 'right', render: (_, c) => `${moneyShort(c.operating_rate)} / ${moneyShort(c.standby_rate)}` },
    {
      title: 'Terms',
      key: 'terms',
      render: (_, c) => (
        <span className="muted" style={{ fontSize: 12 }}>
          Maintenance {c.breakdown_allowance_hrs} h/month{c.allowance_accrues ? ', carries forward' : ''}
          <br />
          Weather at {c.weather_billing === 'OPERATING' ? 'operating' : 'standby'} rate · {c.tax_label} {Math.round(c.tax_rate * 100)}%
          {c.client_signoff_required && (
            <>
              <br />
              Client signs the timesheet
            </>
          )}
        </span>
      ),
    },
    {
      title: 'Bank guarantee',
      key: 'bg',
      render: (_, c) =>
        c.bg_expiry ? (
          <>
            {money(c.bg_amount)}
            <div>{c.bg_days_left! <= 60 ? <Tag color="warning">expires {fmtDate(c.bg_expiry)}</Tag> : <span className="muted">to {fmtDate(c.bg_expiry)}</span>}</div>
          </>
        ) : (
          <Typography.Text type="secondary">—</Typography.Text>
        ),
    },
    { title: 'Billed', dataIndex: 'billed', align: 'right', render: moneyShort },
    { title: 'Status', dataIndex: 'status', render: (s) => <StateTag kind="contract" value={s} /> },
    ...(can.approve(me)
      ? [
          {
            title: '',
            key: 'act',
            render: (_: unknown, c: Contract) =>
              c.status === 'ACTIVE' && (
                <Popconfirm title="Mark this contract completed? The vessel becomes available." onConfirm={() => complete.mutate(c.contract_no)}>
                  <Button size="small">Complete</Button>
                </Popconfirm>
              ),
          },
        ]
      : []),
  ]

  return (
    <>
    <PageHead
      title="Charter contracts"
      sub="Day rates, paid breakdown allowance and bank guarantees. Billing reads the rates from here."
      actions={
        can.manageContracts(me) && (
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setAdding(true)}>
            New contract
          </Button>
        )
      }
    />
    <Card>
      <ErrorAlert error={contracts.error} />
      <Table size="small" rowKey="contract_no" columns={columns} dataSource={contracts.data} loading={contracts.isPending} pagination={false} scroll={{ x: 1100 }} />
      <NewContract open={adding} onClose={() => setAdding(false)} />
    </Card>
    </>
  )
}
