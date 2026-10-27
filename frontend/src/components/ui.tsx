import { BulbOutlined, MoonOutlined } from '@ant-design/icons'
import { Button, Form, Modal, Tooltip, Typography } from 'antd'
import { useContext, type ReactNode } from 'react'
import { Link } from 'react-router-dom'

import { DarkMode } from '../brand'
import { ErrorAlert } from './Tags'

/** The title row at the top of every page, with the page's main buttons on the right. */
export function PageHead({ title, sub, actions }: { title: ReactNode; sub?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="page-head">
      <div>
        <Typography.Title level={2}>{title}</Typography.Title>
        {sub && <Typography.Text type="secondary">{sub}</Typography.Text>}
      </div>
      {actions}
    </div>
  )
}

/** One figure in a page's metric strip; with `to`, the whole cell links to the page behind it. */
export function Metric({ label, value, note, to, alert }: { label: string; value: ReactNode; note?: ReactNode; to?: string; alert?: boolean }) {
  const body = (
    <>
      <span className="muted">{label}</span>
      <b>{value}</b>
      {note && <span className="muted">{note}</span>}
    </>
  )
  const className = `metric${alert ? ' alert' : ''}${to ? '' : ' still'}`
  return to ? <Link to={to} className={className}>{body}</Link> : <div className={className}>{body}</div>
}

/** Rupee amounts in number inputs: ₹ 12,34,567. */
export const RUPEES = {
  style: { width: '100%' },
  min: 0,
  step: 100000,
  formatter: (v?: number | string) => `₹ ${v ?? ''}`.replace(/\B(?=(\d{3})+(?!\d))/g, ','),
  parser: (v?: string) => Number((v ?? '').replace(/[₹,\s]/g, '')),
}

/**
 * A form in a dialog. The fields start from `initial` each time it opens; `onSubmit` gets the checked values.
 * Keeps every "New …" and "Edit …" dialog the same shape.
 */
export function FormModal<T extends object>({ open, title, okText, width, initial, pending, error, onSubmit, onClose, children, danger }: {
  open: boolean
  title: ReactNode
  okText: string
  width?: number
  initial?: Partial<T>
  pending?: boolean
  error?: Error | null
  onSubmit: (values: T) => void
  onClose: () => void
  children: ReactNode
  danger?: boolean
}) {
  const [form] = Form.useForm<T>()
  return (
    <Modal open={open} title={title} okText={okText} width={width ?? 560} confirmLoading={pending} okButtonProps={{ danger }} onOk={() => form.submit()} onCancel={onClose} destroyOnHidden>
      <ErrorAlert error={error} />
      <Form form={form} layout="vertical" requiredMark={false} preserve={false} initialValues={initial} onFinish={onSubmit}>
        {children}
      </Form>
    </Modal>
  )
}

export const VesselLink = ({ id, name }: { id: string; name?: string | null }) => <Link to={`/vessels/${encodeURIComponent(id)}`}>{name || id}</Link>

export function ModeButton({ light }: { light?: boolean }) {
  const { dark, flip } = useContext(DarkMode)
  return (
    <Tooltip title={dark ? 'Light mode' : 'Dark mode'}>
      <Button type="text" shape="circle" aria-label="Switch light or dark mode" icon={dark ? <BulbOutlined /> : <MoonOutlined />} onClick={flip} style={light ? { color: '#fff' } : undefined} />
    </Tooltip>
  )
}
