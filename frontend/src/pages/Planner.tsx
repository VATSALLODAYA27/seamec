import {
  AlertOutlined,
  CalendarOutlined,
  ExclamationCircleOutlined,
  FileProtectOutlined,
  InfoCircleOutlined,
  SafetyOutlined,
  TeamOutlined,
  ToolOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import { Card, Empty, Skeleton, Tabs, Tooltip } from 'antd'
import dayjs, { type Dayjs } from 'dayjs'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

import { fmtDate, moneyShort, usePlanner, type PlanEvent, type PlanRow } from '../api'
import { STATUS } from '../brand'
import { ErrorAlert } from '../components/Tags'
import { PageHead, VesselLink } from '../components/ui'

const iso = (d: Dayjs) => d.format('YYYY-MM-DD')
const clientOf = (e: PlanEvent) => e.label.replace(/\s*\(.*$/, '')

// ---------------- "What's coming": one plain sentence per thing to act on ----------------

type Level = 'urgent' | 'warn' | 'info'
interface Item {
  vessel: PlanRow
  date: string
  level: Level
  icon: ReactNode
  text: ReactNode
  action?: { label: string; to: string }
}

const CERT_SOON_DAYS = 90 // later expiries are summed up in one line, so the list stays short

const LEVEL_COLOUR: Record<Level, string> = { urgent: STATUS.bad, warn: STATUS.warn, info: STATUS.info }

function itemsFor(p: PlanRow, today: Dayjs): Item[] {
  const contracts = p.events.filter((e) => e.type === 'CONTRACT')
  const onContract = (day: string) => contracts.find((c) => c.from <= day && day <= c.to)
  const items: Item[] = []
  const days = (d: string) => dayjs(d).diff(today, 'day')
  const dock = p.events.find((e) => e.type === 'DRYDOCK')

  // Dry dock (bottom survey) deadline
  if (p.bottom_survey_due) {
    const due = p.bottom_survey_due
    if (p.status === 'DRY_DOCK') {
      items.push({ vessel: p, date: iso(today), level: 'info', icon: <ToolOutlined />,
        text: <>is <b>in dry dock now</b>. Complete the docking when she is out (that records the bottom survey), then line up the next charter.</>,
        action: { label: 'Dry dock', to: '/drydock' } })
    } else if (dock && dock.from <= due) {
      items.push({ vessel: p, date: dock.from, level: 'info', icon: <ToolOutlined />,
        text: <>{dock.label.replace(/^Dry dock/, 'dry dock')} from <b>{fmtDate(dock.from)}</b> to {fmtDate(dock.to)}, before the bottom survey falls due ({fmtDate(due)}).</>,
        action: { label: 'Dry dock', to: '/drydock' } })
    } else if (days(due) < 0) {
      items.push({ vessel: p, date: due, level: 'urgent', icon: <ExclamationCircleOutlined />,
        text: <>dry dock deadline <b>passed on {fmtDate(due)}</b>. Dock now, or agree an in-water survey with class.</> })
    } else if (days(due) <= 365) {
      const clash = onContract(due)
      items.push({ vessel: p, date: due, level: clash ? 'warn' : days(due) <= 60 ? 'urgent' : 'info', icon: <ToolOutlined />,
        text: clash
          ? <>dry dock due <b>{fmtDate(due)}</b>, during its contract with {clientOf(clash)}. Agree a docking break, or an in-water survey if class accepts it.</>
          : <>dry dock due <b>{fmtDate(due)}</b> ({days(due)} days). It has no work then: a good time to dock.</> })
    }
  }

  // Contract ending with nothing booked after it
  for (const c of contracts) {
    const next = contracts.find((o) => o.from > c.to)
    if (!next && days(c.to) <= 365) {
      items.push({ vessel: p, date: c.to, level: days(c.to) <= 30 ? 'warn' : 'info', icon: <CalendarOutlined />,
        text: <>contract with {clientOf(c)} ends <b>{fmtDate(c.to)}</b>. Line up the next charter.</>,
        action: { label: 'Contracts', to: '/contracts' } })
    }
  }

  // Certificates expiring (one line per vessel, so the list stays short)
  const certs = p.events.filter((e) => e.type === 'CERT_EXPIRY')
  if (certs.length && days(certs[0].from) <= CERT_SOON_DAYS) {
    const first = certs[0]
    const expired = days(first.from) < 0
    items.push({ vessel: p, date: first.from, level: expired ? 'urgent' : days(first.from) <= 60 ? 'warn' : 'info', icon: <FileProtectOutlined />,
      text: <>{first.label.replace(/ expires$/, '')} {expired ? 'expired' : 'expires'} <b>{fmtDate(first.from)}</b>
        {certs.length > 1 ? `, and ${certs.length - 1} more certificate${certs.length > 2 ? 's' : ''} within a year` : ''}. Renew in time.</>,
      action: { label: 'Certificates', to: '/certificates' } })
  }

  // Insurance lapsing (charters need hull and machinery and P&I cover throughout)
  for (const e of p.events.filter((e) => e.type === 'INSURANCE_EXPIRY' && days(e.from) <= 60)) {
    items.push({ vessel: p, date: e.from, level: days(e.from) <= 30 ? 'warn' : 'info', icon: <SafetyOutlined />,
      text: <>{e.label.replace(/ expires$/, '')} expires <b>{fmtDate(e.from)}</b>. Renew before it lapses.</>,
      action: { label: 'Insurance', to: '/insurance' } })
  }

  return items
}

// Each item goes in the first group whose end date it falls on or before (overdue items land in the first).
const GROUPS: { label: string; until: (today: Dayjs) => string }[] = [
  { label: 'Now and next 30 days', until: (t) => iso(t.add(30, 'day')) },
  { label: 'Next 3 months', until: (t) => iso(t.add(3, 'month')) },
  { label: 'Later this year', until: () => '9999-12-31' },
]

function WhatsComing({ rows, today }: { rows: PlanRow[]; today: Dayjs }) {
  const order: Record<Level, number> = { urgent: 0, warn: 1, info: 2 }
  const all = rows.flatMap((p) => itemsFor(p, today)).sort((a, b) => a.date.localeCompare(b.date) || order[a.level] - order[b.level])
  const idle = rows.filter((p) => p.status !== 'DRY_DOCK' && !p.events.some((e) => e.type === 'CONTRACT' && e.from <= iso(today)))
  const groupOf = (date: string) => GROUPS.findIndex((g) => date <= g.until(today))
  const reliefs = rows.filter((p) => p.reliefs_30d).sort((a, b) => b.reliefs_30d - a.reliefs_30d)
  const totalReliefs = reliefs.reduce((n, p) => n + p.reliefs_30d, 0)
  const laterCerts = rows.flatMap((p) => p.events.filter((e) => e.type === 'CERT_EXPIRY' && dayjs(e.from).diff(today, 'day') > CERT_SOON_DAYS))
  const summary: Record<number, ReactNode> = {
    0: totalReliefs > 0 && (
      <div className="coming-row" style={{ borderLeftColor: STATUS.info }}>
        <span className="coming-icon" style={{ color: STATUS.info, background: `${STATUS.info}1f` }}>
          <TeamOutlined />
        </span>
        <div className="coming-text">
          <b>{totalReliefs} crew reliefs</b> due in the next 30 days:{' '}
          {reliefs.map((p) => `${p.name.replace('SEAMEC ', '')} ${p.reliefs_30d}`).join(', ')}.
        </div>
        <Link to="/crew" className="coming-action">
          Crew →
        </Link>
      </div>
    ),
    2: laterCerts.length > 0 && (
      <div className="coming-row" style={{ borderLeftColor: STATUS.info }}>
        <span className="coming-icon" style={{ color: STATUS.info, background: `${STATUS.info}1f` }}>
          <FileProtectOutlined />
        </span>
        <div className="coming-text">
          <b>{laterCerts.length} certificates</b> expire later in the year, across the fleet. Each shows on the Certificates page with its renewal date.
        </div>
        <Link to="/certificates" className="coming-action">
          Certificates →
        </Link>
      </div>
    ),
  }
  return (
    <>
      {idle.length > 0 && (
        <div className="coming-idle">
          <AlertOutlined style={{ color: STATUS.warn }} /> <b>No work today:</b>{' '}
          {idle.map((p, i) => (
            <span key={p.vessel_id}>
              {i > 0 && ', '}
              <VesselLink id={p.vessel_id} name={p.name} />
            </span>
          ))}
          <span className="muted"> · running cost {moneyShort(idle.reduce((s, p) => s + p.idle_cost_180, 0))} over the next 6 months if nothing changes</span>
        </div>
      )}
      {GROUPS.map((g, index) => {
        const mine = all.filter((i) => groupOf(i.date) === index)
        return (
          <section key={g.label} className="coming-group">
            <h3>{g.label}</h3>
            {mine.length === 0 && !summary[index] ? (
              <p className="muted">Nothing to do.</p>
            ) : (
              mine.map((i, k) => (
                <div key={k} className="coming-row" style={{ borderLeftColor: LEVEL_COLOUR[i.level] }}>
                  <span className="coming-icon" style={{ color: LEVEL_COLOUR[i.level], background: `${LEVEL_COLOUR[i.level]}1f` }}>
                    {i.icon}
                  </span>
                  <div className="coming-text">
                    <VesselLink id={i.vessel.vessel_id} name={i.vessel.name} /> {i.text}
                  </div>
                  {i.action && (
                    <Link to={i.action.to} className="coming-action">
                      {i.action.label} →
                    </Link>
                  )}
                </div>
              ))
            )}
            {summary[index]}
          </section>
        )
      })}
    </>
  )
}

// ---------------- "Month by month": one word per vessel per month ----------------

type Cell = { word: string; kind: 'work' | 'idle' | 'dock' | 'end' | 'start'; note?: string }

function cellFor(p: PlanRow, month: Dayjs, today: Dayjs): Cell {
  const first = iso(month.isBefore(today) ? today : month.startOf('month'))
  const last = iso(month.endOf('month'))
  const contracts = p.events.filter((e) => e.type === 'CONTRACT')
  const certs = p.events.filter((e) => e.type === 'CERT_EXPIRY' && e.from >= first && e.from <= last)
  const note = certs.length ? `${certs.length} certificate${certs.length > 1 ? 's' : ''} expire${certs.length > 1 ? '' : 's'}` : undefined
  if (p.status === 'DRY_DOCK' && month.isSame(today, 'month')) return { word: 'In dock', kind: 'dock', note }
  if (p.events.some((e) => e.type === 'DRYDOCK' && e.from <= last && e.to >= first)) return { word: 'Dry dock', kind: 'dock', note }
  if (p.bottom_survey_due && p.bottom_survey_due >= first && p.bottom_survey_due <= last) return { word: 'Dry dock due', kind: 'dock', note }
  const ending = contracts.find((c) => c.to >= first && c.to < last && !contracts.some((o) => o.from > c.to && o.from <= last))
  if (ending) return { word: `Ends ${dayjs(ending.to).format('D MMM')}`, kind: 'end', note }
  const starting = contracts.find((c) => c.from > first && c.from <= last)
  if (starting) return { word: `Starts ${dayjs(starting.from).format('D MMM')}`, kind: 'start', note }
  if (contracts.some((c) => c.from <= first && c.to >= last)) return { word: 'Working', kind: 'work', note }
  return { word: 'Idle', kind: 'idle', note }
}

function MonthGrid({ rows, today }: { rows: PlanRow[]; today: Dayjs }) {
  const months = Array.from({ length: 12 }, (_, i) => today.startOf('month').add(i, 'month'))
  return (
    <>
      <div className="grid-legend">
        <span className="cell work">Working</span>
        <span className="cell idle">Idle</span>
        <span className="cell end">Contract ends</span>
        <span className="cell dock">Dry dock due</span>
        <span className="muted">
          <FileProtectOutlined /> = a certificate expires that month
        </span>
      </div>
      <div className="grid-wrap">
        <table className="month-grid">
          <thead>
            <tr>
              <th className="vessel-col">Vessel</th>
              {months.map((m) => (
                <th key={m.toString()}>{m.format(m.month() === 0 || m.isSame(today, 'month') ? "MMM 'YY" : 'MMM')}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => (
              <tr key={p.vessel_id}>
                <td className="vessel-col">
                  <VesselLink id={p.vessel_id} name={p.name} />
                </td>
                {months.map((m) => {
                  const c = cellFor(p, m, today)
                  return (
                    <td key={m.toString()}>
                      <Tooltip title={c.note}>
                        <span className={`cell ${c.kind}`}>
                          {c.word}
                          {c.note && <FileProtectOutlined className="cell-cert" aria-label={c.note} />}
                        </span>
                      </Tooltip>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}

// ---------------- Page ----------------

function Summary({ rows, today }: { rows: PlanRow[]; today: Dayjs }) {
  const idleNow = rows.filter((r) => r.status !== 'DRY_DOCK' && !r.events.some((e) => e.type === 'CONTRACT' && e.from <= iso(today)))
  const docks = rows.filter((r) => r.bottom_survey_due && dayjs(r.bottom_survey_due).diff(today, 'day') <= 365)
  const ending = rows.filter((r) => r.contract_end && dayjs(r.contract_end).diff(today, 'day') <= 90)
  const tiles = [
    { icon: <CalendarOutlined />, colour: STATUS.warn, value: `${idleNow.length} of ${rows.length}`, label: 'Vessels with no work today' },
    { icon: <WarningOutlined />, colour: STATUS.bad, value: moneyShort(rows.reduce((s, r) => s + r.idle_cost_180, 0)), label: 'Idle cost, next 6 months' },
    { icon: <ToolOutlined />, colour: STATUS.bad, value: String(docks.length), label: 'Dry docks due in 12 months' },
    { icon: <InfoCircleOutlined />, colour: STATUS.info, value: String(ending.length), label: 'Contracts ending in 90 days' },
  ]
  return (
    <div className="plan-summary">
      {tiles.map((t) => (
        <div key={t.label} className="plan-tile">
          <span className="plan-tile-icon" style={{ color: t.colour, background: `${t.colour}1f` }}>
            {t.icon}
          </span>
          <div>
            <b>{t.value}</b>
            <span className="muted">{t.label}</span>
          </div>
        </div>
      ))}
    </div>
  )
}

/** The year ahead: what to act on, soonest first, and a month-by-month view of every vessel. */
export default function Planner() {
  const plan = usePlanner()
  const today = dayjs().startOf('day')
  const rows = plan.data ?? []
  return (
    <>
      <PageHead
        title="Planner"
        sub="The year ahead for every vessel. Dry dock dates follow the rule that the hull's bottom must be inspected at least every 36 months."
      />
      <ErrorAlert error={plan.error} />
      <Skeleton loading={plan.isPending} active>
        {rows.length ? (
          <>
            <Summary rows={rows} today={today} />
            <Card>
              <Tabs
                items={[
                  { key: 'coming', label: "What's coming", children: <WhatsComing rows={rows} today={today} /> },
                  { key: 'grid', label: 'Month by month', children: <MonthGrid rows={rows} today={today} /> },
                ]}
              />
            </Card>
          </>
        ) : (
          <Empty />
        )}
      </Skeleton>
    </>
  )
}
