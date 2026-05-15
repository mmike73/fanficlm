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

function Avatar({ role }) {
  return (
    <div className={`avatar ${role}`}>
      {role === 'assistant' ? '✦' : 'U'}
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

  // Apply the theme to the document root so CSS variables cascade
  // through everything (background, bubbles, accents, etc.).
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

  // Fire-and-forget theme detection. We don't block the chat reply
  // on it — the UI just re-skins itself once the classifier returns.
  const detectTheme = async (text) => {
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

    // Run theme detection in parallel with the chat call.
    detectTheme(text)

    try {
      const res = await fetch(`${API}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: updatedHistory }),
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
          <div className="empty-logo">✦</div>
          <h1>How can I help you?</h1>
          <p>Start a conversation below</p>
        </div>
      ) : (
        <div className="messages">
          {messages.map((msg, i) => (
            <div key={i} className={`message ${msg.role}`}>
              {msg.role !== 'user' && (
                <div className="message-header">
                  <Avatar role={msg.role === 'error' ? 'assistant' : msg.role} />
                  <span>{msg.role === 'error' ? 'Error' : 'Assistant'}</span>
                </div>
              )}
              <div className="bubble">{msg.content}</div>
            </div>
          ))}
          {loading && (
            <div className="message assistant">
              <div className="message-header">
                <Avatar role="assistant" />
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