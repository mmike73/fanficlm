import { useState, useRef, useEffect } from 'react'
import './index.css'

const API = 'http://127.0.0.1:8000/api/v1'

const THEME_LABELS = {
  love:      'Love',
  sadness:   'Sadness',
  anime:     'Anime',
  history:   'History',
  war:       'War',
  cozy:      'Cozy',
  royal:     'Royal',
  mafia:     'Mafia',
  horror:    'Horror',
  mystery:   'Mystery',
  adventure: 'Adventure',
  comedy:    'Comedy',
}

const THEME_SYMBOLS = {
  default:   '✦',
  love:      '♥',
  sadness:   '☂',
  anime:     '✿',
  history:   '⌛',
  war:       '⚔',
  cozy:      '☕',
  royal:     '♛',
  mafia:     '♠',
  horror:    '☾',
  mystery:   '☉',
  adventure: '✦',
  comedy:    '☺',
}

const THEME_SONGS = {
  default:   null, 
  love:      '/music/love.mp3',
  sadness:   '/music/sadness.mp3',
  anime:     '/music/anime.mp3',
  history:   '/music/history.mp3',
  war:       '/music/war.mp3',
  cozy:      '/music/cozy.mp3',
  royal:     '/music/royal.mp3',
  mafia:     '/music/mafia.mp3',
  horror:    '/music/horror.mp3',
  mystery:   '/music/mystery.mp3',
  adventure: '/music/adventure.mp3',
  comedy:    '/music/comedy.mp3',
}

const THEME_MOTIFS = {
  love:
    'M50 78C50 78 18 58 18 36C18 24 27 16 37 16C44 16 49 20 50 26C51 20 56 16 63 16C73 16 82 24 82 36C82 58 50 78 50 78Z',
  sadness:
    'M50 14C50 14 26 44 26 60C26 74 37 84 50 84C63 84 74 74 74 60C74 44 50 14 50 14Z',
  anime:
    'M50 12L60 40L90 40L66 58L75 88L50 70L25 88L34 58L10 40L40 40Z',
  history:
    'M30 16H70L42 50L70 84H30L58 50Z M30 16H70 M30 84H70',
  war:
    'M22 78L62 38 M58 30L70 18L82 30L70 42 M28 72L18 82 M40 60L72 28',
  cozy:
    'M28 44H64V64C64 73 57 80 46 80C35 80 28 73 28 64Z M64 50H74C80 50 80 62 74 62H64 M34 24V34 M46 20V32 M58 24V34',
  royal:
    'M22 70H78L82 36L62 52L50 28L38 52L18 36Z M22 70H78V78H22Z',
  mafia:
    'M50 18C40 30 24 30 24 30C24 56 34 76 50 84C66 76 76 56 76 30C76 30 60 30 50 18Z',
  horror:
    'M62 16C46 18 34 32 34 50C34 68 46 82 62 84C50 80 42 66 42 50C42 34 50 20 62 16Z',
  mystery:
    'M44 44m-26 0a26 26 0 1 0 52 0a26 26 0 1 0 -52 0 M62 62L86 86',
  adventure:
    'M14 82L40 30L54 56L66 36L86 82Z M40 30L48 46',
  comedy: 'FACE',
}

const COMEDY_FACE = {
  circle: 'M50 14A36 36 0 1 0 50 86A36 36 0 1 0 50 14Z',
  eyes:
    'M38 42A3.5 3.5 0 1 0 45 42A3.5 3.5 0 1 0 38 42Z ' +
    'M55 42A3.5 3.5 0 1 0 62 42A3.5 3.5 0 1 0 55 42Z',
  smile: 'M35 58C42 70 58 70 65 58',
}

const MOTIF_STROKE = {
  history: true, war: true, adventure: true, mystery: true,
}

const PARTICLE_CONFIG = {
  love:      { glyph: '♥', count: 16, direction: 'up',    sizeMin: 10, sizeMax: 22 },
  sadness:   { glyph: '|', count: 28, direction: 'down',  sizeMin: 8,  sizeMax: 16 },
  anime:     { glyph: '✦', count: 20, direction: 'drift', sizeMin: 8,  sizeMax: 18 },
  history:   { glyph: '✶', count: 14, direction: 'drift', sizeMin: 8,  sizeMax: 16 },
  war:       { glyph: '·', count: 22, direction: 'up',    sizeMin: 10, sizeMax: 24 },
  cozy:      { glyph: '✺', count: 16, direction: 'drift', sizeMin: 8,  sizeMax: 18 },
  royal:     { glyph: '✦', count: 16, direction: 'drift', sizeMin: 9,  sizeMax: 18 },
  mafia:     { glyph: '·', count: 18, direction: 'up',    sizeMin: 10, sizeMax: 20 },
  horror:    { glyph: '✕', count: 18, direction: 'drift', sizeMin: 9,  sizeMax: 20 },
  mystery:   { glyph: '?', count: 14, direction: 'drift', sizeMin: 10, sizeMax: 20 },
  adventure: { glyph: '▲', count: 16, direction: 'up',    sizeMin: 8,  sizeMax: 18 },
  comedy:    { glyph: '☺', count: 16, direction: 'up',    sizeMin: 10, sizeMax: 22 },
}

function Avatar({ role, symbol }) {
  return (
    <div className={`avatar ${role}`}>
      {role === 'assistant' ? symbol : 'U'}
    </div>
  )
}

function ThemeMotif({ theme }) {
  if (theme === 'comedy') {
    return (
      <svg className="theme-motif" viewBox="0 0 100 100" aria-hidden="true">
        <path d={COMEDY_FACE.circle} fill="none" stroke="var(--accent-1)" strokeWidth={6} />
        <path d={COMEDY_FACE.eyes} fill="var(--accent-1)" />
        <path d={COMEDY_FACE.smile} fill="none" stroke="var(--accent-1)"
              strokeWidth={6} strokeLinecap="round" />
      </svg>
    )
  }
  const path = THEME_MOTIFS[theme]
  if (!path) return null
  const stroked = MOTIF_STROKE[theme]
  return (
    <svg className="theme-motif" viewBox="0 0 100 100" aria-hidden="true">
      <path
        d={path}
        fill={stroked ? 'none' : 'var(--accent-1)'}
        stroke={stroked ? 'var(--accent-1)' : 'none'}
        strokeWidth={stroked ? 6 : 0}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function ParticleField({ theme }) {
  const cfg = PARTICLE_CONFIG[theme]
  if (!cfg) return null

  const particles = Array.from({ length: cfg.count }, (_, i) => {
    const size = cfg.sizeMin + Math.random() * (cfg.sizeMax - cfg.sizeMin)
    const duration = 9 + Math.random() * 12         
    const delay = -Math.random() * duration          
    const left = Math.random() * 100                 
    const drift = (Math.random() * 60 - 30).toFixed(0) 
    return (
      <span
        key={i}
        className={`particle particle-${cfg.direction}`}
        style={{
          left: `${left}%`,
          fontSize: `${size}px`,
          animationDuration: `${duration}s`,
          animationDelay: `${delay}s`,
          '--drift': `${drift}px`,
        }}
      >
        {cfg.glyph}
      </span>
    )
  })

  return <div className="particle-field" aria-hidden="true">{particles}</div>
}

export default function App() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [theme, setTheme] = useState('default')
  const [sweep, setSweep] = useState(0)  
  const bottomRef = useRef(null)
  const textareaRef = useRef(null)

  const audioRef = useRef(null)
  const symbol = THEME_SYMBOLS[theme] ?? THEME_SYMBOLS.default


  const [isMuted, setIsMuted] = useState(false)
  const isMutedRef = useRef(isMuted) 

  useEffect(() => {
    isMutedRef.current = isMuted
  }, [isMuted])

  const toggleMute = () => {
    setIsMuted(prev => {
      const nextMuted = !prev
      if (audioRef.current) {
        if (nextMuted) {
          audioRef.current.pause()
        } else {
          audioRef.current.play().catch(e => console.warn(e))
        }
      }
      return nextMuted
    })
  }

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)

    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current.currentTime = 0 
    }

    const songUrl = THEME_SONGS[theme]

    if (songUrl) {
      audioRef.current = new Audio(songUrl)
      audioRef.current.loop = true 
      audioRef.current.volume = 0.3 
      
      if (!isMutedRef.current) {
        audioRef.current.play().catch(err => {
          console.warn('Audio playback was prevented by the browser:', err)
        })
      }
    }
    
    return () => {
      if (audioRef.current) {
        audioRef.current.pause()
      }
    }
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

  const buildThemeText = (history) =>
    history
      .filter(m => m.role === 'user')
      .map(m => m.content)
      .join('\n')
      .slice(-2000)

  const applyTheme = (next) => {
    setTheme(prev => {
      if (next !== prev) setSweep(s => s + 1)
      return next
    })
  }

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
      if (data?.theme) applyTheme(data.theme)
    } catch {
      
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

    detectTheme(buildThemeText(updatedHistory))

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
      <ParticleField key={theme} theme={theme} />
      <ThemeMotif theme={theme} />

      {sweep > 0 && <div key={sweep} className="theme-sweep" />}

      {theme !== 'default' && (
        <div className="theme-badge">
          <button className="mute-btn" onClick={toggleMute} title="Toggle music">
            {isMuted ? '🔇' : '🔊'}
          </button>
          
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