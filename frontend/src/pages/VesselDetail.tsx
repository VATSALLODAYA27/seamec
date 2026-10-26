import { Card, Col, Descriptions, Result, Row, Spin, Table, Typography } from 'antd'
import { useMemo } from 'react'
import { Link, useParams } from 'react-router-dom'

import { ApiError, fmtDate, positionNote, money, moneyShort, num, useVessel } from '../api'
import FleetMap from '../components/FleetMap'
import { StateTag, TYPE_LABEL } from '../components/Tags'

export default function VesselDetail() {
  const { vesselId = '' } = useParams()
  const vessel = useVessel(vesselId)
  const map = useMemo(() => {
    const v = vessel.data
    if (!v?.position) return null
    return { points: [{ id: v.vessel_id, name: v.name, status: v.status, position: v.position }], track: v.track.map((t) => [t.lat, t.lon] as [number, number]) }
  }, [vessel.data])
  if (vessel.isPending) return <Spin />
  if (vessel.isError) {
    const notFound = vessel.error instanceof ApiError && vessel.error.status === 404
    return <Result status={notFound ? '404' : 'error'} title={notFound ? 'Vessel not found' : vessel.error.message} extra={<Link to="/vessels">All vessels</Link>} />
  }
  const v = vessel.data

  return (
    <Row gutter={[16, 16]}>
      <Col span={24}>
        <Card>
          <Typography.Title level={3} style={{ marginTop: 0 }}>
            {v.name} <StateTag kind="vessel" value={v.status} />
          </Typography.Title>
          <Descriptions size="small" column={{ xs: 1, md: 3 }}>
            <Descriptions.Item label="Type">{TYPE_LABEL[v.vessel_type]}</Descriptions.Item>
            <Descriptions.Item label="MMSI">{v.mmsi || '—'}</Descriptions.Item>
            <Descriptions.Item label="Owner">{v.entity}</Descriptions.Item>
            <Descriptions.Item label="IMO">{v.imo || '—'}</Descriptions.Item>
            <Descriptions.Item label="Flag">{v.flag}</Descriptions.Item>
            <Descriptions.Item label="Built">{v.built_year ?? '—'}</Descriptions.Item>
            <Descriptions.Item label="Running cost / day">{money(v.daily_opex)}</Descriptions.Item>
          </Descriptions>
        </Card>
      </Col>
      {map && (
        <Col span={24}>
          <Card
            title="Position and track"
            extra={
              <span className="muted">
                {v.position!.label} · {v.position!.lat.toFixed(3)}, {v.position!.lon.toFixed(3)}
                {' · '}
                {positionNote(v.position!)}
              </span>
            }
            styles={{ body: { padding: 0 } }}
          >
            <FleetMap points={map.points} track={map.track} height={300} />
          </Card>
        </Col>
      )}
      <Col xs={24} xl={12}>
        <Card title="Certificates" extra={<Link to="/certificates">Renew</Link>} style={{ height: '100%' }}>
          <Table
            size="small"
            rowKey="id"
            pagination={false}
            dataSource={v.certificates}
            columns={[
              { title: 'Certificate', dataIndex: 'name' },
              { title: 'Expires', dataIndex: 'expires_on', render: fmtDate },
              { title: 'Days left', dataIndex: 'days_left', align: 'right' },
              { title: 'State', dataIndex: 'state', render: (s) => <StateTag kind="cert" value={s} /> },
            ]}
          />
        </Card>
      </Col>
      <Col xs={24} xl={12}>
        <Card title="Contracts" style={{ height: '100%' }}>
          <Table
            size="small"
            rowKey="contract_no"
            pagination={false}
            dataSource={v.contracts}
            locale={{ emptyText: 'No contracts yet' }}
            columns={[
              { title: 'Contract', dataIndex: 'contract_no' },
              { title: 'Client', dataIndex: 'client', ellipsis: true },
              { title: 'Period', key: 'p', render: (_, c) => `${fmtDate(c.start_date)} – ${fmtDate(c.end_date)}` },
              { title: 'Day rate', dataIndex: 'operating_rate', align: 'right', render: moneyShort },
              { title: 'Status', dataIndex: 'status', render: (s) => <StateTag kind="contract" value={s} /> },
            ]}
          />
        </Card>
      </Col>
      <Col span={24}>
        <Card title="Latest daily reports" extra={<Link to={`/reports?vessel=${v.vessel_id}`}>All reports</Link>}>
          <Table
            size="small"
            rowKey="id"
            pagination={false}
            dataSource={v.reports}
            locale={{ emptyText: 'No reports' }}
            columns={[
              { title: 'Date', dataIndex: 'on_date', render: fmtDate },
              { title: 'Operating', dataIndex: 'operating_hrs', align: 'right' },
              { title: 'Standby', dataIndex: 'standby_hrs', align: 'right' },
              { title: 'Weather', dataIndex: 'weather_hrs', align: 'right' },
              { title: 'Breakdown', dataIndex: 'breakdown_hrs', align: 'right', render: (h) => (h ? <Typography.Text type="danger">{h}</Typography.Text> : 0) },
              { title: 'Dive hrs', dataIndex: 'dive_hrs', align: 'right', render: num },
              { title: 'Work done', dataIndex: 'work_done', ellipsis: true },
              { title: 'Status', dataIndex: 'status', render: (s) => <StateTag kind="report" value={s} /> },
            ]}
          />
        </Card>
      </Col>
    </Row>
  )
}
