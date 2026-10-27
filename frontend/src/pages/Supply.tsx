import { CheckOutlined, DownOutlined, MinusCircleOutlined, PlusOutlined, StarFilled } from '@ant-design/icons'
import { Button, Card, Col, DatePicker, Dropdown, Flex, Form, Input, InputNumber, Popconfirm, Row, Select, Space, Switch, Table, Tabs, Tag, Tooltip, Typography } from 'antd'
import type { Dayjs } from 'dayjs'
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import {
  can,
  fmtDate,
  locationOptions,
  money,
  moneyShort,
  num,
  postJson,
  putJson,
  useAction,
  useEquipment,
  useParts,
  usePurchaseOrders,
  useReorder,
  useStock,
  useVendors,
  useVessels,
  ymd,
  type PartRow,
  type PurchaseOrderRow,
  type StockRow,
  type User,
  type VendorRow,
} from '../api'
import Documents from '../components/Documents'
import { ErrorAlert, StateTag } from '../components/Tags'
import { FormModal, Metric, PageHead, RUPEES } from '../components/ui'

const CATEGORY: Record<VendorRow['category'], string> = { SPARES: 'Spares', STORES: 'Stores', SERVICE: 'Service', AGENT: 'Port agent', YARD: 'Shipyard' }

// ---------------- Stock ----------------

function Stock({ me }: { me: User }) {
  const stock = useStock()
  const vessels = useVessels()
  const [place, setPlace] = useState<string>()
  const [onlyShort, setOnlyShort] = useState(false)
  const [moving, setMoving] = useState<StockRow | null>(null)
  const [counting, setCounting] = useState<StockRow | null>(null)
  const [levelFor, setLevelFor] = useState<StockRow | null>(null)
  const equipment = useEquipment(levelFor && levelFor.location !== 'SHORE' ? levelFor.location : '')
  const transfer = useAction((b: { part_id: number; from_location: string; to_location: string; qty: number }) => postJson<{ jobs_released: number }>('/stock/transfer', b),
    (out) => (out.jobs_released ? `Sent; ${out.jobs_released} waiting job${out.jobs_released > 1 ? 's' : ''} got the spare` : 'Sent'), () => setMoving(null))
  const adjust = useAction((b: { part_id: number; location: string; qty: number; reason: string }) => postJson('/stock/adjust', b), 'Count recorded', () => setCounting(null))
  const level = useAction((b: { part_id: number; location: string; min_qty: number; equipment_id?: number | null; bin?: string }) => putJson('/stock/level', b), 'Minimum saved', () => setLevelFor(null))
  const manage = can.manage(me)
  const rows = (stock.data ?? []).filter((s) => (!place || s.location === place) && (!onlyShort || s.short))

  return (
    <>
      <Flex gap={12} wrap align="center" style={{ marginBottom: 12 }}>
        <Select allowClear placeholder="Every place" style={{ width: 240 }} value={place} onChange={setPlace} options={locationOptions(vessels.data)} />
        <Space>
          <Switch checked={onlyShort} onChange={setOnlyShort} aria-label="Only below minimum" /> Only below minimum
        </Space>
      </Flex>
      <Table<StockRow>
        size="small"
        rowKey="id"
        loading={stock.isPending}
        dataSource={rows}
        pagination={{ pageSize: 25 }}
        scroll={{ x: 900 }}
        columns={[
          { title: 'Part', dataIndex: 'part', render: (p, s) => <>{p}<div className="muted">{s.part_no}{s.bin && ` · bin ${s.bin}`}</div></> },
          { title: 'Where', dataIndex: 'location_name' },
          { title: 'Held for', dataIndex: 'equipment', render: (e, s) => (e ? <>{e} {s.critical && <Tag color="red">Critical</Tag>}</> : <span className="muted">—</span>) },
          {
            title: 'On hand',
            dataIndex: 'qty',
            align: 'right',
            sorter: (a, b) => Number(a.short) - Number(b.short),
            render: (q, s) => (
              <>
                <Typography.Text strong type={s.short ? (s.critical && q <= 0 ? 'danger' : 'warning') : undefined}>{num(q)} {s.unit}</Typography.Text>
                <div className="muted">min {num(s.min_qty)}{s.waiting_qty ? ` · ${num(s.waiting_qty)} waited for` : ''}</div>
              </>
            ),
          },
          { title: 'Value', dataIndex: 'value', align: 'right', render: moneyShort },
          {
            title: '',
            key: 'act',
            render: (_, s) => (
              <Dropdown
                trigger={['click']}
                menu={{
                  items: [
                    { key: 'move', label: 'Send to…', disabled: s.qty <= 0 },
                    ...(manage ? [{ key: 'count', label: 'Record a count' }, { key: 'level', label: 'Minimum and equipment' }] : []),
                  ],
                  onClick: ({ key }) => (key === 'move' ? setMoving(s) : key === 'count' ? setCounting(s) : setLevelFor(s)),
                }}
              >
                <Button size="small">
                  Stock <DownOutlined />
                </Button>
              </Dropdown>
            ),
          },
        ]}
      />
      <FormModal<{ to_location: string; qty: number }>
        open={!!moving}
        title={`Send ${moving?.part} from ${moving?.location_name}`}
        okText="Send"
        initial={{ qty: 1, to_location: moving?.location === 'SHORE' ? undefined : 'SHORE' }}
        pending={transfer.isPending}
        error={transfer.error}
        onSubmit={(v) => transfer.mutate({ part_id: moving!.part_id, from_location: moving!.location, ...v })}
        onClose={() => setMoving(null)}
      >
        <Typography.Paragraph type="secondary">Sending from the shore warehouse to a vessel books the spares' cost to that vessel.</Typography.Paragraph>
        <Form.Item name="to_location" label="To" rules={[{ required: true }]}>
          <Select options={locationOptions(vessels.data).filter((o) => o.value !== moving?.location)} />
        </Form.Item>
        <Form.Item name="qty" label={`Quantity (${moving?.qty} available)`} rules={[{ required: true }]}>
          <InputNumber min={0.001} max={moving?.qty} style={{ width: '100%' }} />
        </Form.Item>
      </FormModal>
      <FormModal<{ qty: number; reason: string }>
        open={!!counting}
        title={`Count: ${counting?.part} at ${counting?.location_name}`}
        okText="Save count"
        initial={{ qty: counting?.qty }}
        pending={adjust.isPending}
        error={adjust.error}
        onSubmit={(v) => adjust.mutate({ part_id: counting!.part_id, location: counting!.location, ...v })}
        onClose={() => setCounting(null)}
      >
        <Form.Item name="qty" label="Counted quantity" rules={[{ required: true }]}>
          <InputNumber min={0} style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item name="reason" label="Reason for the difference" rules={[{ required: true, min: 3 }]}>
          <Input placeholder="Quarterly stock count" />
        </Form.Item>
      </FormModal>
      <FormModal<{ min_qty: number; equipment_id?: number | null; bin?: string }>
        open={!!levelFor}
        title={`${levelFor?.part} at ${levelFor?.location_name}`}
        okText="Save"
        initial={{ min_qty: levelFor?.min_qty, equipment_id: levelFor?.equipment_id, bin: levelFor?.bin }}
        pending={level.isPending}
        error={level.error}
        onSubmit={(v) => level.mutate({ part_id: levelFor!.part_id, location: levelFor!.location, ...v, equipment_id: v.equipment_id ?? null })}
        onClose={() => setLevelFor(null)}
      >
        <Form.Item name="min_qty" label="Minimum to keep" rules={[{ required: true }]}>
          <InputNumber min={0} style={{ width: '100%' }} />
        </Form.Item>
        {levelFor?.location !== 'SHORE' && (
          <Form.Item name="equipment_id" label="Held for equipment" extra="A spare for critical equipment counts for hire readiness (ISM 10.3): none on board stops the vessel going on hire.">
            <Select allowClear options={equipment.data?.map((e) => ({ value: e.id, label: `${e.name}${e.critical ? ' (critical)' : ''}` }))} />
          </Form.Item>
        )}
        <Form.Item name="bin" label="Bin / location on board">
          <Input />
        </Form.Item>
      </FormModal>
    </>
  )
}

// ---------------- Reorder ----------------

function Reorder() {
  const reorder = useReorder()
  const vessels = useVessels()
  const [place, setPlace] = useState<string>()
  const raise = useAction((location: string) => postJson<{ orders: string[]; skipped: string[] }>('/stock/reorder', { location }),
    (out) => `Drafted ${out.orders.join(', ')}${out.skipped.length ? `; no vendor for ${out.skipped.join(', ')}` : ''}`)
  const places = [...new Set((reorder.data ?? []).filter((r) => r.to_order).map((r) => r.location))]
  const names = Object.fromEntries(locationOptions(vessels.data).map((o) => [o.value, o.label]))
  const chosen = place && places.includes(place) ? place : places[0]
  return (
    <>
      <Flex gap={12} align="center" wrap style={{ marginBottom: 12 }}>
        <Typography.Text type="secondary">Everything below its minimum. Draft orders for one place at a time, one per preferred vendor:</Typography.Text>
        <Select style={{ width: 220 }} value={chosen} onChange={setPlace} options={places.map((p) => ({ value: p, label: names[p] ?? p }))} placeholder="Nothing to order" />
        <Button type="primary" disabled={!chosen} loading={raise.isPending} onClick={() => raise.mutate(chosen!)}>
          Draft orders
        </Button>
      </Flex>
      <Table<StockRow>
        size="small"
        rowKey="id"
        loading={reorder.isPending}
        dataSource={reorder.data}
        pagination={false}
        columns={[
          { title: 'Part', dataIndex: 'part', render: (p, s) => <>{p} {s.critical && <Tag color="red">Critical</Tag>}<div className="muted">{s.part_no}</div></> },
          { title: 'Where', dataIndex: 'location_name' },
          { title: 'On hand / minimum', key: 'q', align: 'right', render: (_, s) => `${num(s.qty)} / ${num(s.min_qty)} ${s.unit}` },
          { title: 'Already on order', dataIndex: 'on_order', align: 'right', render: (q) => (q ? num(q) : '—') },
          { title: 'To order', dataIndex: 'to_order', align: 'right', render: (q) => (q ? <b>{num(q)}</b> : <span className="muted">covered</span>) },
        ]}
      />
    </>
  )
}

// ---------------- Purchase orders ----------------

type POValues = { vendor_id: number; deliver_to: string; needed_by?: Dayjs; note?: string; lines: { part_id?: number; description?: string; qty: number; unit_price: number }[] }

function Orders({ me }: { me: User }) {
  const orders = usePurchaseOrders()
  const vendors = useVendors()
  const parts = useParts()
  const vessels = useVessels()
  const [adding, setAdding] = useState(false)
  const [receiving, setReceiving] = useState<PurchaseOrderRow | null>(null)
  const [showClosed, setShowClosed] = useState(false)
  const create = useAction(({ needed_by, ...v }: POValues) => postJson('/purchase-orders', { ...v, needed_by: ymd(needed_by), lines: v.lines.map((l) => ({ ...l, description: l.description ?? '' })) }), 'Order drafted', () => setAdding(false))
  const step = useAction(({ po, action }: { po: string; action: string }) => postJson(`/purchase-orders/${encodeURIComponent(po)}/${action}`), 'Order updated')
  const receive = useAction((v: { po: string; lines: Record<number, number> }) => postJson(`/purchase-orders/${encodeURIComponent(v.po)}/receive`, { lines: v.lines }), 'Delivery recorded', () => setReceiving(null))
  const manage = can.manage(me)
  const partById = Object.fromEntries((parts.data ?? []).map((p) => [p.id, p]))
  const rows = (orders.data ?? []).filter((o) => showClosed || !['RECEIVED', 'CANCELLED'].includes(o.status))

  return (
    <>
      <Flex gap={12} align="center" style={{ marginBottom: 12 }}>
        <Button icon={<PlusOutlined />} onClick={() => setAdding(true)}>New order</Button>
        <Space>
          <Switch checked={showClosed} onChange={setShowClosed} aria-label="Show received and cancelled" /> Show received and cancelled
        </Space>
      </Flex>
      <Table<PurchaseOrderRow>
        size="small"
        rowKey="po_no"
        loading={orders.isPending}
        dataSource={rows}
        pagination={{ pageSize: 20 }}
        scroll={{ x: 1000 }}
        expandable={{
          expandedRowRender: (o) => (
            <Table
              size="small"
              rowKey="id"
              pagination={false}
              dataSource={o.lines}
              columns={[
                { title: 'Item', dataIndex: 'description', render: (d, l) => <>{d}{l.part_no && <span className="muted"> · {l.part_no}</span>}</> },
                { title: 'Ordered', dataIndex: 'qty', align: 'right', render: (q, l) => `${num(q)} ${l.unit}` },
                { title: 'Received', dataIndex: 'received_qty', align: 'right', render: num },
                { title: 'Price', dataIndex: 'unit_price', align: 'right', render: money },
                { title: 'Amount', key: 'a', align: 'right', render: (_, l) => money(l.qty * l.unit_price) },
              ]}
            />
          ),
        }}
        columns={[
          { title: 'Order', dataIndex: 'po_no', render: (no, o) => <><b>{no}</b><div className="muted">{o.note || `${o.lines.length} line${o.lines.length > 1 ? 's' : ''}`}</div></> },
          { title: 'Vendor', dataIndex: 'vendor_name' },
          { title: 'Deliver to', dataIndex: 'deliver_to_name', render: (n, o) => <>{n}{o.needed_by && <div className="muted">by {fmtDate(o.needed_by)}</div>}</> },
          {
            title: 'Total',
            dataIndex: 'total',
            align: 'right',
            render: (t, o) => (
              <>
                {moneyShort(t)}
                {o.needs_admin && o.status === 'DRAFT' && <div><Tooltip title="Above ₹10 lakh: an admin approves"><Tag>Admin approves</Tag></Tooltip></div>}
              </>
            ),
          },
          { title: 'Raised', dataIndex: 'raised_on', render: (d, o) => <>{fmtDate(d)}<div className="muted">by {o.raised_by}</div></> },
          { title: 'Status', dataIndex: 'status', render: (s) => <StateTag kind="po" value={s} /> },
          {
            title: '',
            key: 'act',
            width: 190,
            render: (_, o) => (
              <Space size={4}>
                <Documents entity="po" entityKey={o.po_no} title={o.po_no} canUpload={manage} defaultKind="INVOICE" />
                {o.status === 'DRAFT' && manage && (!o.needs_admin || me.role === 'admin') && (
                  <Button size="small" type="primary" icon={<CheckOutlined />} onClick={() => step.mutate({ po: o.po_no, action: 'approve' })}>Approve</Button>
                )}
                {o.status === 'APPROVED' && manage && <Button size="small" onClick={() => step.mutate({ po: o.po_no, action: 'order' })}>Sent to vendor</Button>}
                {['ORDERED', 'PART_RECEIVED'].includes(o.status) && <Button size="small" type="primary" onClick={() => setReceiving(o)}>Receive</Button>}
                {['DRAFT', 'APPROVED'].includes(o.status) && manage && (
                  <Popconfirm title="Cancel this order?" onConfirm={() => step.mutate({ po: o.po_no, action: 'cancel' })}>
                    <Button size="small" type="text" danger>Cancel</Button>
                  </Popconfirm>
                )}
              </Space>
            ),
          },
        ]}
      />
      <FormModal<POValues>
        open={adding}
        title="New purchase order"
        okText="Draft order"
        width={820}
        initial={{ deliver_to: 'SHORE', lines: [{ qty: 1, unit_price: 0 }] }}
        pending={create.isPending}
        error={create.error}
        onSubmit={create.mutate}
        onClose={() => setAdding(false)}
      >
        <Row gutter={16}>
          <Col span={9}>
            <Form.Item name="vendor_id" label="Vendor" rules={[{ required: true }]}>
              <Select showSearch optionFilterProp="label" options={vendors.data?.filter((v) => v.approved && ['SPARES', 'STORES', 'SERVICE'].includes(v.category)).map((v) => ({ value: v.id, label: v.name }))} />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item name="deliver_to" label="Deliver to">
              <Select options={locationOptions(vessels.data)} />
            </Form.Item>
          </Col>
          <Col span={7}>
            <Form.Item name="needed_by" label="Needed by">
              <DatePicker style={{ width: '100%' }} />
            </Form.Item>
          </Col>
        </Row>
        <Form.List name="lines">
          {(fields, { add, remove }) => (
            <>
              {fields.map((f) => (
                <Row key={f.key} gutter={8} align="top">
                  <Col span={10}>
                    <Form.Item noStyle shouldUpdate>
                      {({ setFieldValue }) => (
                        <Form.Item name={[f.name, 'part_id']} label={f.name === 0 ? 'Part' : undefined}>
                          <Select
                            allowClear
                            showSearch
                            optionFilterProp="label"
                            placeholder="Catalogue part, or leave empty"
                            options={parts.data?.map((p) => ({ value: p.id, label: `${p.name} (${p.part_no})` }))}
                            onChange={(id) => id && setFieldValue(['lines', f.name, 'unit_price'], partById[id]?.unit_cost)}
                          />
                        </Form.Item>
                      )}
                    </Form.Item>
                    <Form.Item noStyle dependencies={[['lines', f.name, 'part_id']]}>
                      {({ getFieldValue }) =>
                        !getFieldValue(['lines', f.name, 'part_id']) && (
                          <Form.Item name={[f.name, 'description']} rules={[{ required: true, message: 'Describe the item or service' }]}>
                            <Input placeholder="Service or one-off item" />
                          </Form.Item>
                        )
                      }
                    </Form.Item>
                  </Col>
                  <Col span={4}>
                    <Form.Item name={[f.name, 'qty']} label={f.name === 0 ? 'Qty' : undefined} rules={[{ required: true }]}>
                      <InputNumber min={0.001} style={{ width: '100%' }} />
                    </Form.Item>
                  </Col>
                  <Col span={8}>
                    <Form.Item name={[f.name, 'unit_price']} label={f.name === 0 ? 'Unit price' : undefined} rules={[{ required: true }]}>
                      <InputNumber {...RUPEES} step={1000} />
                    </Form.Item>
                  </Col>
                  <Col span={2} style={{ paddingTop: f.name === 0 ? 30 : 0 }}>
                    {fields.length > 1 && <Button type="text" icon={<MinusCircleOutlined />} onClick={() => remove(f.name)} aria-label="Remove line" />}
                  </Col>
                </Row>
              ))}
              <Button type="dashed" icon={<PlusOutlined />} onClick={() => add({ qty: 1, unit_price: 0 })}>Add line</Button>
            </>
          )}
        </Form.List>
        <Form.Item name="note" label="Note" style={{ marginTop: 16 }}>
          <Input maxLength={500} />
        </Form.Item>
      </FormModal>
      <FormModal<{ lines: Record<string, number> }>
        open={!!receiving}
        title={`Receive ${receiving?.po_no} at ${receiving?.deliver_to_name}`}
        okText="Record delivery"
        initial={{ lines: Object.fromEntries((receiving?.lines ?? []).map((l) => [String(l.id), l.qty - l.received_qty])) }}
        pending={receive.isPending}
        error={receive.error}
        onSubmit={(v) => receive.mutate({ po: receiving!.po_no, lines: Object.fromEntries(Object.entries(v.lines).filter(([, q]) => q > 0).map(([id, q]) => [Number(id), q])) })}
        onClose={() => setReceiving(null)}
      >
        <Typography.Paragraph type="secondary">What arrived now. Spares delivered to a vessel go to any job there waiting for them, and their cost is booked to the vessel.</Typography.Paragraph>
        {receiving?.lines.map((l) => (
          <Form.Item key={l.id} name={['lines', String(l.id)]} label={`${l.description} (${num(l.qty - l.received_qty)} ${l.unit} to come)`}>
            <InputNumber min={0} max={l.qty - l.received_qty} style={{ width: '100%' }} />
          </Form.Item>
        ))}
      </FormModal>
    </>
  )
}

// ---------------- Parts and vendors ----------------

function Parts({ me }: { me: User }) {
  const parts = useParts()
  const vendors = useVendors()
  const [adding, setAdding] = useState(false)
  const create = useAction((v: Omit<PartRow, 'id' | 'vendor_name' | 'total_qty'>) => postJson('/parts', v), 'Part added', () => setAdding(false))
  return (
    <>
      <Table<PartRow>
        size="small"
        rowKey="id"
        loading={parts.isPending}
        dataSource={parts.data}
        pagination={{ pageSize: 25 }}
        title={() => can.manage(me) && <Button icon={<PlusOutlined />} onClick={() => setAdding(true)}>New part</Button>}
        columns={[
          { title: 'Part', dataIndex: 'name', render: (n, p) => <>{n}<div className="muted">{p.part_no}{p.maker && ` · ${p.maker}`}</div></> },
          { title: 'Preferred vendor', dataIndex: 'vendor_name', render: (v) => v ?? <span className="muted">—</span> },
          { title: 'Lead time', dataIndex: 'lead_days', align: 'right', render: (d) => `${d} days` },
          { title: 'Last price', dataIndex: 'unit_cost', align: 'right', render: (c, p) => `${money(c)} / ${p.unit}` },
          { title: 'Held across fleet', dataIndex: 'total_qty', align: 'right', render: (q, p) => `${num(q)} ${p.unit}` },
        ]}
      />
      <FormModal<Omit<PartRow, 'id' | 'vendor_name' | 'total_qty'>> open={adding} title="New part" okText="Add part" initial={{ unit: 'pc', lead_days: 14, unit_cost: 0 }} pending={create.isPending} error={create.error} onSubmit={create.mutate} onClose={() => setAdding(false)}>
        <Row gutter={16}>
          <Col span={10}><Form.Item name="part_no" label="Part number" rules={[{ required: true, min: 2 }]}><Input /></Form.Item></Col>
          <Col span={14}><Form.Item name="name" label="Name" rules={[{ required: true, min: 2 }]}><Input /></Form.Item></Col>
          <Col span={12}><Form.Item name="maker" label="Maker"><Input /></Form.Item></Col>
          <Col span={6}><Form.Item name="unit" label="Unit"><Input /></Form.Item></Col>
          <Col span={6}><Form.Item name="lead_days" label="Lead days"><InputNumber min={0} style={{ width: '100%' }} /></Form.Item></Col>
          <Col span={12}><Form.Item name="unit_cost" label="Price"><InputNumber {...RUPEES} step={1000} /></Form.Item></Col>
          <Col span={12}>
            <Form.Item name="vendor_id" label="Preferred vendor">
              <Select allowClear options={vendors.data?.filter((v) => ['SPARES', 'STORES'].includes(v.category)).map((v) => ({ value: v.id, label: v.name }))} />
            </Form.Item>
          </Col>
        </Row>
      </FormModal>
    </>
  )
}

export function Vendors({ me }: { me: User }) {
  const vendors = useVendors()
  const [editing, setEditing] = useState<VendorRow | null | 'new'>(null)
  const current = editing === 'new' ? null : editing
  const save = useAction((v: Omit<VendorRow, 'id' | 'spend'>) => (current ? putJson(`/vendors/${current.id}`, v) : postJson('/vendors', v)), 'Vendor saved', () => setEditing(null))
  const manage = can.manage(me)
  return (
    <>
      <Table<VendorRow>
        size="small"
        rowKey="id"
        loading={vendors.isPending}
        dataSource={vendors.data}
        pagination={{ pageSize: 25 }}
        scroll={{ x: 900 }}
        title={() => manage && <Button icon={<PlusOutlined />} onClick={() => setEditing('new')}>New vendor</Button>}
        columns={[
          { title: 'Vendor', dataIndex: 'name', render: (n, v) => <>{n}<div className="muted">{v.country}{v.tax_id && ` · ${v.tax_id}`}</div></> },
          { title: 'Type', dataIndex: 'category', filters: Object.entries(CATEGORY).map(([value, text]) => ({ value, text })), onFilter: (val, v) => v.category === val, render: (c) => CATEGORY[c as VendorRow['category']] },
          { title: 'Contact', dataIndex: 'contact', render: (c, v) => <>{c || '—'}<div className="muted">{[v.email, v.phone].filter(Boolean).join(' · ')}</div></> },
          { title: 'Rating', dataIndex: 'rating', render: (r) => (r ? <span style={{ color: '#B86E00', whiteSpace: 'nowrap' }}>{Array.from({ length: r }, (_, i) => <StarFilled key={i} />)}</span> : <span className="muted">Not rated</span>) },
          { title: 'Terms', dataIndex: 'payment_terms_days', render: (d) => (d ? `${d} days` : 'Advance') },
          { title: 'Spend', dataIndex: 'spend', align: 'right', render: moneyShort },
          { title: 'Approved', dataIndex: 'approved', render: (a) => (a ? <Tag color="success">Approved</Tag> : <Tag color="warning">Not approved</Tag>) },
          { title: '', key: 'act', render: (_, v) => manage && <Button size="small" onClick={() => setEditing(v)}>Edit</Button> },
        ]}
      />
      <FormModal<Omit<VendorRow, 'id' | 'spend'>>
        open={editing !== null}
        title={current ? `Edit ${current.name}` : 'New vendor'}
        okText="Save vendor"
        width={640}
        initial={current ?? { category: 'SPARES', approved: true, payment_terms_days: 30 }}
        pending={save.isPending}
        error={save.error}
        onSubmit={save.mutate}
        onClose={() => setEditing(null)}
      >
        <Row gutter={16}>
          <Col span={14}><Form.Item name="name" label="Name" rules={[{ required: true, min: 2 }]}><Input /></Form.Item></Col>
          <Col span={10}>
            <Form.Item name="category" label="Type">
              <Select options={Object.entries(CATEGORY).map(([value, label]) => ({ value, label }))} />
            </Form.Item>
          </Col>
          <Col span={8}><Form.Item name="country" label="Country"><Input /></Form.Item></Col>
          <Col span={8}><Form.Item name="tax_id" label="GSTIN / tax number"><Input /></Form.Item></Col>
          <Col span={8}><Form.Item name="payment_terms_days" label="Payment terms (days)"><InputNumber min={0} max={180} style={{ width: '100%' }} /></Form.Item></Col>
          <Col span={8}><Form.Item name="contact" label="Contact person"><Input /></Form.Item></Col>
          <Col span={8}><Form.Item name="email" label="Email" rules={[{ type: 'email' }]}><Input /></Form.Item></Col>
          <Col span={8}><Form.Item name="phone" label="Phone"><Input /></Form.Item></Col>
          <Col span={12}>
            <Form.Item name="rating" label="Rating (last evaluation)">
              <Select allowClear options={[1, 2, 3, 4, 5].map((r) => ({ value: r, label: `${r} of 5` }))} />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="approved" label="Approved vendor" valuePropName="checked" extra="Only approved vendors get orders.">
              <Switch />
            </Form.Item>
          </Col>
        </Row>
      </FormModal>
    </>
  )
}

/** Spares and stores on each vessel and ashore, what to reorder, purchase orders and the vendor list. */
export default function Supply({ me }: { me: User }) {
  const [params, setParams] = useSearchParams()
  const stock = useStock()
  const orders = usePurchaseOrders()
  const rows = stock.data ?? []
  const criticalShort = rows.filter((s) => s.critical && s.short)
  const toApprove = (orders.data ?? []).filter((o) => o.status === 'DRAFT')
  const withVendors = (orders.data ?? []).filter((o) => ['ORDERED', 'PART_RECEIVED'].includes(o.status))

  return (
    <>
      <PageHead title="Supply" sub="Spares on board and ashore, purchase orders and vendors." />
      <ErrorAlert error={stock.error ?? orders.error} />
      <div className="metrics page-figures">
        <Metric label="Stock value" value={moneyShort(rows.reduce((s, r) => s + r.value, 0))} note={`${rows.filter((r) => r.location === 'SHORE').length} lines ashore`} />
        <Metric label="Critical spares below minimum" value={criticalShort.length} note={`${criticalShort.filter((s) => s.qty <= 0).length} with none on board`} alert={criticalShort.some((s) => s.qty <= 0)} />
        <Metric label="Orders to approve" value={toApprove.length} note={moneyShort(toApprove.reduce((s, o) => s + o.total, 0))} />
        <Metric label="With vendors" value={withVendors.length} note={moneyShort(withVendors.reduce((s, o) => s + o.total, 0))} />
      </div>
      <Card>
        <Tabs
          activeKey={params.get('tab') ?? 'stock'}
          onChange={(tab) => setParams({ tab })}
          items={[
            { key: 'stock', label: 'Stock', children: <Stock me={me} /> },
            { key: 'reorder', label: 'To reorder', children: <Reorder /> },
            { key: 'orders', label: `Purchase orders${toApprove.length ? ` (${toApprove.length})` : ''}`, children: <Orders me={me} /> },
            { key: 'parts', label: 'Parts', children: <Parts me={me} /> },
            { key: 'vendors', label: 'Vendors', children: <Vendors me={me} /> },
          ]}
        />
      </Card>
    </>
  )
}
