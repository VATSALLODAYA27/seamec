import { Card, Table, Tag, Typography } from 'antd'
import { useMemo } from 'react'
import type { ColumnsType } from 'antd/es/table'

import { fmtDate, moneyShort, positionNote, useVessels, type Vessel } from '../api'
import FleetMap, { MapLegend } from '../components/FleetMap'
import { PageHead, VesselLink } from '../components/ui'
import { ErrorAlert, StateTag, TYPE_LABEL, stateOptions } from '../components/Tags'

const columns: ColumnsType<Vessel> = [
  { title: 'Vessel', dataIndex: 'name', render: (name, v) => <VesselLink id={v.vessel_id} name={name} /> },
  {
    title: 'Type',
    dataIndex: 'vessel_type',
    filters: Object.entries(TYPE_LABEL).map(([value, text]) => ({ value, text })),
    onFilter: (value, v) => v.vessel_type === value,
    render: (t) => TYPE_LABEL[t],
  },
  {
    title: 'IMO / MMSI',
    key: 'ids',
    render: (_, v) => (
      <span className="num">
        {v.imo || '—'}
        <div className="muted">{v.mmsi ? `MMSI ${v.mmsi}` : 'No MMSI: not on AIS'}</div>
      </span>
    ),
  },
  { title: 'Flag', dataIndex: 'flag', render: (f) => f || '—' },
  { title: 'Owner', dataIndex: 'entity' },
  { title: 'Status', dataIndex: 'status', filters: stateOptions('vessel'), onFilter: (value, v) => v.status === value, render: (s) => <StateTag kind="vessel" value={s} /> },
  {
    title: 'Current contract',
    key: 'contract',
    render: (_, v) =>
      v.contract_no ? (
        <>
          {v.client}
          <div className="muted">
            {v.contract_no} · to {fmtDate(v.contract_end)}
          </div>
        </>
      ) : (
        <Typography.Text type="secondary">—</Typography.Text>
      ),
  },
  {
    title: 'Certificates',
    key: 'certs',
    render: (_, v) =>
      v.certs_expired ? (
        <Tag color="error">{v.certs_expired} expired</Tag>
      ) : v.certs_expiring ? (
        <Tag color="warning">{v.certs_expiring} expiring</Tag>
      ) : (
        <Tag color="success">All valid</Tag>
      ),
  },
  {
    title: 'Last position',
    dataIndex: 'position',
    render: (p: Vessel['position'], v: Vessel) =>
      p ? (
        <>
          {p.label}
          <div className="muted" style={p.stale ? { color: 'var(--bad-text, #c62828)' } : undefined}>
            {positionNote(p)}
          </div>
        </>
      ) : (
        <Typography.Text type="secondary">{v.base_port || 'Unknown'}</Typography.Text>
      ),
  },
  { title: 'Running cost / day', dataIndex: 'daily_opex', align: 'right', render: (c: number) => (c ? moneyShort(c) : <Typography.Text type="secondary">Not on file</Typography.Text>) },
]

export default function Vessels() {
  const vessels = useVessels()
  // Memoised so the map is not rebuilt on every render.
  const points = useMemo(
    () => (vessels.data ?? []).filter((v) => v.position).map((v) => ({ id: v.vessel_id, name: v.name, status: v.status, position: v.position! })),
    [vessels.data],
  )
  return (
    <>
      <PageHead title="Vessels" sub="Diving support vessels, support vessel, accommodation barge and bulk carriers" />
      <Card title="Where the fleet is" extra={<MapLegend />} style={{ marginBottom: 16 }} styles={{ body: { padding: 0 } }}>
        <FleetMap points={points} />
      </Card>
      <Card>
        <ErrorAlert error={vessels.error} />
        <Table size="middle" rowKey="vessel_id" columns={columns} dataSource={vessels.data} loading={vessels.isPending} pagination={false} />
      </Card>
    </>
  )
}
