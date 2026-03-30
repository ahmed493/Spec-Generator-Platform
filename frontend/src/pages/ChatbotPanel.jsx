
import { useState, useRef, useEffect } from 'react'
import { chat } from '../api'
import { User, Bot, Loader2, AlertCircle } from 'lucide-react'
import '../chatbot.css'

export default function ChatbotPanel({ repoName = null }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const messagesEndRef = useRef(null)

  // Scroll to bottom on new message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const sendMessage = async (e) => {
    e.preventDefault()
    if (!input.trim()) return
    setLoading(true)
    setError(null)
    const userMsg = { role: 'user', text: input }
    setMessages((msgs) => [...msgs, userMsg])
    try {
      const res = await chat(input, repoName)
      const botMsg = { role: 'bot', text: res.data.response }
      // If backend returns history, use it for full sync
      if (res.data.history) {
        const hist = res.data.history.flatMap(turn => [
          { role: 'user', text: turn.question },
          { role: 'bot', text: turn.answer }
        ])
        setMessages(hist)
      } else {
        setMessages((msgs) => [...msgs, botMsg])
      }
      setInput('')
    } catch (err) {
      setError(err.response?.data?.detail || 'Erreur lors de la requête.')
    }
    setLoading(false)
  }

  return (
    <div className="chatbot-panel">
      <div className="chat-history">
        {messages.length === 0 && (
          <div className="chat-empty">Commencez la conversation avec le chatbot !</div>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`chat-msg ${msg.role}`}> 
            <div className="chat-avatar">
              {msg.role === 'user' ? <User size={20} /> : <Bot size={20} />}
            </div>
            <div className="chat-bubble">{msg.text}</div>
          </div>
        ))}
        {loading && (
          <div className="chat-msg bot">
            <div className="chat-avatar"><Bot size={20} /></div>
            <div className="chat-bubble loading"><Loader2 className="spinner" size={16} /> Génération...</div>
          </div>
        )}
        {error && (
          <div className="chat-msg error">
            <div className="chat-avatar"><AlertCircle size={20} color="#ef4444" /></div>
            <div className="chat-bubble error">{error}</div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>
      <form className="chat-input-row" onSubmit={sendMessage}>
        <input
          type="text"
          placeholder="Posez une question sur la spec..."
          value={input}
          onChange={e => setInput(e.target.value)}
          disabled={loading}
        />
        <button className="btn btn-primary" type="submit" disabled={loading || !input.trim()}>
          Envoyer
        </button>
      </form>
    </div>
  )
}
