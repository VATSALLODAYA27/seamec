// Offline support for vessels on an intermittent VSAT link.
// - Reports filed with no connection go to an outbox on this device and are sent when the link returns.
// - The last good copy of a few lists (who is signed in, vessels, equipment) is kept, so the report form still
//   works offline. The server checks everything again when the outbox is sent.
import { useCallback, useEffect, useState } from 'react'

import { ApiError, postJson } from './api'

const OUTBOX = 'maris-outbox'
const CACHE = 'maris-cache:'

export interface Queued {
  id: string
  savedAt: string
  body: Record<string, unknown>
  /** Set when the server refused it; it then stays here until corrected or removed. */
  error?: string
}

function read<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : fallback
  } catch {
    return fallback
  }
}

function write(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // storage full or blocked: nothing more can be done here
  }
}

/** A network failure, as opposed to the server answering with an error. */
export const isOffline = (error: unknown) => !(error instanceof ApiError) || !navigator.onLine

/** Fetch, keep the answer, and fall back to the kept answer when there is no connection. */
export async function remembered<T>(key: string, fetcher: () => Promise<T>): Promise<T> {
  try {
    const value = await fetcher()
    write(CACHE + key, value)
    return value
  } catch (error) {
    const kept = read<T | undefined>(CACHE + key, undefined)
    if (isOffline(error) && kept !== undefined) return kept
    throw error
  }
}

export const forget = (key: string) => {
  try {
    localStorage.removeItem(CACHE + key)
  } catch {
    // ignore
  }
}

/** Forget everything kept for offline use (on sign-out, so the next person on a shared ship computer sees nothing). */
export function forgetAll() {
  try {
    Object.keys(localStorage)
      .filter((k) => k.startsWith(CACHE))
      .forEach((k) => localStorage.removeItem(k))
  } catch {
    // ignore
  }
}

const listeners = new Set<() => void>()
const notify = () => listeners.forEach((l) => l())

/** A reference for one report, made on this device, so a resend is recognised by the server. */
export const newRef = () => (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`)

export function queueReport(body: Record<string, unknown>) {
  const box = read<Queued[]>(OUTBOX, [])
  const id = String(body.client_ref ?? newRef())
  box.push({ id, savedAt: new Date().toISOString(), body: { ...body, client_ref: id } })
  write(OUTBOX, box)
  notify()
}

let sending = false

/** Send everything waiting. Refused items stay with the server's reason; a network failure stops the run. */
export async function flushOutbox(): Promise<{ sent: number; failed: number }> {
  if (sending || !navigator.onLine) return { sent: 0, failed: 0 }
  sending = true
  let sent = 0
  let failed = 0
  try {
    for (const item of read<Queued[]>(OUTBOX, [])) {
      // Skip what was refused, and what another tab or an earlier run has sent meanwhile.
      if (item.error || !read<Queued[]>(OUTBOX, []).some((q) => q.id === item.id)) continue
      try {
        await postJson('/reports', item.body)
        write(OUTBOX, read<Queued[]>(OUTBOX, []).filter((q) => q.id !== item.id))
        sent++
      } catch (error) {
        if (isOffline(error)) break
        write(OUTBOX, read<Queued[]>(OUTBOX, []).map((q) => (q.id === item.id ? { ...q, error: (error as Error).message } : q)))
        failed++
      }
    }
  } finally {
    sending = false
    notify()
  }
  return { sent, failed }
}

export function removeQueued(id: string) {
  write(OUTBOX, read<Queued[]>(OUTBOX, []).filter((q) => q.id !== id))
  notify()
}

/** The outbox, kept up to date, plus whether the browser thinks it is online. Sends automatically on reconnect. */
export function useOutbox(onSent?: (sent: number) => void) {
  const [items, setItems] = useState<Queued[]>(() => read<Queued[]>(OUTBOX, []))
  const [online, setOnline] = useState(navigator.onLine)
  const send = useCallback(async () => {
    const { sent } = await flushOutbox()
    if (sent) onSent?.(sent)
  }, [onSent])

  useEffect(() => {
    const refresh = () => setItems(read<Queued[]>(OUTBOX, []))
    const up = () => {
      setOnline(true)
      void send()
    }
    const down = () => setOnline(false)
    listeners.add(refresh)
    window.addEventListener('online', up)
    window.addEventListener('offline', down)
    void send()
    return () => {
      listeners.delete(refresh)
      window.removeEventListener('online', up)
      window.removeEventListener('offline', down)
    }
  }, [send])

  return { items, online, send }
}
