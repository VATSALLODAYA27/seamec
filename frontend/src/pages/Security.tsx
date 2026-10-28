import { LinkOutlined, PlusOutlined } from '@ant-design/icons'
import { App as AntApp, AutoComplete, Button, Card, Checkbox, Col, DatePicker, Dropdown, Flex, Form, Input, Radio, Row, Select, Space, Table, Tabs, Tag, Typography } from 'antd'
import dayjs, { type Dayjs } from 'dayjs'
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import {
  api,
  can,
  fmtDate,
  INCIDENT_KINDS,
  postJson,
  putJson,
  useAction,
  useSecurity,
  useVessels,
  ymd,
  type CameraRow,
  type DrillRow,
  type IncidentRow,
  type User,
  type VesselSecurityRow,
} from '../api'
import { ErrorAlert, StateTag } from '../components/Tags'
import { FormModal, Metric, PageHead, VesselLink } from '../components/ui'

const CAMERA_KIND: Record<CameraRow['kind'], string> = { FIXED: 'Fixed', PTZ: 'Pan-tilt-zoom', THERMAL: 'Thermal' }
const PLACES = ['Gangway', 'Bridge', 'Main deck aft', 'Main deck forward', 'Engine room', 'Helideck', 'Dive control', 'Accommodation entrance', 'Moon pool', 'Stern']
const LEVEL_COLOUR = { 1: 'success', 2: 'warning', 3: 'error' } as const
const minute = (d: Dayjs) => d.format('YYYY-MM-DDTHH:mm')

function Due({ d }: { d: VesselSecurityRow['drill'] }) {
  return (
    <>
      <StateTag kind="due" value={d.state} />
      <div className="muted">{d.last ? `last ${fmtDate(d.last)}${d.due ? ` · due ${fmtDate(d.due)}` : ''}` : 'none recorded'}</div>
    </>
  )
}

// ---------------- Vessels ----------------

function Vessels({ rows, me }: { rows: VesselSecurityRow[]; me: User }) {
  const [setting, setSetting] = useState<VesselSecurityRow | null>(null)
  const save = useAction((v: { level: number; sso: string }) => putJson(`/security/vessels/${setting!.vessel_id}`, v), 'Security level saved', () => setSetting(null))
  return (
    <>
      <Table<VesselSecurityRow>
        size="small"
        rowKey="vessel_id"
        dataSource={rows}
        pagination={false}
        scroll={{ x: 900 }}
        columns={[
          { title: 'Vessel', dataIndex: 'name', render: (n, r) => <><VesselLink id={r.vessel_id} name={n} /><div className="muted">SSO: {r.sso || 'not named'}</div></> },
          { title: 'Security level', dataIndex: 'level', render: (l: 1 | 2 | 3, r) => <><Tag color={LEVEL_COLOUR[l]}>Level {l}</Tag>{r.set_on && <div className="muted">since {fmtDate(r.set_on)}</div>}</> },
          { title: 'Drill (every 3 months)', dataIndex: 'drill', render: (d) => <Due d={d} /> },
          { title: 'Exercise (yearly)', dataIndex: 'exercise', render: (d) => <Due d={d} /> },
          {
            title: 'Cameras',
            dataIndex: 'cameras',
            render: (n, r) => (n ? <>{n - r.cameras_down.length} of {n} working{r.cameras_down.length > 0 && <div className="muted">down: {r.cameras_down.join(', ')}</div>}</> : <span className="muted">none listed</span>),
          },
          { title: 'Open incidents', dataIndex: 'open_incidents', render: (n, r) => (n ? <Tag color={r.open_high ? 'error' : 'warning'}>{n} open</Tag> : <span className="muted">none</span>) },
          { title: '', key: 'act', render: (_, r) => can.manage(me) && <Button size="small" onClick={() => setSetting(r)}>Set level</Button> },
        ]}
      />
      <FormModal<{ level: number; sso: string }>
        open={!!setting}
        title={`Security: ${setting?.name}`}
        okText="Save"
        initial={{ level: setting?.level, sso: setting?.sso }}
        pending={save.isPending}
        error={save.error}
        onSubmit={save.mutate}
        onClose={() => setSetting(null)}
      >
        <Form.Item name="level" label="ISPS security level" extra="Level 2 or 3 is set by the flag state or the port; record it here when it applies.">
          <Radio.Group optionType="button" options={[{ value: 1, label: '1 · Normal' }, { value: 2, label: '2 · Heightened' }, { value: 3, label: '3 · Exceptional' }]} />
        </Form.Item>
        <Form.Item name="sso" label="Ship security officer">
          <Input maxLength={80} />
        </Form.Item>
      </FormModal>
    </>
  )
}

// ---------------- Cameras ----------------

type CameraValues = Omit<CameraRow, 'id' | 'vessel_name' | 'status' | 'checked_on'>

function Cameras({ rows, me }: { rows: CameraRow[]; me: User }) {
  const vessels = useVessels()
  const [vessel, setVessel] = useState<string>()
  const [editing, setEditing] = useState<CameraRow | null | 'new'>(null)
  const [checking, setChecking] = useState<CameraRow | null>(null)
  const current = editing === 'new' ? null : editing
  const save = useAction((v: CameraValues) => (current ? putJson(`/security/cameras/${current.id}`, v) : postJson('/security/cameras', v)), 'Camera saved', () => setEditing(null))
  const check = useAction((v: { status: string; on: Dayjs; note?: string }) => postJson(`/security/cameras/${checking!.id}/check`, { ...v, on: ymd(v.on), note: v.note ?? '' }), 'Check recorded', () => setChecking(null))
  const remove = useAction((id: number) => api(`/security/cameras/${id}`, { method: 'DELETE' }), 'Camera removed')
  const { modal } = AntApp.useApp()
  const shown = rows.filter((c) => !vessel || c.vessel_id === vessel)
  return (
    <>
      <Flex gap={12} wrap style={{ marginBottom: 12 }}>
        <Select allowClear placeholder="Every vessel" style={{ width: 220 }} value={vessel} onChange={setVessel} options={vessels.data?.map((v) => ({ value: v.vessel_id, label: v.name }))} />
        <Button icon={<PlusOutlined />} onClick={() => setEditing('new')}>Add camera</Button>
      </Flex>
      <Table<CameraRow>
        size="small"
        rowKey="id"
        dataSource={shown}
        pagination={{ pageSize: 25 }}
        scroll={{ x: 800 }}
        locale={{ emptyText: 'No cameras listed yet. Add each vessel’s CCTV cameras to keep track of them.' }}
        columns={[
          { title: 'Vessel', dataIndex: 'vessel_name', render: (n, c) => <VesselLink id={c.vessel_id} name={n} /> },
          { title: 'Camera', dataIndex: 'name', render: (n, c) => <>{n}<div className="muted">{CAMERA_KIND[c.kind]}{c.note && ` · ${c.note}`}</div></> },
          { title: 'Status', dataIndex: 'status', render: (s, c) => <><StateTag kind="camera" value={s} /><div className="muted">checked {fmtDate(c.checked_on)}</div></> },
          {
            title: 'View',
            dataIndex: 'view_url',
            render: (u) =>
              u ? (
                <Button size="small" icon={<LinkOutlined />} href={u} target="_blank" rel="noopener noreferrer">
                  Open viewer
                </Button>
              ) : (
                <span className="muted">no link</span>
              ),
          },
          {
            title: '',
            key: 'act',
            render: (_, c) => (
              <Space size={4}>
                <Button size="small" onClick={() => setChecking(c)}>Record check</Button>
                <Dropdown
                  trigger={['click']}
                  menu={{ items: [{ key: 'edit', label: 'Edit' }, ...(can.manage(me) ? [{ key: 'remove', label: 'Remove', danger: true }] : [])], onClick: ({ key }) =>
                      key === 'edit'
                        ? setEditing(c)
                        : modal.confirm({ title: `Remove ${c.name} on ${c.vessel_name}?`, content: 'To keep its history, mark it offline instead.', okText: 'Remove', okButtonProps: { danger: true }, onOk: () => remove.mutate(c.id) }),
                  }}
                >
                  <Button size="small">More</Button>
                </Dropdown>
              </Space>
            ),
          },
        ]}
      />
      <FormModal<CameraValues>
        open={editing !== null}
        title={current ? `Edit ${current.name}` : 'Add camera'}
        okText="Save camera"
        initial={current ?? { kind: 'FIXED', vessel_id: vessel }}
        pending={save.isPending}
        error={save.error}
        onSubmit={save.mutate}
        onClose={() => setEditing(null)}
      >
        <Form.Item name="vessel_id" label="Vessel" rules={[{ required: true }]}>
          <Select disabled={!!current} options={vessels.data?.map((v) => ({ value: v.vessel_id, label: v.name }))} />
        </Form.Item>
        <Row gutter={16}>
          <Col span={14}>
            <Form.Item name="name" label="Where it looks" rules={[{ required: true, min: 2 }]}>
              <AutoComplete options={PLACES.map((p) => ({ value: p }))} filterOption placeholder="Gangway, bridge…" />
            </Form.Item>
          </Col>
          <Col span={10}>
            <Form.Item name="kind" label="Type">
              <Select options={Object.entries(CAMERA_KIND).map(([value, label]) => ({ value, label }))} />
            </Form.Item>
          </Col>
        </Row>
        <Form.Item
          name="view_url"
          label="Viewer address"
          extra="The camera's or video recorder's own web page (https). Live video stays on the vessel's system; this only opens it."
          rules={[{ pattern: /^$|^https:\/\/\S+$/, message: 'An https:// address' }]}
        >
          <Input placeholder="https://" />
        </Form.Item>
        <Form.Item name="note" label="Note">
          <Input maxLength={300} />
        </Form.Item>
      </FormModal>
      <FormModal<{ status: string; on: Dayjs; note?: string }>
        open={!!checking}
        title={`Check: ${checking?.vessel_name} · ${checking?.name}`}
        okText="Record check"
        initial={{ status: 'WORKING', on: dayjs() }}
        pending={check.isPending}
        error={check.error}
        onSubmit={check.mutate}
        onClose={() => setChecking(null)}
      >
        <Form.Item name="status" label="Found">
          <Radio.Group optionType="button" options={[{ value: 'WORKING', label: 'Working' }, { value: 'FAULT', label: 'Fault' }, { value: 'OFFLINE', label: 'Offline' }]} />
        </Form.Item>
        <Form.Item name="on" label="Checked on" rules={[{ required: true }]}>
          <DatePicker style={{ width: '100%' }} disabledDate={(d) => d.isAfter(dayjs(), 'day')} />
        </Form.Item>
        <Form.Item name="note" label="Note">
          <Input maxLength={300} placeholder="Lens cleaned, recording verified…" />
        </Form.Item>
      </FormModal>
    </>
  )
}

// ---------------- Incidents ----------------

type IncidentValues = { vessel_id: string; when: Dayjs; kind: string; severity: string; description: string; action_taken?: string; reported_to_authorities?: boolean; camera_id?: number }

function Incidents({ rows, cameras, me }: { rows: IncidentRow[]; cameras: CameraRow[]; me: User }) {
  const vessels = useVessels()
  const [logging, setLogging] = useState(false)
  const [closing, setClosing] = useState<IncidentRow | null>(null)
  const log = useAction(
    ({ when, ...v }: IncidentValues) => postJson('/security/incidents', { ...v, happened_at: minute(when), action_taken: v.action_taken ?? '', reported_to_authorities: !!v.reported_to_authorities, camera_id: v.camera_id ?? null }),
    'Incident logged',
    () => setLogging(false),
  )
  const close = useAction((v: { note: string }) => postJson(`/security/incidents/${closing!.id}/close`, v), 'Incident closed', () => setClosing(null))
  return (
    <>
      <Table<IncidentRow>
        size="small"
        rowKey="id"
        dataSource={rows}
        pagination={{ pageSize: 20 }}
        scroll={{ x: 1000 }}
        title={() => <Button icon={<PlusOutlined />} onClick={() => setLogging(true)}>Log incident</Button>}
        locale={{ emptyText: 'No security incidents logged.' }}
        expandable={{ expandedRowRender: (i) => <>{i.action_taken && <p><b>Action taken:</b> {i.action_taken}</p>}{i.closed_note && <p><b>Closed:</b> {i.closed_note}</p>}{!i.action_taken && !i.closed_note && 'No further notes.'}</>, rowExpandable: () => true }}
        columns={[
          { title: 'When', dataIndex: 'happened_at', render: (at) => dayjs(at).format('D MMM YYYY, HH:mm'), width: 150 },
          { title: 'Vessel', dataIndex: 'vessel_name', render: (n, i) => <VesselLink id={i.vessel_id} name={n} /> },
          { title: 'What', dataIndex: 'kind', render: (k, i) => <><b>{INCIDENT_KINDS[k as IncidentRow['kind']]}</b><div className="muted">{i.description}</div></> },
          { title: 'Severity', dataIndex: 'severity', render: (s) => <StateTag kind="severity" value={s} /> },
          { title: 'Reported', dataIndex: 'reported_to_authorities', render: (r, i) => <>{r ? <Tag>To authorities</Tag> : <span className="muted">internal</span>}{i.camera_name && <div className="muted">footage: {i.camera_name}</div>}</> },
          { title: 'Status', dataIndex: 'status', render: (s) => <StateTag kind="incident" value={s} /> },
          { title: '', key: 'act', render: (_, i) => i.status === 'OPEN' && can.manage(me) && <Button size="small" onClick={() => setClosing(i)}>Close</Button> },
        ]}
      />
      <FormModal<IncidentValues>
        open={logging}
        title="Log a security incident"
        okText="Log incident"
        width={640}
        initial={{ when: dayjs().startOf('hour'), kind: 'SUSPICIOUS_APPROACH', severity: 'LOW' }}
        pending={log.isPending}
        error={log.error}
        onSubmit={log.mutate}
        onClose={() => setLogging(false)}
      >
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item name="vessel_id" label="Vessel" rules={[{ required: true }]}>
              <Select options={vessels.data?.map((v) => ({ value: v.vessel_id, label: v.name }))} />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="when" label="When" rules={[{ required: true }]}>
              <DatePicker showTime={{ format: 'HH:mm' }} format="D MMM YYYY HH:mm" style={{ width: '100%' }} />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="kind" label="What">
              <Select options={Object.entries(INCIDENT_KINDS).map(([value, label]) => ({ value, label }))} />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="severity" label="Severity">
              <Radio.Group optionType="button" options={[{ value: 'LOW', label: 'Low' }, { value: 'MEDIUM', label: 'Medium' }, { value: 'HIGH', label: 'High' }]} />
            </Form.Item>
          </Col>
        </Row>
        <Form.Item name="description" label="What happened" rules={[{ required: true, min: 5 }]}>
          <Input.TextArea rows={3} maxLength={2000} />
        </Form.Item>
        <Form.Item name="action_taken" label="Action taken">
          <Input.TextArea rows={2} maxLength={2000} />
        </Form.Item>
        <Form.Item noStyle dependencies={['vessel_id']}>
          {({ getFieldValue }) => (
            <Form.Item name="camera_id" label="Camera with footage">
              <Select allowClear options={cameras.filter((c) => c.vessel_id === getFieldValue('vessel_id')).map((c) => ({ value: c.id, label: c.name }))} />
            </Form.Item>
          )}
        </Form.Item>
        <Form.Item name="reported_to_authorities" valuePropName="checked">
          <Checkbox>Reported to the authorities (port, coast guard, flag state)</Checkbox>
        </Form.Item>
      </FormModal>
      <FormModal<{ note: string }>
        open={!!closing}
        title="Close incident"
        okText="Close incident"
        pending={close.isPending}
        error={close.error}
        onSubmit={close.mutate}
        onClose={() => setClosing(null)}
      >
        <Typography.Paragraph type="secondary">{closing?.description}</Typography.Paragraph>
        <Form.Item name="note" label="Outcome" rules={[{ required: true, min: 3 }]}>
          <Input.TextArea rows={2} maxLength={1000} />
        </Form.Item>
      </FormModal>
    </>
  )
}

// ---------------- Drills ----------------

function Drills({ rows }: { rows: DrillRow[] }) {
  const vessels = useVessels()
  const [adding, setAdding] = useState(false)
  const add = useAction((v: { vessel_id: string; kind: string; on: Dayjs; scenario: string; note?: string }) =>
    postJson('/security/drills', { vessel_id: v.vessel_id, kind: v.kind, on_date: ymd(v.on), scenario: v.scenario, note: v.note ?? '' }), 'Recorded', () => setAdding(false))
  return (
    <>
      <Table<DrillRow>
        size="small"
        rowKey="id"
        dataSource={rows}
        pagination={{ pageSize: 20 }}
        title={() => <Button icon={<PlusOutlined />} onClick={() => setAdding(true)}>Record drill or exercise</Button>}
        locale={{ emptyText: 'No drills or exercises recorded yet.' }}
        columns={[
          { title: 'Date', dataIndex: 'on_date', render: fmtDate, width: 130 },
          { title: 'Vessel', dataIndex: 'vessel_name', render: (n, d) => <VesselLink id={d.vessel_id} name={n} /> },
          { title: 'Type', dataIndex: 'kind', render: (k) => (k === 'DRILL' ? 'Drill' : <Tag color="blue">Exercise</Tag>) },
          { title: 'Scenario', dataIndex: 'scenario', render: (s, d) => <>{s}{d.note && <div className="muted">{d.note}</div>}</> },
          { title: 'Recorded by', dataIndex: 'by' },
        ]}
      />
      <FormModal<{ vessel_id: string; kind: string; on: Dayjs; scenario: string; note?: string }>
        open={adding}
        title="Record a drill or exercise"
        okText="Record"
        initial={{ kind: 'DRILL', on: dayjs() }}
        pending={add.isPending}
        error={add.error}
        onSubmit={add.mutate}
        onClose={() => setAdding(false)}
      >
        <Form.Item name="vessel_id" label="Vessel" rules={[{ required: true }]}>
          <Select options={vessels.data?.map((v) => ({ value: v.vessel_id, label: v.name }))} />
        </Form.Item>
        <Form.Item name="kind" label="Type" extra="Drills at least every 3 months; an exercise at least once a calendar year, no more than 18 months apart (ISPS Code B/13).">
          <Radio.Group optionType="button" options={[{ value: 'DRILL', label: 'Drill' }, { value: 'EXERCISE', label: 'Exercise' }]} />
        </Form.Item>
        <Form.Item name="on" label="Held on" rules={[{ required: true }]}>
          <DatePicker style={{ width: '100%' }} disabledDate={(d) => d.isAfter(dayjs(), 'day')} />
        </Form.Item>
        <Form.Item name="scenario" label="Scenario" rules={[{ required: true, min: 3 }]}>
          <AutoComplete options={['Unauthorised boarding', 'Stowaway search', 'Bomb threat', 'Piracy approach', 'Cyber attack on bridge systems', 'Access control at gangway'].map((s) => ({ value: s }))} filterOption />
        </Form.Item>
        <Form.Item name="note" label="Note">
          <Input maxLength={500} />
        </Form.Item>
      </FormModal>
    </>
  )
}

/** Ship security under the ISPS Code: each vessel's security level, its cameras, incidents, and drills. */
export default function Security({ me }: { me: User }) {
  const [params, setParams] = useSearchParams()
  const sec = useSecurity()
  const d = sec.data
  const vessels = d?.vessels ?? []
  const down = (d?.cameras ?? []).filter((c) => c.status !== 'WORKING')
  const open = (d?.incidents ?? []).filter((i) => i.status === 'OPEN')
  const overdue = vessels.filter((v) => v.drill.state === 'OVERDUE' || v.exercise.state === 'OVERDUE')
  const raised = vessels.filter((v) => v.level > 1)

  return (
    <>
      <PageHead title="Security" sub="Ship security (ISPS Code): security level, cameras, incidents, drills and exercises." />
      <ErrorAlert error={sec.error} />
      <div className="metrics page-figures">
        <Metric label="Cameras working" value={`${(d?.cameras.length ?? 0) - down.length} of ${d?.cameras.length ?? 0}`} note={down.length ? `${down.length} need attention` : 'all working'} alert={down.length > 0} />
        <Metric label="Open incidents" value={open.length} note={`${open.filter((i) => i.severity === 'HIGH').length} high severity`} alert={open.some((i) => i.severity === 'HIGH')} />
        <Metric label="Drills or exercises overdue" value={`${overdue.length} of ${vessels.length}`} note="vessels" alert={overdue.length > 0} />
        <Metric label="Above security level 1" value={raised.length} note={raised.map((v) => v.name).join(', ') || 'all at level 1'} />
      </div>
      <Card loading={sec.isPending}>
        {d && (
          <Tabs
            activeKey={params.get('tab') ?? 'vessels'}
            onChange={(tab) => setParams({ tab })}
            items={[
              { key: 'vessels', label: 'Vessels', children: <Vessels rows={d.vessels} me={me} /> },
              { key: 'cameras', label: `Cameras${down.length ? ` (${down.length} down)` : ''}`, children: <Cameras rows={d.cameras} me={me} /> },
              { key: 'incidents', label: `Incidents${open.length ? ` (${open.length})` : ''}`, children: <Incidents rows={d.incidents} cameras={d.cameras} me={me} /> },
              { key: 'drills', label: 'Drills and exercises', children: <Drills rows={d.drills} /> },
            ]}
          />
        )}
      </Card>
    </>
  )
}
