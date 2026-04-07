import { useState, useRef, useEffect } from 'react'
import { MessageSquare, X, Send, Loader2, User, Bot, Sparkles } from 'lucide-react'
import { useProject, STEPS } from '../context/ProjectContext'
import { projectChat } from '../api'

export default function ChatPanel() {
  const { state, dispatch } = useProject()
  const { chatOpen, chatHistory, project, pipelineStep, placeholders, confirmedValues } = state
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const endRef = useRef(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [chatHistory])

  if (!project) return null

  const toggle = () => dispatch({ type: 'TOGGLE_CHAT' })

  const send = async (e) => {
    e?.preventDefault()
    if (!input.trim() || loading) return
    const question = input.trim()
    setInput('')
    dispatch({ type: 'ADD_CHAT_MESSAGE', payload: { role: 'user', text: question } })
    setLoading(true)
    try {
      const res = await projectChat(
        project.id,
        question,
        STEPS[pipelineStep] || '',
        placeholders,
        confirmedValues,
      )
      dispatch({
        type: 'ADD_CHAT_MESSAGE',
        payload: { role: 'bot', text: res.data.answer, mode: res.data.mode },
      })
    } catch {
      dispatch({
        type: 'ADD_CHAT_MESSAGE',
        payload: { role: 'bot', text: 'Sorry, an error occurred.', mode: 'general' },
      })
    }
    setLoading(false)
  }

  // Proactive suggestions based on pipeline step
  const suggestions = []
  if (pipelineStep === 1) {
    const lowCount = (state.extractionResults || []).filter(r => r.confidence === 'low').length
    if (lowCount > 0) suggestions.push(`You have ${lowCount} uncertain value${lowCount > 1 ? 's' : ''} — want me to suggest better ones?`)
  }
  if (pipelineStep === 2) {
    const gapCount = Object.values(confirmedValues).filter(v => !v || v === 'Non identifié').length
    if (gapCount > 0) suggestions.push(`There are ${gapCount} unfilled placeholder${gapCount > 1 ? 's' : ''} — shall I attempt to fill them?`)
  }

  return (
    <>
      {/* Toggle button */}
      <button className={`chat-toggle-btn ${chatOpen ? 'open' : ''}`} onClick={toggle}>
        {chatOpen ? <X size={20} /> : <MessageSquare size={20} />}
      </button>

      {/* Slide-in panel */}
      <div className={`chat-panel ${chatOpen ? 'open' : ''}`}>
        <div className="cp-header">
          <div className="cp-header-left">
            <Sparkles size={16} />
            <span>AI Assistant</span>
          </div>
          <button className="cp-close" onClick={toggle}><X size={16} /></button>
        </div>

        <div className="cp-messages">
          {chatHistory.length === 0 && (
            <div className="cp-empty">
              <Sparkles size={28} />
              <p>Ask me anything about your project, sources, or the current pipeline step.</p>
            </div>
          )}
          {chatHistory.map((msg, i) => (
            <div key={i} className={`cp-msg ${msg.role}`}>
              <div className="cp-msg-avatar">
                {msg.role === 'user' ? <User size={14} /> : <Bot size={14} />}
              </div>
              <div className="cp-msg-body">
                <div className="cp-msg-text">{msg.text}</div>
                {msg.mode && (
                  <span className={`cp-msg-tag ${msg.mode}`}>
                    {msg.mode === 'sources' ? 'from sources' : 'general'}
                  </span>
                )}
              </div>
            </div>
          ))}
          {loading && (
            <div className="cp-msg bot">
              <div className="cp-msg-avatar"><Bot size={14} /></div>
              <div className="cp-msg-body">
                <div className="cp-msg-text typing"><Loader2 size={14} className="spinner" /> Thinking…</div>
              </div>
            </div>
          )}
          <div ref={endRef} />
        </div>

        {/* Proactive suggestions */}
        {suggestions.length > 0 && (
          <div className="cp-suggestions">
            {suggestions.map((s, i) => (
              <button key={i} className="cp-suggestion-btn" onClick={() => { setInput(s) }}>
                <Sparkles size={12} /> {s}
              </button>
            ))}
          </div>
        )}

        <form className="cp-input" onSubmit={send}>
          <input
            type="text"
            placeholder="Ask about your project…"
            value={input}
            onChange={e => setInput(e.target.value)}
            disabled={loading}
          />
          <button type="submit" disabled={loading || !input.trim()}>
            <Send size={16} />
          </button>
        </form>
      </div>
    </>
  )
}
