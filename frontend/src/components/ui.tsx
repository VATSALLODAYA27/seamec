import { BulbOutlined, MoonOutlined } from '@ant-design/icons'
import { Button, Tooltip, Typography } from 'antd'
import { useContext, type ReactNode } from 'react'
import { Link } from 'react-router-dom'

import { DarkMode } from '../brand'

/** The title row at the top of every page, with the page's main buttons on the right. */
export function PageHead({ title, sub, actions }: { title: ReactNode; sub?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="page-head">
      <div>
        <Typography.Title level={2}>{title}</Typography.Title>
        {sub && <Typography.Text type="secondary">{sub}</Typography.Text>}
      </div>
      {actions}
    </div>
  )
}

/** One figure in the dashboard's metric strip; the whole cell links to the page behind it. */
export function Metric({ label, value, note, to, alert }: { label: string; value: ReactNode; note?: ReactNode; to: string; alert?: boolean }) {
  return (
    <Link to={to} className={`metric${alert ? ' alert' : ''}`}>
      <span className="muted">{label}</span>
      <b>{value}</b>
      {note && <span className="muted">{note}</span>}
    </Link>
  )
}

export const VesselLink = ({ id, name }: { id: string; name?: string | null }) => <Link to={`/vessels/${encodeURIComponent(id)}`}>{name || id}</Link>

export function ModeButton({ light }: { light?: boolean }) {
  const { dark, flip } = useContext(DarkMode)
  return (
    <Tooltip title={dark ? 'Light mode' : 'Dark mode'}>
      <Button type="text" shape="circle" aria-label="Switch light or dark mode" icon={dark ? <BulbOutlined /> : <MoonOutlined />} onClick={flip} style={light ? { color: '#fff' } : undefined} />
    </Tooltip>
  )
}
