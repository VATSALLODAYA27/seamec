import {
  CheckCircleFilled,
  ClockCircleOutlined,
  CloseCircleFilled,
  EditOutlined,
  EnvironmentOutlined,
  ExclamationCircleFilled,
  FileTextOutlined,
  InboxOutlined,
  InfoCircleOutlined,
  MinusCircleOutlined,
  SendOutlined,
  StopFilled,
  ToolOutlined,
  TrophyOutlined,
} from '@ant-design/icons'
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
  tender: {
    DRAFT: { label: 'Preparing', icon: <EditOutlined /> },
    SUBMITTED: { label: 'Submitted', color: 'processing', icon: <SendOutlined /> },
    WON: { label: 'Won', color: 'success', icon: <TrophyOutlined /> },
    LOST: { label: 'Lost', color: 'error', icon: <CloseCircleFilled /> },
    WITHDRAWN: { label: 'Withdrawn', icon: <MinusCircleOutlined /> },
  },
  offhire: {
    OPEN: { label: 'Off hire now', color: 'error', icon: <ExclamationCircleFilled /> },
    ENDED: { label: 'Back on hire', color: 'warning', icon: <ClockCircleOutlined /> },
    AGREED: { label: 'Agreed with charterer', color: 'success', icon: <CheckCircleFilled /> },
  },
  claim: {
    OPEN: { label: 'Awaiting answer', color: 'warning', icon: <ClockCircleOutlined /> },
    ACCEPTED: { label: 'Accepted', color: 'processing', icon: <CheckCircleFilled /> },
    REJECTED: { label: 'Rejected', icon: <CloseCircleFilled /> },
  },
  po: {
    DRAFT: { label: 'To approve', color: 'warning', icon: <ClockCircleOutlined /> },
    APPROVED: { label: 'Approved', color: 'processing', icon: <CheckCircleFilled /> },
    ORDERED: { label: 'With vendor', color: 'processing', icon: <SendOutlined /> },
    PART_RECEIVED: { label: 'Part received', color: 'warning', icon: <InboxOutlined /> },
    RECEIVED: { label: 'Received', color: 'success', icon: <CheckCircleFilled /> },
    CANCELLED: { label: 'Cancelled', icon: <MinusCircleOutlined /> },
  },
  port: {
    PLANNED: { label: 'Planned', icon: <ClockCircleOutlined /> },
    ARRIVED: { label: 'In port', color: 'processing', icon: <EnvironmentOutlined /> },
    SAILED: { label: 'Awaiting FDA', color: 'warning', icon: <FileTextOutlined /> },
    CLOSED: { label: 'Closed', color: 'success', icon: <CheckCircleFilled /> },
  },
  drydock: {
    PLANNING: { label: 'Planning', icon: <EditOutlined /> },
    CONTRACTED: { label: 'Yard chosen', color: 'processing', icon: <CheckCircleFilled /> },
    IN_DOCK: { label: 'In dock', color: 'warning', icon: <ToolOutlined /> },
    COMPLETED: { label: 'Completed', color: 'success', icon: <CheckCircleFilled /> },
  },
  dockitem: {
    OPEN: { label: 'Open', color: 'processing', icon: <ClockCircleOutlined /> },
    DONE: { label: 'Done', color: 'success', icon: <CheckCircleFilled /> },
    DEFERRED: { label: 'Deferred', icon: <MinusCircleOutlined /> },
  },
  policy: {
    FUTURE: { label: 'Starts later', icon: <ClockCircleOutlined /> },
    IN_FORCE: { label: 'In force', color: 'success', icon: <CheckCircleFilled /> },
    EXPIRING: { label: 'Expiring', color: 'warning', icon: <ExclamationCircleFilled /> },
    EXPIRED: { label: 'Expired', color: 'error', icon: <StopFilled /> },
  },
  camera: {
    WORKING: { label: 'Working', color: 'success', icon: <CheckCircleFilled /> },
    FAULT: { label: 'Fault', color: 'warning', icon: <ExclamationCircleFilled /> },
    OFFLINE: { label: 'Offline', color: 'error', icon: <StopFilled /> },
  },
  incident: {
    OPEN: { label: 'Open', color: 'warning', icon: <ClockCircleOutlined /> },
    CLOSED: { label: 'Closed', icon: <CheckCircleFilled /> },
  },
  severity: {
    LOW: { label: 'Low', icon: <InfoCircleOutlined /> },
    MEDIUM: { label: 'Medium', color: 'warning', icon: <ExclamationCircleFilled /> },
    HIGH: { label: 'High', color: 'error', icon: <StopFilled /> },
  },
  due: {
    OK: { label: 'In date', color: 'success', icon: <CheckCircleFilled /> },
    DUE_SOON: { label: 'Due soon', color: 'warning', icon: <ClockCircleOutlined /> },
    OVERDUE: { label: 'Overdue', color: 'error', icon: <StopFilled /> },
  },
  insclaim: {
    NOTIFIED: { label: 'Notified', color: 'warning', icon: <ClockCircleOutlined /> },
    SUBMITTED: { label: 'Submitted', color: 'processing', icon: <SendOutlined /> },
    SETTLED: { label: 'Settled', color: 'success', icon: <CheckCircleFilled /> },
    REJECTED: { label: 'Rejected', color: 'error', icon: <CloseCircleFilled /> },
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
