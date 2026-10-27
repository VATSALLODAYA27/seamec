import { Alert, Button, Card, Col, Empty, Flex, List, Progress, Row, Skeleton, Tag, Typography } from 'antd'
import dayjs from 'dayjs'
import { Link } from 'react-router-dom'

import { can, fmtDate, moneyShort, useDashboard, type FleetRow, type User } from '../api'
import { STATUS } from '../brand'
import { ErrorAlert, StateTag } from '../components/Tags'
import { Metric, PageHead, VesselLink } from '../components/ui'

const STATUS_COLOUR: Record<FleetRow['status'], string> = { ON_HIRE: STATUS.ok, AVAILABLE: STATUS.info, DRY_DOCK: STATUS.warn }

/** One vessel on the fleet board: what it is doing, and what it has earned and cost this month. */
function VesselCard({ v }: { v: FleetRow }) {
  const tone = v.utilisation >= 85 ? STATUS.ok : v.utilisation >= 60 ? STATUS.warn : STATUS.bad
  return (
    <Card size="small" className="vessel-card" style={{ ['--status' as string]: STATUS_COLOUR[v.status] }}>
      <Flex justify="space-between" align="start" gap={8}>
        <div>
          <Typography.Text strong style={{ fontSize: 15 }}>
            <VesselLink id={v.vessel_id} name={v.name} />
          </Typography.Text>
          <div className="muted">{v.vessel_type}</div>
        </div>
        <StateTag kind="vessel" value={v.status} />
      </Flex>
      <Typography.Text type={v.client ? undefined : 'secondary'} ellipsis>
        {v.client ?? 'No contract'}
      </Typography.Text>
      {v.contract_no ? (
        <>
          <Flex align="center" gap={12}>
            <Progress type="circle" size={52} percent={v.utilisation} strokeColor={tone} format={(p) => `${Math.round(p ?? 0)}%`} />
            <div className="figures" style={{ flex: 1 }}>
              <span className="muted">Revenue</span>
              <span>{moneyShort(v.revenue_mtd)}</span>
              <span className="muted">Cost</span>
              <span>{moneyShort(v.cost_mtd)}</span>
              <span className="muted">Profit</span>
              <Typography.Text strong type={v.pnl_mtd < 0 ? 'danger' : 'success'}>
                {moneyShort(v.pnl_mtd)}
              </Typography.Text>
            </div>
          </Flex>
          {v.missing_reports_7d ? (
            <Tag color="error">{v.missing_reports_7d} daily report missing this week</Tag>
          ) : (
            <span className="muted">Last report {fmtDate(v.last_report)}</span>
          )}
        </>
      ) : (
        <span className="muted">Idle cost this month {moneyShort(v.cost_mtd)}</span>
      )}
    </Card>
  )
}

export default function Dashboard({ me }: { me: User }) {
  const dash = useDashboard()
  const d = dash.data
  const k = d?.kpis

  return (
    <>
      <PageHead
        title="Fleet control tower"
        sub={d ? `${dayjs(`${d.period}-01`).format('MMMM YYYY')} · ${d.days_elapsed} days so far` : 'Loading…'}
        actions={
          <Flex gap={8}>
            {can.approve(me) && !!k?.reports_pending && (
              <Link to="/reports?status=SUBMITTED">
                <Button>Approve {k.reports_pending} reports</Button>
              </Link>
            )}
            <Link to="/reports?new=1">
              <Button type="primary">File daily report</Button>
            </Link>
          </Flex>
        }
      />
      <ErrorAlert error={dash.error} />
      <Skeleton loading={dash.isPending} active>
        {k && d && (
          <Flex vertical gap={20}>
            <div className="metrics">
              <Metric label="Vessels on hire" value={`${k.on_hire} of ${k.vessels}`} note={`${k.dry_dock} in dry dock`} to="/vessels" />
              <Metric label="Fleet utilisation" value={`${k.utilisation}%`} note="paid hours / all hours" to="/reports" />
              <Metric label="Hire revenue this month" value={moneyShort(k.revenue_mtd)} note={`profit ${moneyShort(k.pnl_mtd)}`} to="/invoices" />
              <Metric label="Receivables" value={moneyShort(k.receivables)} note={`${moneyShort(k.overdue)} overdue`} to="/invoices" alert={k.overdue > 0} />
              <Metric label="Reports to approve" value={k.reports_pending} to="/reports?status=SUBMITTED" />
              <Metric label="Certificates" value={`${k.certs_expired} expired`} note={`${k.certs_expiring} due in 60 days`} to="/certificates" alert={k.certs_expired > 0} />
            </div>

            <Row gutter={[16, 16]}>
              {d.fleet.map((v) => (
                <Col key={v.vessel_id} xs={24} sm={12} lg={8} xxl={6}>
                  <VesselCard v={v} />
                </Col>
              ))}
            </Row>

            <Row gutter={[16, 16]}>
              <Col xs={24} lg={8}>
                <Card title="Needs attention" style={{ height: '100%' }}>
                  {d.attention.length ? (
                    d.attention.map((a) => (
                      <Link key={a.label} to={a.to} className="attention-row">
                        <span className="attention-dot" style={{ background: a.level === 'error' ? STATUS.bad : a.level === 'warning' ? STATUS.warn : STATUS.info }} />
                        <span style={{ flex: 1 }}>{a.label}</span>
                        <b>{a.count}</b>
                      </Link>
                    ))
                  ) : (
                    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Nothing waiting" />
                  )}
                </Card>
              </Col>
              <Col xs={24} lg={8}>
                <Card title="Certificates needing action" extra={<Link to="/certificates">All</Link>} style={{ height: '100%' }}>
                  <List
                    size="small"
                    dataSource={d.cert_alerts}
                    locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="All certificates are valid" /> }}
                    renderItem={(c) => (
                      <List.Item extra={<StateTag kind="cert" value={c.state} />}>
                        <List.Item.Meta
                          title={<>{c.vessel_name} · {c.name}</>}
                          description={c.state === 'EXPIRED' ? `Expired ${-c.days_left} days ago, on ${fmtDate(c.expires_on)}` : `Expires ${fmtDate(c.expires_on)} (${c.days_left} days)`}
                        />
                      </List.Item>
                    )}
                  />
                </Card>
              </Col>
              <Col xs={24} lg={8}>
                <Card title="Contracts ending in 90 days" extra={<Link to="/contracts">All</Link>} style={{ height: '100%' }}>
                  <List
                    size="small"
                    dataSource={d.contracts_ending}
                    locale={{ emptyText: 'None' }}
                    renderItem={(c) => (
                      <List.Item extra={<Tag color={c.days_left <= 30 ? 'error' : 'warning'}>{c.days_left} days</Tag>}>
                        <List.Item.Meta title={c.vessel_name} description={`${c.client} · ends ${fmtDate(c.end_date)}. Line up the next charter.`} />
                      </List.Item>
                    )}
                  />
                  {d.bg_expiring.map((b) => (
                    <Alert key={b.contract_no} type="warning" showIcon style={{ marginTop: 8 }} message={`Bank guarantee for ${b.contract_no} (${moneyShort(b.bg_amount)}) expires ${fmtDate(b.bg_expiry)}`} />
                  ))}
                </Card>
              </Col>
            </Row>
          </Flex>
        )}
      </Skeleton>
    </>
  )
}
