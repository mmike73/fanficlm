import { useState, useRef, useEffect } from 'react'
import './index.css'

const API = 'http://127.0.0.1:8000/api/v1'

const THEME_LABELS = {
  love:    'Love',
  sadness: 'Sadness',
  anime:   'Anime',
  history: 'History',
  war:     'War',
  cozy:    'Cozy',
  royal:   'Royal',
  mafia:   'Mafia',
}

// One-character symbol per theme. Keep it to a single glyph so the
// existing avatar/logo sizing still works without tweaks.
const THEME_SYMBOLS = {
  default: '✦',
  love:    '♥',
  sadness: '☂',
  anime:   '✿',
  history: '⌛',
  war:     '⚔',
  cozy:    '☕',
  royal:   '♛',
  mafia:   '♠',
}

// Max characters of conversation history sent to the theme detector.
// Embedding models cap at thousands of tokens but the thematic signal
// stabilises well before that — keep the tail to bias toward recency.
const THEME_TEXT_LIMIT = 2000

function Avatar({ role, symbol }) {
  return (
    <div className={`avatar ${role}`}>
      {role === 'assistant' ? symbol : 'U'}
    </div>
  )
}

export default function App() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [theme, setTheme] = useState('default')
  const bottomRef = useRef(null)
  const textareaRef = useRef(null)

  const symbol = THEME_SYMBOLS[theme] ?? THEME_SYMBOLS.default

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
  }, [theme])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  const adjustTextarea = () => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = el.scrollHeight + 'px'
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  // Theming runs on the full user-side conversation, not just the
  // latest message. That keeps the theme stable for follow-ups
  // ("make it more dramatic") instead of flipping every turn.
  const buildThemeText = (history) =>
    history
      .filter(m => m.role === 'user')
      .map(m => m.content)
      .join('\n')
      .slice(-THEME_TEXT_LIMIT)

  // Fire-and-forget. We don't block the chat reply on it — the UI
  // just re-skins itself once the classifier returns.
  const detectTheme = async (text) => {
    if (!text.trim()) return
    try {
      const res = await fetch(`${API}/theme`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: text }),
      })
      if (!res.ok) return
      const data = await res.json()
      if (data?.theme) setTheme(data.theme)
    } catch {
      // Theme detection is non-critical — silently ignore failures.
    }
  }

  const submit = async () => {
    const text = input.trim()
    if (!text || loading) return

    const userMessage = { role: 'user', content: text }
    const updatedHistory = [...messages, userMessage]

    setMessages(updatedHistory)
    setInput('')
    setTimeout(adjustTextarea, 0)
    setLoading(true)

    // Classify the full conversation in parallel with chat generation.
    detectTheme(buildThemeText(updatedHistory))

    // Only valid chat roles get sent to the model. Error messages
    // are UI-only — sending them would 400 because LM Studio rejects
    // unknown roles, and that one bad request would poison every
    // future turn.
    const apiMessages = updatedHistory.filter(
      m => m.role === 'user' || m.role === 'assistant'
    )

    try {
      const res = await fetch(`${API}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: apiMessages }),
      })
      if (!res.ok) throw new Error(`Server error: ${res.status}`)
      const data = await res.json()
      setMessages(prev => [...prev, { role: 'assistant', content: data.reply }])
    } catch (err) {
      setMessages(prev => [...prev, { role: 'error', content: err.message }])
    } finally {
      setLoading(false)
      textareaRef.current?.focus()
    }
  }

  const isEmpty = messages.length === 0 && !loading

  return (
    <>
      {theme !== 'default' && (
        <div className="theme-badge">
          <span className="theme-dot" />
          {THEME_LABELS[theme] ?? theme}
        </div>
      )}

      {isEmpty ? (
        <div className="empty-state">
          <div className="empty-logo">{symbol}</div>
          <h1>How can I help you?</h1>
          <p>Start a conversation below</p>
        </div>
      ) : (
        <div className="messages">
          {messages.map((msg, i) => (
            <div key={i} className={`message ${msg.role}`}>
              {msg.role !== 'user' && (
                <div className="message-header">
                  <Avatar
                    role={msg.role === 'error' ? 'assistant' : msg.role}
                    symbol={symbol}
                  />
                  <span>{msg.role === 'error' ? 'Error' : 'Assistant'}</span>
                </div>
              )}
              <div className="bubble">{msg.content}</div>
            </div>
          ))}
          {loading && (
            <div className="message assistant">
              <div className="message-header">
                <Avatar role="assistant" symbol={symbol} />
                <span>Assistant</span>
              </div>
              <div className="typing"><span /><span /><span /></div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      )}

      <div className="input-area">
        <div className="input-box">
          <textarea
            ref={textareaRef}
            rows={1}
            placeholder="Message..."
            value={input}
            onChange={e => { setInput(e.target.value); adjustTextarea() }}
            onKeyDown={handleKeyDown}
          />
          <button className="send-btn" onClick={submit} disabled={!input.trim() || loading}>
            <svg viewBox="0 0 16 16" fill="none">
              <path d="M8 13V3M3 8l5-5 5 5" stroke="white" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </button>
        </div>
        <p className="hint">Shift + Enter for new line</p>
      </div>
    </>
  )
}