import { BulbOutlined } from '@ant-design/icons'
import { Card, Skeleton, Tooltip, Typography } from 'antd'
import dayjs from 'dayjs'

import { fmtDate, moneyShort, usePlanner, type PlanEvent } from '../api'
import { STATUS } from '../brand'
import { ErrorAlert } from '../components/Tags'
import { PageHead, VesselLink } from '../components/ui'

const DAYS = 365
const COLOUR: Record<PlanEvent['type'], string> = { CONTRACT: STATUS.ok, DRYDOCK_DUE: STATUS.bad, CERT_EXPIRY: STATUS.warn }

/** Twelve months ahead for every vessel: contracts, the dry dock deadline, certificate expiries, and idle time. */
export default function Planner() {
  const plan = usePlanner()
  const start = dayjs().startOf('day')
  const pct = (iso: string) => Math.max(0, Math.min(100, (dayjs(iso).diff(start, 'day') / DAYS) * 100))
  const months = Array.from({ length: 12 }, (_, i) => start.add(i + 1, 'month').startOf('month')) // month boundaries ahead, so labels never overlap

  return (
    <>
      <PageHead
        title="Planner"
        sub="The next 12 months. Green: on contract. Red mark: bottom survey due (HSSC: at most 36 months between bottom inspections). Amber mark: a certificate expires. Gaps are idle time, costed at the vessel's running cost."
      />
      <ErrorAlert error={plan.error} />
      <Card>
        <Skeleton loading={plan.isPending} active>
          <div className="plan">
            <div className="plan-row plan-head">
              <div />
              <div className="plan-track">
                {months.map((m) => (
                  <span key={m.toString()} style={{ left: `${pct(m.format('YYYY-MM-DD'))}%` }}>
                    {m.format('MMM')}
                  </span>
                ))}
              </div>
            </div>
            {(plan.data ?? []).map((p) => (
              <div key={p.vessel_id} className="plan-row">
                <div>
                  <VesselLink id={p.vessel_id} name={p.name} />
                  <div className="muted">
                    {p.idle_days_180 ? `Idle ${p.idle_days_180} of next 180 days · ${moneyShort(p.idle_cost_180)}` : 'Booked for the next 180 days'}
                    {p.reliefs_30d ? ` · ${p.reliefs_30d} crew reliefs in 30 days` : ''}
                  </div>
                </div>
                <div className="plan-track">
                  {p.events.map((e, i) =>
                    e.type === 'CONTRACT' ? (
                      <Tooltip key={i} title={`${e.label}: ${fmtDate(e.from)} – ${fmtDate(e.to)}`}>
                        <span className="plan-bar" style={{ left: `${pct(e.from)}%`, width: `${Math.max(0.8, pct(e.to) - pct(e.from))}%`, background: COLOUR.CONTRACT }} />
                      </Tooltip>
                    ) : (
                      <Tooltip key={i} title={`${e.label}: ${fmtDate(e.from)}`}>
                        <span className="plan-mark" style={{ left: `${pct(e.from)}%`, background: COLOUR[e.type] }} />
                      </Tooltip>
                    ),
                  )}
                </div>
                {p.suggestion && (
                  <Typography.Text className="plan-note">
                    <BulbOutlined style={{ color: STATUS.warn }} /> {p.suggestion}
                  </Typography.Text>
                )}
              </div>
            ))}
          </div>
        </Skeleton>
      </Card>
    </>
  )
}
