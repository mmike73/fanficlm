import { useState, useRef, useEffect } from 'react'
import './index.css'

const API = 'http://127.0.0.1:8000/api/v1'

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
  const bottomRef = useRef(null)
  const textareaRef = useRef(null)

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

  const submit = async () => {
    const text = input.trim()
    if (!text || loading) return

    const userMessage = { role: 'user', content: text }
    const updatedHistory = [...messages, userMessage]

    setMessages(updatedHistory)
    setInput('')
    setTimeout(adjustTextarea, 0)
    setLoading(true)

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