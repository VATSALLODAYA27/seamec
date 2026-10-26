import { FileAddOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import { Alert, Button, Card, DatePicker, Descriptions, Drawer, Flex, Form, Modal, Popconfirm, Select, Space, Table, Tag, Tooltip, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import dayjs, { type Dayjs } from 'dayjs'
import { useState } from 'react'

import { api, can, fmtDate, money, moneyShort, num, postJson, useAction, useContracts, useInvoices, type Calc, type Invoice, type User } from '../api'
import { PageHead, VesselLink } from '../components/ui'
import { ErrorAlert, StateTag, stateOptions } from '../components/Tags'

/** The breakdown of one month's hire: how the hours became money. */
function CalcTable({ calc }: { calc: Calc }) {
  return (
    <>
      <Table
        size="small"
        rowKey="label"
        pagination={false}
        dataSource={calc.lines}
        columns={[
          { title: 'Line', dataIndex: 'label' },
          { title: 'Days', dataIndex: 'days', align: 'right', render: (d) => (d === null ? '—' : num(d)) },
          { title: 'Rate', dataIndex: 'rate', align: 'right', render: money },
          { title: 'Amount', dataIndex: 'amount', align: 'right', render: money },
        ]}
        summary={() => (
          <Table.Summary.Row>
            <Table.Summary.Cell index={0} colSpan={3}>
              <b>Hire before tax</b>
            </Table.Summary.Cell>
            <Table.Summary.Cell index={1} align="right">
              <b>{money(calc.amount)}</b>
            </Table.Summary.Cell>
          </Table.Summary.Row>
        )}
      />
      <Typography.Paragraph type="secondary" style={{ marginTop: 12 }}>
        {calc.reported_days} of {calc.contract_days} contract days have an approved report. Maintenance allowance available {num(calc.allowance_hrs)} h
        {calc.allowance_accrues ? ' (including hours carried forward)' : ''}; used {num(calc.hours.breakdown_paid)} h, off hire {num(calc.hours.off_hire)} h
        {calc.allowance_left_hrs !== null && calc.allowance_left_hrs !== undefined ? `, ${num(calc.allowance_left_hrs)} h left` : ''}. Weather billed at the{' '}
        {calc.weather_billing === 'OPERATING' ? 'operating' : 'standby'} rate.
      </Typography.Paragraph>
      {!!calc.missing_dates.length && (
        <Alert type="warning" showIcon message={`${calc.missing_dates.length} day(s) not billed: no approved report`} description={calc.missing_dates.map(fmtDate).join(', ')} />
      )}
    </>
  )
}

function DraftDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const contracts = useContracts()
  const [contractNo, setContractNo] = useState<string>()
  const [month, setMonth] = useState<Dayjs>(dayjs().subtract(1, 'month'))
  const period = month.format('YYYY-MM')
  const preview = useQuery({
    queryKey: ['invoice-preview', contractNo, period],
    queryFn: () =>
      api<{ calc: Calc; amount: number; tax_label: string; tax_rate: number; tax: number; total: number }>(
        `/invoices/preview?contract_no=${encodeURIComponent(contractNo!)}&period=${period}`,
      ),
    enabled: open && !!contractNo,
  })
  const draft = useAction(() => postJson<Invoice>('/invoices', { contract_no: contractNo, period }), (inv) => `Invoice ${inv.inv_no} drafted`, onClose)

  return (
    <Modal open={open} width={760} title="Draft a hire invoice" okText="Draft invoice" okButtonProps={{ disabled: !preview.data }} confirmLoading={draft.isPending} onOk={() => draft.mutate()} onCancel={onClose} destroyOnHidden>
      <ErrorAlert error={draft.error ?? preview.error} />
      <Form layout="vertical">
        <Flex gap={16}>
          <Form.Item label="Contract" style={{ flex: 1 }}>
            <Select value={contractNo} onChange={setContractNo} options={contracts.data?.map((c) => ({ value: c.contract_no, label: `${c.contract_no} · ${c.vessel_name}` }))} />
          </Form.Item>
          <Form.Item label="Month">
            <DatePicker picker="month" value={month} onChange={(m) => m && setMonth(m)} allowClear={false} disabledDate={(d) => !d.isBefore(dayjs(), 'month')} />
          </Form.Item>
        </Flex>
      </Form>
      {preview.data && (
        <>
          <CalcTable calc={preview.data.calc} />
          <Descriptions size="small" column={3} style={{ marginTop: 12 }}>
            <Descriptions.Item label="Hire">{money(preview.data.amount)}</Descriptions.Item>
            <Descriptions.Item label={`${preview.data.tax_label} ${Math.round(preview.data.tax_rate * 100)}%`}>{money(preview.data.tax)}</Descriptions.Item>
            <Descriptions.Item label="Total">
              <b>{money(preview.data.total)}</b>
            </Descriptions.Item>
          </Descriptions>
        </>
      )}
    </Modal>
  )
}

export default function Invoices({ me }: { me: User }) {
  const invoices = useInvoices()
  const [drafting, setDrafting] = useState(false)
  const [openNo, setOpenNo] = useState<string | null>(null)
  const open = invoices.data?.find((i) => i.inv_no === openNo)
  const approve = useAction((no: string) => postJson(`/invoices/${no}/approve`), 'Invoice approved')
  const pay = useAction((no: string) => postJson(`/invoices/${no}/pay`, { paid_on: dayjs().format('YYYY-MM-DD') }), 'Payment recorded')
  const discard = useAction((no: string) => api(`/invoices/${no}`, { method: 'DELETE' }), 'Draft discarded', () => setOpenNo(null))
  const decider = can.approve(me)

  const columns: ColumnsType<Invoice> = [
    { title: 'Invoice', dataIndex: 'inv_no', render: (no) => <a onClick={() => setOpenNo(no)}>{no}</a> },
    { title: 'Month', dataIndex: 'period', render: (p) => dayjs(`${p}-01`).format('MMM YYYY') },
    { title: 'Client', dataIndex: 'client', ellipsis: true },
    { title: 'Vessel', dataIndex: 'vessel_name', render: (n, i) => <VesselLink id={i.vessel_id} name={n} /> },
    { title: 'Hire', dataIndex: 'amount', align: 'right', render: moneyShort },
    { title: 'Total with tax', dataIndex: 'total', align: 'right', render: moneyShort },
    { title: 'Due', dataIndex: 'due_date', render: (d, i) => (i.overdue ? <Tag color="error">Overdue · {fmtDate(d)}</Tag> : fmtDate(d)) },
    { title: 'Status', dataIndex: 'status', filters: stateOptions('invoice'), onFilter: (v, i) => i.status === v, render: (s) => <StateTag kind="invoice" value={s} /> },
    {
      title: 'Client timesheet',
      key: 'signoff',
      render: (_, i) => (i.signoff ? <StateTag kind="signoff" value={i.signoff.status} /> : i.signoff_required ? <span className="muted">Awaiting client</span> : <span className="muted">Not required</span>),
    },
  ]

  return (
    <>
    <PageHead
      title="Charter hire invoices"
      sub="One invoice per contract per month, worked out from the approved daily reports. Tax as set on each contract."
      actions={
        decider && (
          <Button type="primary" icon={<FileAddOutlined />} onClick={() => setDrafting(true)}>
            Draft invoice
          </Button>
        )
      }
    />
    <Card>
      <ErrorAlert error={invoices.error} />
      <Table size="small" rowKey="inv_no" columns={columns} dataSource={invoices.data} loading={invoices.isPending} pagination={{ pageSize: 20, hideOnSinglePage: true }} />
      <DraftDialog open={drafting} onClose={() => setDrafting(false)} />
      <Drawer
        open={!!open}
        width={720}
        title={open && <>{open.inv_no} <StateTag kind="invoice" value={open.status} /></>}
        onClose={() => setOpenNo(null)}
        extra={
          open &&
          decider && (
            <Space>
              {open.status === 'DRAFT' && (
                <>
                  <Popconfirm title="Discard this draft?" onConfirm={() => discard.mutate(open.inv_no)}>
                    <Button danger>Discard</Button>
                  </Popconfirm>
                  <Tooltip title={open.signoff_required && open.signoff?.status !== 'SIGNED' ? 'Needs the client to sign the timesheet first' : undefined}>
                    <Button type="primary" loading={approve.isPending} disabled={open.signoff_required && open.signoff?.status !== 'SIGNED'} onClick={() => approve.mutate(open.inv_no)}>
                      Approve
                    </Button>
                  </Tooltip>
                </>
              )}
              {open.status === 'APPROVED' && (
                <Button type="primary" loading={pay.isPending} onClick={() => pay.mutate(open.inv_no)}>
                  Record payment today
                </Button>
              )}
            </Space>
          )
        }
      >
        {open && (
          <>
            <Descriptions size="small" column={2} style={{ marginBottom: 16 }}>
              <Descriptions.Item label="Client">{open.client}</Descriptions.Item>
              <Descriptions.Item label="Contract">{open.contract_no}</Descriptions.Item>
              <Descriptions.Item label="Vessel">{open.vessel_name}</Descriptions.Item>
              <Descriptions.Item label="Month">{dayjs(`${open.period}-01`).format('MMMM YYYY')}</Descriptions.Item>
              <Descriptions.Item label="Invoice date">{fmtDate(open.invoice_date)}</Descriptions.Item>
              <Descriptions.Item label="Due">{fmtDate(open.due_date)}</Descriptions.Item>
              <Descriptions.Item label={`${open.tax_label} ${Math.round(open.tax_rate * 100)}%`}>{money(open.tax)}</Descriptions.Item>
              <Descriptions.Item label="Total">
                <b>{money(open.total)}</b>
              </Descriptions.Item>
              {open.paid_on && <Descriptions.Item label="Paid on">{fmtDate(open.paid_on)}</Descriptions.Item>}
            </Descriptions>
            {open.signoff && (
              <Alert
                type={open.signoff.status === 'SIGNED' ? 'success' : 'warning'}
                showIcon
                style={{ marginBottom: 12 }}
                message={`Timesheet ${open.signoff.status === 'SIGNED' ? 'signed' : 'disputed'} by ${open.signoff.by} on ${fmtDate(open.signoff.at)}`}
                description={open.signoff.note || undefined}
              />
            )}
            <CalcTable calc={open.calc} />
          </>
        )}
      </Drawer>
    </Card>
    </>
  )
}
