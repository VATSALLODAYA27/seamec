import { CheckCircleFilled, ClockCircleOutlined, CloseCircleFilled, ExclamationCircleFilled, StopFilled, ToolOutlined } from '@ant-design/icons'
import { Alert, Tag, Typography } from 'antd'
import type { ReactNode } from 'react'

import type { Role } from '../api'

// Every status has a colour, an icon and a text label, so it never depends on colour alone.

type Spec = { label: string; color?: string; icon?: ReactNode }

const STATES: Record<string, Record<string, Spec>> = {
  vessel: {
    ON_HIRE: { label: 'On hire', color: 'success', icon: <CheckCircleFilled /> },
    AVAILABLE: { label: 'Available', color: 'processing', icon: <ClockCircleOutlined /> },
    DRY_DOCK: { label: 'Dry dock', color: 'warning', icon: <ToolOutlined /> },
  },
  cert: {
    VALID: { label: 'Valid', color: 'success', icon: <CheckCircleFilled /> },
    SURVEY_DUE: { label: 'Survey window open', color: 'processing', icon: <ClockCircleOutlined /> },
    EXPIRING: { label: 'Expiring', color: 'warning', icon: <ExclamationCircleFilled /> },
    SURVEY_OVERDUE: { label: 'Survey missed', color: 'error', icon: <StopFilled /> },
    EXPIRED: { label: 'Expired', color: 'error', icon: <StopFilled /> },
  },
  contract: {
    ACTIVE: { label: 'Active', color: 'success', icon: <CheckCircleFilled /> },
    COMPLETED: { label: 'Completed', icon: <CheckCircleFilled /> },
  },
  report: {
    SUBMITTED: { label: 'Awaiting approval', color: 'processing', icon: <ClockCircleOutlined /> },
    APPROVED: { label: 'Approved', color: 'success', icon: <CheckCircleFilled /> },
    REJECTED: { label: 'Rejected', color: 'error', icon: <CloseCircleFilled /> },
  },
  job: {
    OPEN: { label: 'Open defect', color: 'error', icon: <ExclamationCircleFilled /> },
    OVERDUE: { label: 'Overdue', color: 'error', icon: <StopFilled /> },
    DUE_SOON: { label: 'Due soon', color: 'warning', icon: <ClockCircleOutlined /> },
    OK: { label: 'In date', color: 'success', icon: <CheckCircleFilled /> },
    CLOSED: { label: 'Closed', icon: <CheckCircleFilled /> },
  },
  signoff: {
    SIGNED: { label: 'Client signed', color: 'success', icon: <CheckCircleFilled /> },
    DISPUTED: { label: 'Client disputed', color: 'error', icon: <CloseCircleFilled /> },
  },
  invoice: {
    DRAFT: { label: 'Draft', icon: <ClockCircleOutlined /> },
    APPROVED: { label: 'Awaiting payment', color: 'processing', icon: <CheckCircleFilled /> },
    PAID: { label: 'Paid', color: 'success', icon: <CheckCircleFilled /> },
  },
}

export type StateKind = keyof typeof STATES

export const stateOptions = (kind: StateKind) => Object.entries(STATES[kind]).map(([value, s]) => ({ value, text: s.label, label: s.label }))

export function StateTag({ kind, value }: { kind: StateKind; value: string | null | undefined }) {
  if (!value) return <Typography.Text type="secondary">—</Typography.Text>
  const s = STATES[kind][value] ?? { label: value }
  return (
    <Tag color={s.color} icon={s.icon}>
      {s.label}
    </Tag>
  )
}

export const ROLE_LABEL: Record<Role, string> = { ops: 'Vessel / Ops', manager: 'Ops Manager', admin: 'Admin', client: 'Client representative' }

export const TYPE_LABEL: Record<string, string> = { DSV: 'Diving support vessel', OSV: 'Offshore support vessel', BARGE: 'Accommodation barge', BULK: 'Bulk carrier' }

export function ErrorAlert({ error }: { error: Error | null | undefined }) {
  return error ? <Alert type="error" showIcon message={error.message} style={{ marginBottom: 16 }} /> : null
}
