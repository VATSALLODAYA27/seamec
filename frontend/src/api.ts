// MARIS: types, queries and actions. Field names follow the backend's JSON.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App as AntApp } from 'antd'
import dayjs from 'dayjs'

import { forget, remembered } from './offline'

export type Role = 'ops' | 'manager' | 'admin' | 'client'

export interface User {
  username: string
  name: string
  role: Role
}

export interface Account extends User {
  active: boolean
  client_name: string | null
}

export interface AuditEntry {
  id: number
  at: string
  username: string
  role: string
  action: string
  target: string
  detail: string
}

export interface Position {
  lat: number
  lon: number
  label: string
  /** UTC time of the fix, or null when this is the vessel's base port. */
  at: string | null
  on_date: string | null
  source: 'REPORT' | 'VSAT' | 'AIS' | 'BASE'
  age_hours: number | null
  /** Not heard from for longer than the server's limit (36 h). */
  stale: boolean
}

/** "VSAT · 2 h ago", "Daily report · 1 d ago", "Base port". */
export function positionNote(p: Position) {
  if (p.source === 'BASE') return 'Base port, no reported position'
  const source = p.source === 'REPORT' ? 'Daily report (noon)' : p.source
  const age = p.age_hours === null ? '' : p.age_hours < 1 ? 'just now' : p.age_hours < 48 ? `${Math.round(p.age_hours)} h ago` : `${Math.round(p.age_hours / 24)} d ago`
  return `${source} · ${age}${p.stale ? ' · out of date' : ''}`
}

export interface Vessel {
  vessel_id: string
  name: string
  vessel_type: 'DSV' | 'OSV' | 'BARGE' | 'BULK'
  imo: string
  mmsi: string | null
  flag: string
  built_year: number | null
  entity: string
  daily_opex: number
  status: 'AVAILABLE' | 'ON_HIRE' | 'DRY_DOCK'
  contract_no: string | null
  client: string | null
  contract_end: string | null
  certs_expired: number
  certs_expiring: number
  position: Position | null
}

export interface Certificate {
  id: number
  vessel_id: string
  vessel_name?: string
  name: string
  authority: string
  issued_on: string
  expires_on: string
  critical: boolean
  annual_survey: boolean
  endorsed_on: string | null
  survey: 'UPCOMING' | 'DUE' | 'OVERDUE' | null
  survey_from: string | null
  survey_to: string | null
  days_left: number
  state: 'VALID' | 'SURVEY_DUE' | 'EXPIRING' | 'SURVEY_OVERDUE' | 'EXPIRED'
}

export interface Contract {
  contract_no: string
  client: string
  vessel_id: string
  vessel_name: string
  scope: string
  start_date: string
  end_date: string
  operating_rate: number
  standby_rate: number
  breakdown_allowance_hrs: number
  allowance_accrues: boolean
  weather_billing: 'OPERATING' | 'STANDBY'
  tax_label: string
  tax_rate: number
  client_signoff_required: boolean
  mob_fee: number
  demob_fee: number
  payment_terms_days: number
  bg_amount: number
  bg_expiry: string | null
  bg_days_left: number | null
  status: 'ACTIVE' | 'COMPLETED'
  days_left: number
  billed: number
}

export interface Report {
  id: number
  vessel_id: string
  vessel_name?: string
  contract_no: string | null
  on_date: string
  location: string
  lat: number | null
  lon: number | null
  operating_hrs: number
  standby_hrs: number
  weather_hrs: number
  breakdown_hrs: number
  transit_hrs: number
  work_done: string
  dive_hrs: number
  rov_hrs: number
  fuel_rob: number
  fuel_received: number
  fuel_used?: number | null
  fuel_alert?: boolean
  pob: number
  breakdown_equipment_id?: number | null
  incidents: string
  status: 'SUBMITTED' | 'APPROVED' | 'REJECTED'
  submitted_by: string
  approved_by: string | null
}

export interface VesselDetail extends Omit<Vessel, 'contract_no' | 'client' | 'contract_end' | 'certs_expired' | 'certs_expiring'> {
  certificates: Certificate[]
  contracts: Contract[]
  reports: Report[]
  position: Position | null
  track: { lat: number; lon: number; at: string }[]
}

export interface Calc {
  period: string
  contract_days: number
  reported_days: number
  pending_dates: string[]
  missing_dates: string[]
  hours: { operating: number; standby: number; breakdown_paid: number; off_hire: number }
  allowance_hrs: number
  allowance_left_hrs: number | null
  allowance_accrues: boolean
  weather_billing: 'OPERATING' | 'STANDBY'
  lines: { label: string; days: number | null; rate: number; amount: number }[]
  amount: number
}

export interface Invoice {
  inv_no: string
  contract_no: string
  client: string
  vessel_id: string
  vessel_name: string
  period: string
  invoice_date: string
  due_date: string
  calc: Calc
  amount: number
  tax_label: string
  tax_rate: number
  tax: number
  total: number
  status: 'DRAFT' | 'APPROVED' | 'PAID'
  overdue: boolean
  signoff_required: boolean
  signoff: Signoff | null
  created_by: string
  approved_by: string | null
  paid_on: string | null
}

export interface FleetRow {
  vessel_id: string
  name: string
  vessel_type: Vessel['vessel_type']
  status: Vessel['status']
  client: string | null
  contract_no: string | null
  revenue_mtd: number
  opex_mtd: number
  pnl_mtd: number
  utilisation: number
  last_report: string | null
  missing_reports_7d: number
}

export interface Dashboard {
  period: string
  days_elapsed: number
  kpis: {
    vessels: number
    on_hire: number
    dry_dock: number
    utilisation: number
    revenue_mtd: number
    pnl_mtd: number
    receivables: number
    overdue: number
    reports_pending: number
    certs_expired: number
    certs_expiring: number
  }
  fleet: FleetRow[]
  cert_alerts: Certificate[]
  pending_reports: { id: number; vessel_id: string; vessel_name: string; on_date: string }[]
  contracts_ending: { contract_no: string; vessel_name: string; client: string; end_date: string; days_left: number }[]
  bg_expiring: { contract_no: string; bg_amount: number; bg_expiry: string; days_left: number }[]
}

// ---- Calling the server ----

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, init)
  if (!res.ok) {
    const detail = (await res.json().catch(() => null))?.detail
    // A form the server could not read (422) names each field that was wrong.
    const listed = Array.isArray(detail) ? detail.map((d) => d?.msg?.replace(/^Value error, /, '')).filter(Boolean).join('; ') : ''
    throw new ApiError(res.status, typeof detail === 'string' ? detail : listed || `The request failed (${res.status}).`)
  }
  return res.status === 204 ? (undefined as T) : res.json()
}

export const postJson = <T>(path: string, body?: unknown) =>
  api<T>(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body ?? {}) })

/** The signed-in user, or null when nobody is signed in. With no connection, the last known user (offline use). */
export const useMe = () =>
  useQuery({
    queryKey: ['me'],
    queryFn: () =>
      remembered('me', () => api<User>('/auth/me')).catch((e) => {
        if (e instanceof ApiError && e.status === 401) {
          forget('me')
          return null
        }
        throw e
      }),
  })

export const useDashboard = () => useQuery({ queryKey: ['dashboard'], queryFn: () => api<Dashboard>('/dashboard') })
export const useVessels = () => useQuery({ queryKey: ['vessels'], queryFn: () => remembered('vessels', () => api<Vessel[]>('/vessels')) })
export const useVessel = (id: string) => useQuery({ queryKey: ['vessels', id], queryFn: () => api<VesselDetail>(`/vessels/${encodeURIComponent(id)}`) })
export const useCertificates = () => useQuery({ queryKey: ['certificates'], queryFn: () => api<Certificate[]>('/certificates') })
export const useContracts = () => useQuery({ queryKey: ['contracts'], queryFn: () => api<Contract[]>('/contracts') })
export const useReports = () => useQuery({ queryKey: ['reports'], queryFn: () => api<Report[]>('/reports') })
export const useInvoices = () => useQuery({ queryKey: ['invoices'], queryFn: () => api<Invoice[]>('/invoices') })
export const useUsers = () => useQuery({ queryKey: ['users'], queryFn: () => api<Account[]>('/users') })
export const useAudit = () => useQuery({ queryKey: ['audit'], queryFn: () => api<AuditEntry[]>('/audit') })

/**
 * An action that changes data. On success it shows `done` and refreshes every list, since one action touches several
 * pages (approving a report changes the dashboard, the vessel and billing).
 */
export function useAction<In, Out = unknown>(fn: (input: In) => Promise<Out>, done: string | ((out: Out) => string), after?: (out: Out) => void) {
  const queryClient = useQueryClient()
  const { message } = AntApp.useApp()
  return useMutation({
    mutationFn: fn,
    onSuccess: (out) => {
      queryClient.invalidateQueries({ predicate: (q) => q.queryKey[0] !== 'me' })
      message.success(typeof done === 'string' ? done : done(out))
      after?.(out)
    },
    onError: (error) => message.error(error.message),
  })
}

/** What each role may do. The server enforces the same rules; this only decides what to show. */
export const can = {
  approve: (user: User) => user.role === 'manager' || user.role === 'admin',
  readAudit: (user: User) => user.role === 'manager' || user.role === 'admin',
  assignCrew: (user: User) => user.role === 'manager' || user.role === 'admin',
  manageContracts: (user: User) => user.role === 'admin',
  manageUsers: (user: User) => user.role === 'admin',
}

// ---- Formatting ----

const INR = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 })
const NUM = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 })

/** Rupees with Indian grouping: ₹12,34,567. */
export const money = (value: number | null | undefined) =>
  value === null || value === undefined ? '—' : `${value < 0 ? '-' : ''}₹${INR.format(Math.abs(value))}`

/** The short form for number tiles: ₹1.24 Cr, ₹8.50 L. */
export function moneyShort(value: number | null | undefined) {
  if (value === null || value === undefined) return '—'
  const abs = Math.abs(value)
  const sign = value < 0 ? '-' : ''
  if (abs >= 1e7) return `${sign}₹${(abs / 1e7).toFixed(2)} Cr`
  if (abs >= 1e5) return `${sign}₹${(abs / 1e5).toFixed(2)} L`
  return money(value)
}

export const num = (value: number | null | undefined) => (value === null || value === undefined ? '—' : NUM.format(value))

/** "19 Oct 2026". */
export const fmtDate = (iso: string | null | undefined) => (iso ? dayjs(iso).format('D MMM YYYY') : '—')
export const formatTime = (iso: string) => new Date(iso).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' })

// ---- Fleet operations: maintenance, crew, readiness, planner ----

export interface Job {
  id: number
  kind: 'PLANNED' | 'DEFECT'
  title: string
  equipment_id: number
  equipment: string
  system: string
  critical: boolean
  vessel_id: string
  running_hours: number
  interval_days: number | null
  interval_hours: number | null
  last_done_on: string | null
  last_done_hours: number | null
  raised_on: string | null
  report_id: number | null
  downtime_hrs: number
  closed_on: string | null
  note: string
  repeat_failure: boolean
  state: 'OPEN' | 'OVERDUE' | 'DUE_SOON' | 'OK' | 'CLOSED'
  due_on: string | null
  days_left: number | null
  hours_left: number | null
}

export interface EquipmentItem {
  id: number
  vessel_id: string
  name: string
  system: string
  critical: boolean
  running_hours: number
  hours_updated_on: string | null
}

export interface CrewAlert {
  level: 'BLOCK' | 'WARN' | 'INFO'
  text: string
}

export interface CrewOnBoard {
  assignment_id: number
  crew_id: number
  name: string
  rank: string
  vessel_id: string
  sign_on: string
  relief_due: string
  days_on_board: number
  mlc_limit: string
  certificates: { name: string; expires_on: string }[]
  alerts: CrewAlert[]
}

export interface CrewPerson {
  id: number
  name: string
  rank: string
  on_board: string | null
  certificates: { name: string; expires_on: string }[]
}

export interface ReadinessCheck {
  check: string
  ok: boolean
  problems: string[]
  warnings: string[]
}

export interface Readiness {
  vessel_id: string
  name: string
  ready: boolean
  blocking: number
  warnings: number
  checks: ReadinessCheck[]
}

export interface PlanEvent {
  type: 'CONTRACT' | 'DRYDOCK_DUE' | 'CERT_EXPIRY'
  label: string
  from: string
  to: string
}

export interface PlanRow {
  vessel_id: string
  name: string
  vessel_type: Vessel['vessel_type']
  status: Vessel['status']
  contract_end: string | null
  idle_days_180: number
  idle_cost_180: number
  bottom_survey_due: string | null
  reliefs_30d: number
  events: PlanEvent[]
  suggestion: string | null
}

export const useMaintenance = (vessel?: string) =>
  useQuery({ queryKey: ['maintenance', vessel ?? 'all'], queryFn: () => api<Job[]>(`/maintenance${vessel ? `?vessel=${encodeURIComponent(vessel)}` : ''}`) })
export const useEquipment = (vessel?: string) =>
  useQuery({
    queryKey: ['equipment', vessel ?? 'all'],
    queryFn: () => remembered(`equipment:${vessel ?? 'all'}`, () => api<EquipmentItem[]>(`/equipment${vessel ? `?vessel=${encodeURIComponent(vessel)}` : ''}`)),
    enabled: vessel !== '',
  })
export const useCrewOnBoard = () => useQuery({ queryKey: ['crew-onboard'], queryFn: () => api<{ crew: CrewOnBoard[]; gaps: Record<string, { rank: string; required: number; on_board: number }[]> }>('/crew/onboard') })
export const useCrew = () => useQuery({ queryKey: ['crew'], queryFn: () => api<CrewPerson[]>('/crew') })
export const useReadiness = () => useQuery({ queryKey: ['readiness'], queryFn: () => api<Readiness[]>('/readiness') })
export const usePlanner = () => useQuery({ queryKey: ['planner'], queryFn: () => api<PlanRow[]>('/planner') })

// ---- Client portal ----

export interface Signoff {
  status: 'SIGNED' | 'DISPUTED'
  by: string
  at: string
  note: string
}

export interface ClientContract {
  contract_no: string
  vessel_name: string
  scope: string
  start_date: string
  end_date: string
  status: string
}

export interface TimesheetView {
  contract_no: string
  period: string
  rows: { on_date: string; location: string; operating_hrs: number; standby_hrs: number; weather_hrs: number; breakdown_hrs: number; transit_hrs: number; work_done: string; dive_hrs: number }[]
  hours: Calc['hours']
  missing_dates: string[]
  pending_dates: string[]
  lines: Calc['lines']
  amount: number
  signoff: Signoff | null
}

export const useClientContracts = () => useQuery({ queryKey: ['client-contracts'], queryFn: () => api<ClientContract[]>('/client/contracts') })
export const useTimesheet = (contractNo?: string, period?: string) =>
  useQuery({
    queryKey: ['timesheet', contractNo, period],
    queryFn: () => api<TimesheetView>(`/client/timesheet?contract_no=${encodeURIComponent(contractNo!)}&period=${period}`),
    enabled: !!contractNo && !!period,
  })
