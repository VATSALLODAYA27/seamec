import { CloseOutlined, CompassOutlined, SendOutlined } from '@ant-design/icons'
import { useMutation } from '@tanstack/react-query'
import { Button, Input, Tooltip } from 'antd'
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { postJson } from '../api'
import { APP_NAME } from '../brand'

interface Reply {
  answer: string
  links: { label: string; to: string }[]
  suggestions: string[]
}

type Line = { from: 'me'; text: string } | ({ from: 'bot' } & Reply)

const WELCOME: Line = {
  from: 'bot',
  answer: `Hi! Ask me about ${APP_NAME}'s data, or where to find something.`,
  links: [],
  suggestions: ['Which certificates are expired?', 'Where is SEAMEC Princess?', 'How much revenue this month?', 'How do I file a daily report?'],
}

/**
 * Closed: a small round symbol in the corner. Open: a compact tab on the right edge, over the corner of the page
 * (it does not push the page aside). The conversation is kept while you move between pages.
 */
export default function Assistant({ open, onOpen, onClose }: { open: boolean; onOpen: () => void; onClose: () => void }) {
  const navigate = useNavigate()
  const [lines, setLines] = useState<Line[]>([WELCOME])
  const [draft, setDraft] = useState('')
  const end = useRef<HTMLDivElement>(null)

  const ask = useMutation({
    mutationFn: (question: string) => postJson<Reply>('/assistant', { question }),
    onSuccess: (reply) => setLines((l) => [...l, { from: 'bot', ...reply }]),
    onError: (e) => setLines((l) => [...l, { from: 'bot', answer: `Sorry, I could not answer: ${e.message}`, links: [], suggestions: [] }]),
  })

  const send = (text: string) => {
    const question = text.trim()
    if (!question || ask.isPending) return
    setLines((l) => [...l, { from: 'me', text: question }])
    setDraft('')
    ask.mutate(question)
  }

  // Braces matter: newer browsers return a promise from scrollIntoView, and React must not get it back as a cleanup.
  useEffect(() => {
    end.current?.scrollIntoView({ block: 'end' })
  }, [lines, ask.isPending, open])

  if (!open) {
    return (
      <Tooltip title={`Ask the ${APP_NAME} assistant`} placement="left">
        <button className="assist-symbol" onClick={onOpen} aria-label={`Open the ${APP_NAME} assistant`}>
          <CompassOutlined />
        </button>
      </Tooltip>
    )
  }

  const last = lines[lines.length - 1]
  return (
    <aside className="assist-tab" aria-label={`${APP_NAME} assistant`}>
      <header>
        <CompassOutlined />
        <b>{APP_NAME} assistant</b>
        <Button type="text" size="small" icon={<CloseOutlined />} aria-label="Close the assistant" onClick={onClose} style={{ color: '#fff' }} />
      </header>

      <div className="assist-log" aria-live="polite">
        {lines.map((line, i) =>
          line.from === 'me' ? (
            <p key={i} className="bubble mine">
              {line.text}
            </p>
          ) : (
            <div key={i} className="bubble">
              <p>{line.answer}</p>
              {line.links.map((link) => (
                <Button key={link.to} size="small" type="link" onClick={() => navigate(link.to)} style={{ padding: 0, marginTop: 4, marginRight: 10, height: 'auto' }}>
                  {link.label} →
                </Button>
              ))}
            </div>
          ),
        )}
        {ask.isPending && <p className="bubble muted">Looking it up…</p>}
        <div ref={end} />
      </div>

      {last.from === 'bot' && last.suggestions.length > 0 && !ask.isPending && (
        <div className="assist-chips">
          {last.suggestions.map((s) => (
            <button key={s} onClick={() => send(s)}>
              {s}
            </button>
          ))}
        </div>
      )}

      <footer>
        <Input
          autoFocus
          value={draft}
          maxLength={500}
          size="small"
          placeholder="Ask about MARIS…"
          aria-label="Your question"
          onChange={(e) => setDraft(e.target.value)}
          onPressEnter={() => send(draft)}
        />
        <Button type="primary" size="small" icon={<SendOutlined />} aria-label="Send" disabled={!draft.trim()} loading={ask.isPending} onClick={() => send(draft)} />
      </footer>
    </aside>
  )
}
