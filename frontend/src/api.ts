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
  if (p.source === 'BASE') return 'Approximate: port area, no exact position fix'
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
  /** 0 when not on file */
  daily_opex: number
  /** Home port, or the last area seen on AIS when no coordinates are known */
  base_port: string
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
  documents: number
  cp_on_file: boolean
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
  cost_mtd: number
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
  attention: { level: 'error' | 'warning' | 'info'; label: string; count: number; to: string }[]
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
  /** Tenders, finance, purchase approvals, dry docks, insurance, vendors: the office's commercial decisions. */
  manage: (user: User) => user.role === 'manager' || user.role === 'admin',
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
  awaiting_spares: { request_id: number; part_id: number; part: string; qty: number; unit: string; po_no: string | null }[]
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
  type: 'CONTRACT' | 'DRYDOCK_DUE' | 'CERT_EXPIRY' | 'DRYDOCK' | 'INSURANCE_EXPIRY'
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
  suggestion_level: 'urgent' | 'clash' | 'tip' | 'idle' | 'info' | null
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

// ---- Commercial: tenders, off hire, performance claims ----

export interface TenderModel {
  days: number
  day_rate: number
  revenue: number
  /** null when the vessel's running cost is not on file */
  cost: number | null
  margin: number | null
  margin_pct: number | null
  breakeven_rate: number | null
  expected_margin: number | null
}

export interface Tender {
  id: number
  ref: string
  client: string
  vessel_type: Vessel['vessel_type']
  vessel_id: string | null
  vessel_name: string | null
  scope: string
  start_date: string
  end_date: string
  due_on: string
  operating_rate: number
  standby_rate: number
  operating_share: number
  mob_fee: number
  demob_fee: number
  mob_cost: number
  extra_daily_cost: number
  probability: number
  status: 'DRAFT' | 'SUBMITTED' | 'WON' | 'LOST' | 'WITHDRAWN'
  winning_rate: number | null
  outcome_note: string
  contract_no: string | null
  model: TenderModel
  vessel_clash: string | null
}

export interface TenderStats {
  decided: number
  won: number
  win_rate: number | null
  won_value: number
  lost_value: number
  value_win_rate: number | null
  pipeline_value: number
  weighted_pipeline: number
  price_gap_pct: number | null
  by_client: { client: string; bids: number; won: number; win_rate: number | null }[]
}

export interface OffHire {
  id: number
  vessel_id: string
  vessel_name: string
  contract_no: string | null
  client: string | null
  start_at: string
  end_at: string | null
  reason: 'BREAKDOWN' | 'MAINTENANCE' | 'CREW' | 'DOCUMENTS' | 'OTHER'
  description: string
  status: 'OPEN' | 'ENDED' | 'AGREED'
  hours: number
  uses_allowance: boolean
  reported_breakdown_hrs: number
  mismatch: boolean
}

export interface Claim {
  id: number
  contract_no: string
  client: string
  vessel_id: string
  vessel_name: string
  kind: 'SPEED' | 'FUEL' | 'DP' | 'EQUIPMENT' | 'DIVING' | 'OFF_HIRE' | 'OTHER'
  period: string
  description: string
  amount_claimed: number
  amount_agreed: number | null
  status: 'OPEN' | 'ACCEPTED' | 'REJECTED'
  raised_by: string
  raised_on: string
  response_due: string
  decision_note: string
  overdue: boolean
}

export const CLAIM_KINDS: Record<Claim['kind'], string> = {
  SPEED: 'Speed',
  FUEL: 'Fuel consumption',
  DP: 'DP capability',
  EQUIPMENT: 'Equipment',
  DIVING: 'Diving operations',
  OFF_HIRE: 'Off hire',
  OTHER: 'Other',
}
export const useTenders = () => useQuery({ queryKey: ['tenders'], queryFn: () => api<{ tenders: Tender[]; stats: TenderStats }>('/tenders') })
export const useOffHire = () => useQuery({ queryKey: ['off-hire'], queryFn: () => api<OffHire[]>('/off-hire') })
export const useClaims = () => useQuery({ queryKey: ['claims'], queryFn: () => api<Claim[]>('/claims') })
export const useClientClaims = () => useQuery({ queryKey: ['client-claims'], queryFn: () => api<Claim[]>('/client/claims') })

// ---- Documents ----

export interface DocumentRow {
  id: number
  entity: string
  entity_key: string
  kind: string
  title: string
  version: number
  filename: string
  size: number
  note: string
  uploaded_by: string
  at: string
  latest: boolean
}

export type DocEntity = 'contract' | 'tender' | 'drydock' | 'policy' | 'port_call' | 'po'

export const useDocuments = (entity: DocEntity, key: string, enabled = true) =>
  useQuery({ queryKey: ['documents', entity, key], queryFn: () => api<DocumentRow[]>(`/documents?entity=${entity}&key=${encodeURIComponent(key)}`), enabled })

// ---- Supply ----

export const SHORE = 'SHORE'

export interface VendorRow {
  id: number
  name: string
  category: 'SPARES' | 'STORES' | 'SERVICE' | 'AGENT' | 'YARD'
  country: string
  contact: string
  email: string
  phone: string
  tax_id: string
  payment_terms_days: number
  approved: boolean
  rating: number | null
  spend: number
}

export interface PartRow {
  id: number
  part_no: string
  name: string
  maker: string
  unit: string
  unit_cost: number
  vendor_id: number | null
  vendor_name: string | null
  lead_days: number
  total_qty: number
}

export interface StockRow {
  id: number
  part_id: number
  part_no: string
  part: string
  unit: string
  unit_cost: number
  location: string
  location_name: string
  qty: number
  min_qty: number
  value: number
  equipment_id: number | null
  equipment: string | null
  critical: boolean
  short: boolean
  waiting_qty: number
  bin: string
  on_order?: number
  to_order?: number
}

export interface POLineRow {
  id: number
  part_id: number | null
  part_no: string | null
  description: string
  qty: number
  unit: string
  unit_price: number
  received_qty: number
}

export interface PurchaseOrderRow {
  po_no: string
  vendor_id: number
  vendor_name: string
  deliver_to: string
  deliver_to_name: string
  status: 'DRAFT' | 'APPROVED' | 'ORDERED' | 'PART_RECEIVED' | 'RECEIVED' | 'CANCELLED'
  total: number
  needed_by: string | null
  note: string
  raised_by: string
  raised_on: string
  approved_by: string | null
  ordered_on: string | null
  needs_admin: boolean
  lines: POLineRow[]
}

export const useVendors = () => useQuery({ queryKey: ['vendors'], queryFn: () => api<VendorRow[]>('/vendors') })
export const useParts = () => useQuery({ queryKey: ['parts'], queryFn: () => api<PartRow[]>('/parts') })
export const useStock = () => useQuery({ queryKey: ['stock'], queryFn: () => api<StockRow[]>('/stock') })
export const useReorder = () => useQuery({ queryKey: ['reorder'], queryFn: () => api<StockRow[]>('/stock/reorder') })
export const usePurchaseOrders = () => useQuery({ queryKey: ['purchase-orders'], queryFn: () => api<PurchaseOrderRow[]>('/purchase-orders') })

/** Every vessel, then the shore warehouse: where stock can be and where orders can go. */
export const locationOptions = (vessels: Vessel[] | undefined) => [
  { value: SHORE, label: 'Shore warehouse' },
  ...(vessels ?? []).map((v) => ({ value: v.vessel_id, label: v.name })),
]

// ---- Port calls ----

export interface DaLine {
  id: number | null
  item: string
  pda: number
  fda: number | null
  over?: boolean
}

export interface PortCallRow {
  id: number
  vessel_id: string
  vessel_name: string
  port: string
  purpose: string
  eta: string
  etd: string
  ata: string | null
  atd: string | null
  agent_id: number | null
  agent_name: string | null
  appointed_on: string | null
  status: 'PLANNED' | 'ARRIVED' | 'SAILED' | 'CLOSED'
  advance_paid: number
  pda_total: number
  fda_total: number | null
  balance: number | null
  variance_pct: number | null
  lines: DaLine[]
}

export const usePortCalls = () => useQuery({ queryKey: ['port-calls'], queryFn: () => api<PortCallRow[]>('/port-calls') })

// ---- Dry dock ----

export interface DockItem {
  id: number
  category: 'HULL' | 'MACHINERY' | 'CLASS' | 'ELECTRICAL' | 'SAFETY' | 'DIVING' | 'OTHER'
  description: string
  budget: number
  actual: number
  status: 'OPEN' | 'DONE' | 'DEFERRED'
}

export interface YardQuoteRow {
  id: number
  vendor_id: number
  yard: string
  price: number
  days: number
  deviation_cost: number
  time_cost: number
  evaluated: number
  rank: number
  chosen: boolean
  note: string
}

export interface DryDockRow {
  id: number
  vessel_id: string
  vessel_name: string
  title: string
  status: 'PLANNING' | 'CONTRACTED' | 'IN_DOCK' | 'COMPLETED'
  planned_start: string
  planned_end: string
  actual_start: string | null
  actual_end: string | null
  bottom_survey: boolean
  budget: number
  actual: number
  items_open: number
  items_done: number
  yard: string | null
  items: DockItem[]
  quotes: YardQuoteRow[]
}

export const useDryDocks = () => useQuery({ queryKey: ['drydock'], queryFn: () => api<DryDockRow[]>('/drydock') })

// ---- Insurance ----

export interface PolicyRow {
  id: number
  kind: 'HM' | 'PI' | 'CREW' | 'LOH' | 'OTHER'
  insurer: string
  policy_no: string
  vessel_id: string | null
  vessel_name: string
  sum_insured: number
  deductible: number
  premium: number
  start_date: string
  end_date: string
  state: 'FUTURE' | 'IN_FORCE' | 'EXPIRING' | 'EXPIRED'
  days_left: number
  open_claims: number
}

export interface InsuranceClaimRow {
  id: number
  policy_id: number
  policy_no: string
  kind: PolicyRow['kind']
  insurer: string
  vessel_id: string
  vessel_name: string
  incident_on: string
  description: string
  amount: number
  deductible: number
  expected_recovery: number
  recovered: number | null
  status: 'NOTIFIED' | 'SUBMITTED' | 'SETTLED' | 'REJECTED'
  settled_on: string | null
}

export const COVER_LABEL: Record<PolicyRow['kind'], string> = { HM: 'Hull and machinery', PI: 'P&I', CREW: 'Crew cover', LOH: 'Loss of hire', OTHER: 'Other' }

export const usePolicies = () => useQuery({ queryKey: ['policies'], queryFn: () => api<PolicyRow[]>('/insurance/policies') })
export const useInsuranceClaims = () => useQuery({ queryKey: ['insurance-claims'], queryFn: () => api<InsuranceClaimRow[]>('/insurance/claims') })

// ---- Finance ----

export const COST_LINES = ['running', 'insurance', 'spares', 'port', 'drydock', 'other'] as const

export interface PnlFigures {
  hire: number
  claims: number
  revenue: number
  running: number
  insurance: number
  spares: number
  port: number
  drydock: number
  other: number
  cost: number
  profit: number
  margin_pct: number | null
}

export interface Pnl {
  first: string
  last: string
  vessels: (PnlFigures & { vessel_id: string; name: string; vessel_type: string; status: string; idle_cost: number; paid_hours: number })[]
  contracts: (PnlFigures & { contract_no: string; client: string; vessel_id: string; vessel_name: string; status: string })[]
  totals: PnlFigures
}

export interface BudgetLine {
  category: 'REVENUE' | 'RUNNING' | 'INSURANCE' | 'SPARES' | 'PORT' | 'DRYDOCK' | 'OTHER'
  budget_year: number
  budget_to_date: number
  actual_to_date: number
  variance: number
  months: { period: string; budget: number; actual: number | null }[]
}

export interface ForecastMonth {
  period: string
  days: number
  contracted: number
  pipeline: number
  running: number
  insurance: number
  drydock: number
  other: number
  revenue: number
  cost: number
  profit: number
  budget_revenue: number
  budget_cost: number
}

export interface CostRow {
  id: number
  vessel_id: string
  vessel_name: string
  contract_no: string | null
  on_date: string
  category: string
  amount: number
  description: string
  source: string
  ref: string
  created_by: string
}

export const usePnl = (first: string, last: string) => useQuery({ queryKey: ['pnl', first, last], queryFn: () => api<Pnl>(`/finance/pnl?first=${first}&last=${last}`) })
export const useBudget = (year: number, vessel?: string) =>
  useQuery({ queryKey: ['budget', year, vessel ?? 'all'], queryFn: () => api<{ year: number; through: string; lines: BudgetLine[] }>(`/finance/budget?year=${year}${vessel ? `&vessel=${vessel}` : ''}`) })
export const useForecast = () => useQuery({ queryKey: ['forecast'], queryFn: () => api<{ months: ForecastMonth[]; totals: Record<string, number> }>('/finance/forecast') })
export const useCosts = (first: string, last: string, vessel?: string) =>
  useQuery({ queryKey: ['costs', first, last, vessel ?? 'all'], queryFn: () => api<CostRow[]>(`/finance/costs?first=${first}&last=${last}${vessel ? `&vessel=${vessel}` : ''}`) })

export const putJson = <T>(path: string, body: unknown) => api<T>(path, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

/** "YYYY-MM-DD" from a date picker value. */
export const ymd = (d: { format: (f: string) => string } | null | undefined) => (d ? d.format('YYYY-MM-DD') : null)
