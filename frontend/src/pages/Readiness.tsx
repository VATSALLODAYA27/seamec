import { CheckCircleFilled, CloseCircleFilled, ExclamationCircleOutlined } from '@ant-design/icons'
import { Card, Col, Empty, Row, Skeleton, Tag, Typography } from 'antd'

import { useReadiness, type Readiness as R } from '../api'
import { STATUS } from '../brand'
import { ErrorAlert } from '../components/Tags'
import { PageHead, VesselLink } from '../components/ui'

function VesselReadiness({ r }: { r: R }) {
  return (
    <Card
      size="small"
      style={{ height: '100%', borderTop: `4px solid ${r.ready ? STATUS.ok : STATUS.bad}`, borderRadius: 0 }}
      title={<VesselLink id={r.vessel_id} name={r.name} />}
      extra={r.ready ? <Tag color="success">Hire-ready</Tag> : <Tag color="error">Not ready: {r.blocking}</Tag>}
    >
      {r.checks.map((c) => (
        <div key={c.check} style={{ marginBottom: 8 }}>
          <Typography.Text strong style={{ fontSize: 13 }}>
            {c.ok ? <CheckCircleFilled style={{ color: STATUS.ok }} /> : <CloseCircleFilled style={{ color: STATUS.bad }} />} {c.check}
          </Typography.Text>
          {c.problems.map((p) => (
            <div key={p} style={{ fontSize: 12, color: STATUS.bad, paddingLeft: 20 }}>
              {p}
            </div>
          ))}
          {c.warnings.map((w) => (
            <div key={w} className="muted" style={{ paddingLeft: 20 }}>
              <ExclamationCircleOutlined style={{ color: STATUS.warn }} /> {w}
            </div>
          ))}
        </div>
      ))}
    </Card>
  )
}

/** One verdict per vessel: can it go on hire now, and if not, exactly what stops it. */
export default function Readiness() {
  const ready = useReadiness()
  const rows = [...(ready.data ?? [])].sort((a, b) => Number(b.ready) - Number(a.ready) || a.blocking - b.blocking)
  return (
    <>
      <PageHead
        title="Hire readiness"
        sub="A vessel is hire-ready when: not in dry dock; certificates valid and annual surveys done; bottom survey within 36 months; minimum crew on board with valid certificates and within the 11-month MLC limit; and no open defect or overdue job on critical equipment (ISM Code 10.3)."
      />
      <ErrorAlert error={ready.error} />
      <Skeleton loading={ready.isPending} active>
        {rows.length ? (
          <Row gutter={[16, 16]}>
            {rows.map((r) => (
              <Col key={r.vessel_id} xs={24} md={12} xxl={8}>
                <VesselReadiness r={r} />
              </Col>
            ))}
          </Row>
        ) : (
          <Empty />
        )}
      </Skeleton>
    </>
  )
}
