// MARIS's look: one navy accent, status colours, and a light and a dark mode.
import { theme, type ThemeConfig } from 'antd'
import { createContext } from 'react'

/** The product name, in one place. */
export const APP_NAME = 'MARIS'
export const APP_TAGLINE = 'SEAMEC fleet ERP'

export const NAVY = '#3B5998'

export const STATUS = { ok: '#1E8E3E', warn: '#B86E00', bad: '#C62828', info: '#1D5FBF' } as const

export const DarkMode = createContext<{ dark: boolean; flip: () => void }>({ dark: false, flip: () => {} })

const shared: ThemeConfig['token'] = { borderRadius: 8, borderRadiusLG: 12, fontSize: 14, controlHeight: 36 }

export function themeConfig(dark: boolean): ThemeConfig {
  if (!dark) {
    return {
      algorithm: theme.defaultAlgorithm,
      token: { ...shared, colorPrimary: NAVY, colorLink: NAVY, colorSuccess: STATUS.ok, colorWarning: STATUS.warn, colorError: STATUS.bad, colorInfo: STATUS.info, colorBgLayout: '#F4F5F9', colorTextBase: '#0F172A' },
      components: { Table: { headerBg: '#EEF1F8' }, Menu: { darkItemBg: 'transparent', darkItemSelectedBg: 'rgba(255,255,255,0.18)', darkGroupTitleColor: 'rgba(255,255,255,0.55)', itemHeight: 42 } },
    }
  }
  return {
    algorithm: theme.darkAlgorithm,
    token: { ...shared, colorPrimary: '#7D93C9', colorLink: '#9DB0DE', colorSuccess: '#4CC97F', colorWarning: '#F0B340', colorError: '#FF7B72', colorInfo: '#8AB4F8', colorBgLayout: '#0B0C10', colorBgContainer: '#15171C' },
    components: { Table: { headerBg: '#1C1F26' }, Menu: { darkItemBg: 'transparent', darkItemSelectedBg: 'rgba(255,255,255,0.12)', darkGroupTitleColor: 'rgba(255,255,255,0.5)', itemHeight: 42 } },
  }
}
