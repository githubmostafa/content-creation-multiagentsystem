import React, { useState } from 'react'
import ContentForm from './components/ContentForm'
import ContentDisplay from './components/ContentDisplay'
import ProgressIndicator from './components/ProgressIndicator'
import TextAnalyzer from './components/TextAnalyzer'
import './styles/App.css'

function App() {
  const [activeTab, setActiveTab] = useState('create')
  const [isGenerating, setIsGenerating] = useState(false)
  const [progress, setProgress] = useState([])
  const [contentPieces, setContentPieces] = useState({})
  const [error, setError] = useState(null)
  const [lastFormData, setLastFormData] = useState(null)

  // Chat state
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loadingChat, setLoadingChat] = useState(false)

  // =========================
  // CREATE CONTENT
  // =========================
  const handleContentGeneration = (formData) => {
    setLastFormData(formData)
    setIsGenerating(true)
    setProgress([])
    setContentPieces({})
    setError(null)

    fetch('/api/create-content', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        topic: formData.topic,
        target_audience: formData.targetAudience,
        tone: formData.tone,
        keywords: formData.keywords,
      }),
    })
      .then(response => {
        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        const readStream = () => {
          reader.read().then(({ done, value }) => {
            if (done) {
              setIsGenerating(false)
              return
            }

            buffer += decoder.decode(value, { stream: true })
            const lines = buffer.split('\n')
            buffer = lines.pop()

            lines.forEach(line => {
              if (line.startsWith('data: ')) {
                try {
                  const data = JSON.parse(line.substring(6))

                  if (data.type === 'status') {
                    setProgress(prev => [...prev, { type: 'info', message: data.message }])
                  }

                  if (data.type === 'content_piece') {
                    setContentPieces(prev => ({
                      ...prev,
                      [data.channel]: (prev[data.channel] || '') + data.content
                    }))
                  }

                  if (data.type === 'error') {
                    setError({ message: data.message, retryable: data.retryable })
                    setIsGenerating(false)
                  }

                } catch (e) {}
              }
            })

            readStream()
          })
        }

        readStream()
      })
      .catch(() => {
        setError({ message: 'Backend error', retryable: true })
        setIsGenerating(false)
      })
  }

  // =========================
  // CHAT STREAMING (FIXED)
  // =========================
  const handleSendMessage = async () => {
    if (!input.trim()) return

    const userMessage = input

    setMessages(prev => [
      ...prev,
      { role: 'user', text: userMessage },
      { role: 'bot', text: '' }
    ])

    setInput('')
    setLoadingChat(true)

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ message: userMessage })
      })

      const reader = res.body.getReader()
      const decoder = new TextDecoder()

      let botText = ''

      while (true) {
        const { value, done } = await reader.read()
        if (done) break

        const chunk = decoder.decode(value, { stream: true })
        const lines = chunk.split('\n')

        for (let line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.replace('data: ', ''))

              if (data.type === 'chunk') {
                botText += data.content

                setMessages(prev => {
                  const updated = [...prev]
                  updated[updated.length - 1].text = botText
                  return updated
                })
              }

              if (data.type === 'done') {
                setLoadingChat(false)
                return
              }

              if (data.type === 'error') {
                setMessages(prev => [
                  ...prev,
                  { role: 'bot', text: 'Error from server' }
                ])
                setLoadingChat(false)
                return
              }

            } catch (e) {}
          }
        }
      }

    } catch (err) {
      setMessages(prev => [
        ...prev,
        { role: 'bot', text: 'Error connecting to server' }
      ])
      setLoadingChat(false)
    }
  }

  const hasContent = Object.keys(contentPieces).length > 0

  return (
    <div className="app">

      <header className="app-header">
        <h1>Content Creation Studio</h1>
        <p>AI-Powered Multi-Agent Content Generation</p>
      </header>

      <main className="app-main">

        {/* Tabs */}
        <div className="main-tabs">
          <button onClick={() => setActiveTab('create')}>Create Content</button>
          <button onClick={() => setActiveTab('analyze')}>Analyze Text</button>
          <button onClick={() => setActiveTab('assistant')}>AI Assistant</button>
        </div>

        <div className="content-container">

          {activeTab === 'create' && (
            <ContentForm
              onSubmit={handleContentGeneration}
              isGenerating={isGenerating}
            />
          )}

          {activeTab === 'analyze' && <TextAnalyzer />}

          {activeTab === 'assistant' && (
            <div className="assistant-container">

              <h2>💬 AI Assistant</h2>

              <div className="chat-box">
                {messages.map((msg, i) => (
                  <div key={i} className={`message ${msg.role}`}>
                    {msg.text}
                  </div>
                ))}
              </div>

              <div className="chat-input">
                <input
                  value={input}
                  placeholder="Type your message..."
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') handleSendMessage()
                  }}
                />

                <button onClick={handleSendMessage} disabled={loadingChat}>
                  {loadingChat ? '...' : 'Send'}
                </button>
              </div>

            </div>
          )}

          {(isGenerating || progress.length > 0) && (
            <ProgressIndicator
              progress={progress}
              isGenerating={isGenerating}
            />
          )}

          {error && (
            <div className="error-banner">
              <p>{error.message}</p>
            </div>
          )}

          {hasContent && (
            <ContentDisplay
              contentPieces={contentPieces}
              isGenerating={isGenerating}
            />
          )}

        </div>
      </main>

      <footer className="app-footer">
        <p>Powered by Google ADK & Gemini AI</p>
      </footer>
    </div>
  )
}

export default App