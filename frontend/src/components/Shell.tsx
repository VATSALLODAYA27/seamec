import {
  AuditOutlined,
  BuildOutlined,
  EnvironmentOutlined,
  FieldTimeOutlined,
  LineChartOutlined,
  SafetyOutlined,
  ShoppingCartOutlined,
  TrophyOutlined,
  CalendarOutlined,
  CloudUploadOutlined,
  CompassOutlined,
  ContainerOutlined,
  SafetyCertificateOutlined,
  ToolOutlined,
  DoubleLeftOutlined,
  DoubleRightOutlined,
  FileProtectOutlined,
  FileTextOutlined,
  LogoutOutlined,
  RadarChartOutlined,
  SolutionOutlined,
  TeamOutlined,
  UsergroupAddOutlined,
  WalletOutlined,
} from '@ant-design/icons'
import { useQueryClient } from '@tanstack/react-query'
import { Alert, App as AntApp, Avatar, Button, Layout, Menu, Spin, Tooltip } from 'antd'
import { Suspense, useState } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'

import { can, postJson, type User } from '../api'
import { forgetAll, useOutbox } from '../offline'
import { APP_NAME, APP_TAGLINE } from '../brand'
import Assistant from './Assistant'
import { ROLE_LABEL } from './Tags'
import { ModeButton } from './ui'

const WIDE = 248
const NARROW = 72

/** The page frame: a navy menu down the left, the page on the right. */
export default function Shell({ me }: { me: User }) {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [narrow, setNarrow] = useState(() => {
    try {
      return localStorage.getItem('maris-menu') === 'narrow'
    } catch {
      return false
    }
  })

  const [assistantOpen, setAssistantOpen] = useState(false)
  const { message } = AntApp.useApp()
  const outbox = useOutbox((sent) => {
    message.success(`${sent} report${sent === 1 ? '' : 's'} saved offline now sent`)
    queryClient.invalidateQueries({ predicate: (q) => q.queryKey[0] !== 'me' })
  })
  const waiting = outbox.items.filter((q) => !q.error).length
  const refused = outbox.items.length - waiting

  const toggle = () => {
    setNarrow((n) => {
      try {
        localStorage.setItem('maris-menu', n ? 'wide' : 'narrow')
      } catch {
        // not remembered in a private window
      }
      return !n
    })
  }

  const group = (label: string, children: { key: string; label: string; icon: React.ReactNode }[]) => ({ type: 'group' as const, label, children })
  const items = [
    group('Overview', [
      { key: '/', label: 'Control tower', icon: <RadarChartOutlined /> },
      { key: '/readiness', label: 'Hire readiness', icon: <SafetyCertificateOutlined /> },
      { key: '/planner', label: 'Planner', icon: <CalendarOutlined /> },
    ]),
    group('Fleet', [
      { key: '/vessels', label: 'Vessels', icon: <ContainerOutlined /> },
      { key: '/certificates', label: 'Certificates', icon: <FileProtectOutlined /> },
      { key: '/maintenance', label: 'Maintenance', icon: <ToolOutlined /> },
      { key: '/crew', label: 'Crew', icon: <UsergroupAddOutlined /> },
      { key: '/drydock', label: 'Dry dock', icon: <BuildOutlined /> },
      { key: '/insurance', label: 'Insurance', icon: <SafetyOutlined /> },
    ]),
    group('Operations', [
      { key: '/reports', label: 'Daily reports', icon: <FileTextOutlined /> },
      { key: '/off-hire', label: 'Off hire and claims', icon: <FieldTimeOutlined /> },
      { key: '/port-calls', label: 'Port calls', icon: <EnvironmentOutlined /> },
      { key: '/supply', label: 'Supply', icon: <ShoppingCartOutlined /> },
    ]),
    group('Commercial', [
      { key: '/tenders', label: 'Tenders', icon: <TrophyOutlined /> },
      { key: '/contracts', label: 'Contracts', icon: <SolutionOutlined /> },
      { key: '/invoices', label: 'Hire invoices', icon: <WalletOutlined /> },
      ...(can.manage(me) ? [{ key: '/finance', label: 'Finance', icon: <LineChartOutlined /> }] : []),
    ]),
    ...(can.readAudit(me)
      ? [
          group('Admin', [
            { key: '/audit', label: 'Audit log', icon: <AuditOutlined /> },
            ...(can.manageUsers(me) ? [{ key: '/users', label: 'Users', icon: <TeamOutlined /> }] : []),
          ]),
        ]
      : []),
  ]
  const selected = '/' + (pathname.split('/')[1] ?? '')

  const signOut = async () => {
    await postJson('/auth/logout').catch(() => undefined)
    forgetAll()
    queryClient.removeQueries({ predicate: (q) => q.queryKey[0] !== 'me' })
    queryClient.setQueryData(['me'], null)
    navigate('/')
  }

  return (
    <Layout hasSider style={{ minHeight: '100vh', background: 'var(--page)' }}>
      <Layout.Sider className="side" width={WIDE} collapsedWidth={NARROW} collapsed={narrow} trigger={null}>
        <div className="side-inner">
          <button className="side-brand" onClick={() => navigate('/')} aria-label={`${APP_NAME} home`}>
            <CompassOutlined className="side-logo" />
            {!narrow && (
              <span>
                <b>{APP_NAME}</b>
                <small>{APP_TAGLINE}</small>
              </span>
            )}
          </button>

          {/* Groups show their headings only when the menu is wide. */}
          <Menu
            theme="dark"
            mode="inline"
            selectedKeys={[selected]}
            items={narrow ? items.flatMap((g) => g.children) : items}
            onClick={({ key }) => navigate(key)}
            className="side-menu"
          />

          <div className="side-foot">
            {!narrow && (
              <div className="side-user">
                <Avatar style={{ background: 'rgba(255,255,255,0.18)', flex: 'none' }}>{me.name[0]}</Avatar>
                <span>
                  {me.name}
                  <small>{ROLE_LABEL[me.role]}</small>
                </span>
              </div>
            )}
            <div className={narrow ? 'side-tools stacked' : 'side-tools'}>
              <ModeButton light />
              <Tooltip title="Sign out" placement="right">
                <Button type="text" shape="circle" icon={<LogoutOutlined />} aria-label="Sign out" onClick={signOut} style={{ color: '#fff' }} />
              </Tooltip>
              <Tooltip title={narrow ? 'Widen the menu' : 'Narrow the menu'} placement="right">
                <Button type="text" shape="circle" icon={narrow ? <DoubleRightOutlined /> : <DoubleLeftOutlined />} aria-label={narrow ? 'Widen the menu' : 'Narrow the menu'} onClick={toggle} style={{ color: '#fff' }} />
              </Tooltip>
            </div>
          </div>
        </div>
      </Layout.Sider>
      <Layout.Content className="main" key={pathname}>
        {(!outbox.online || outbox.items.length > 0) && (
          <Alert
            style={{ marginBottom: 16 }}
            type={refused ? 'error' : outbox.online ? 'info' : 'warning'}
            showIcon
            icon={<CloudUploadOutlined />}
            message={
              !outbox.online
                ? `No connection. Daily reports you file are kept on this device${waiting ? ` (${waiting} waiting)` : ''} and sent when the link is back.`
                : refused
                  ? `${refused} report${refused === 1 ? '' : 's'} saved offline could not be sent; see Daily reports.`
                  : `${waiting} report${waiting === 1 ? '' : 's'} saved offline, sending…`
            }
          />
        )}
        {/* Pages load on first visit; show a spinner meanwhile. */}
        <Suspense fallback={<Spin style={{ display: 'block', margin: '64px auto' }} />}>
          <Outlet />
        </Suspense>
      </Layout.Content>
      {/* Kept outside the page, so the conversation survives moving between pages. */}
      <Assistant open={assistantOpen} onOpen={() => setAssistantOpen(true)} onClose={() => setAssistantOpen(false)} />
    </Layout>
  )
}
