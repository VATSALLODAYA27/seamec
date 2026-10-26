import { Button, Card, DatePicker, Form, Modal, Space, Table } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import dayjs, { type Dayjs } from 'dayjs'
import { useState } from 'react'

import { can, fmtDate, postJson, useAction, useCertificates, type Certificate, type User } from '../api'
import { PageHead, VesselLink } from '../components/ui'
import { ErrorAlert, StateTag, stateOptions } from '../components/Tags'

function RenewDialog({ cert, onClose }: { cert: Certificate | null; onClose: () => void }) {
  const [form] = Form.useForm<{ issued_on: Dayjs; expires_on: Dayjs }>()
  const renew = useAction(
    (v: { issued_on: Dayjs; expires_on: Dayjs }) =>
      postJson(`/certificates/${cert!.id}/renew`, { issued_on: v.issued_on.format('YYYY-MM-DD'), expires_on: v.expires_on.format('YYYY-MM-DD') }),
    'Certificate renewed',
    onClose,
  )
  return (
    <Modal open={!!cert} title={`Renew: ${cert?.name} (${cert?.vessel_name})`} okText="Save renewal" confirmLoading={renew.isPending} onOk={() => form.submit()} onCancel={onClose} destroyOnHidden>
      <Form form={form} layout="vertical" requiredMark={false} onFinish={renew.mutate} initialValues={{ issued_on: dayjs(), expires_on: dayjs().add(5, 'year') }}>
        <Form.Item name="issued_on" label="Issued on" rules={[{ required: true }]}>
          <DatePicker style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item name="expires_on" label="Expires on" rules={[{ required: true }]}>
          <DatePicker style={{ width: '100%' }} />
        </Form.Item>
      </Form>
    </Modal>
  )
}

export default function Certificates({ me }: { me: User }) {
  const certs = useCertificates()
  const [renewing, setRenewing] = useState<Certificate | null>(null)
  const endorse = useAction((id: number) => postJson(`/certificates/${id}/endorse`, { on: dayjs().format('YYYY-MM-DD') }), 'Annual survey recorded')

  const columns: ColumnsType<Certificate> = [
    {
      title: 'Vessel',
      dataIndex: 'vessel_name',
      filters: [...new Set((certs.data ?? []).map((c) => c.vessel_name!))].map((v) => ({ value: v, text: v })),
      onFilter: (value, c) => c.vessel_name === value,
      render: (name, c) => <VesselLink id={c.vessel_id} name={name} />,
    },
    { title: 'Certificate', dataIndex: 'name' },
    { title: 'Authority', dataIndex: 'authority' },
    { title: 'Issued', dataIndex: 'issued_on', render: fmtDate },
    { title: 'Expires', dataIndex: 'expires_on', render: fmtDate, sorter: (a, b) => a.expires_on.localeCompare(b.expires_on), defaultSortOrder: 'ascend' },
    { title: 'Days left', dataIndex: 'days_left', align: 'right' },
    {
      title: 'Annual survey',
      key: 'survey',
      render: (_, c) =>
        !c.annual_survey ? (
          <span className="muted">Not annual</span>
        ) : c.survey ? (
          <span className={c.survey === 'OVERDUE' ? undefined : 'muted'} style={c.survey === 'OVERDUE' ? { color: '#c62828' } : undefined}>
            {c.survey === 'UPCOMING' ? 'Next window' : c.survey === 'DUE' ? 'Window open' : 'Missed'}: {fmtDate(c.survey_from)} – {fmtDate(c.survey_to)}
          </span>
        ) : (
          <span className="muted">Renewal survey next</span>
        ),
    },
    { title: 'State', dataIndex: 'state', filters: stateOptions('cert'), onFilter: (value, c) => c.state === value, render: (s) => <StateTag kind="cert" value={s} /> },
    ...(can.approve(me)
      ? [
          {
            title: '',
            key: 'renew',
            render: (_: unknown, c: Certificate) => (
              <Space size={4}>
                {(c.survey === 'DUE' || c.survey === 'OVERDUE') && (
                  <Button size="small" type="primary" ghost loading={endorse.isPending && endorse.variables === c.id} onClick={() => endorse.mutate(c.id)}>
                    Survey done today
                  </Button>
                )}
                <Button size="small" onClick={() => setRenewing(c)}>
                  Renew
                </Button>
              </Space>
            ),
          },
        ]
      : []),
  ]

  return (
    <>
    <PageHead
      title="Certificates"
      sub="Statutory and class certificates (IMO harmonized system: 5-year validity, annual survey within 3 months of each anniversary). An expired certificate, or a missed survey, stops a vessel going on hire."
    />
    <Card>
      <ErrorAlert error={certs.error} />
      <Table size="small" rowKey="id" columns={columns} dataSource={certs.data} loading={certs.isPending} pagination={{ pageSize: 25, hideOnSinglePage: true }} />
      <RenewDialog cert={renewing} onClose={() => setRenewing(null)} />
    </Card>
    </>
  )
}
