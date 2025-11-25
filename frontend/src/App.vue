<script setup lang="ts">
import { ref, computed, nextTick, onMounted } from 'vue'
import axios from 'axios'

// ---------------------------------------------------------
// Types
// ---------------------------------------------------------

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  isSql?: boolean
}

interface ChatRequest {
  dialect: string
  schema_text: string
  message: string
  history: { role: string; content: string }[]
}

interface ChatResponse {
  sql: string
}

// ---------------------------------------------------------
// Reactive State
// ---------------------------------------------------------

// Schema & Dialect
const schemaText = ref('')
const dialect = ref<'PostgreSQL' | 'MySQL' | 'SQLite' | 'SQL Server'>('PostgreSQL')
const dialects = ['PostgreSQL', 'MySQL', 'SQLite', 'SQL Server'] as const

// Chat
const messages = ref<ChatMessage[]>([])
const inputText = ref('')
const isLoading = ref(false)
const chatContainerRef = ref<HTMLElement | null>(null)

// ---------------------------------------------------------
// Computed Properties
// ---------------------------------------------------------

const schemaLoaded = computed(() => schemaText.value.trim().length > 0)

const canSend = computed(() => {
  return (
    inputText.value.trim().length > 0 &&
    schemaLoaded.value &&
    !isLoading.value
  )
})

const statusText = computed(() => {
  if (schemaLoaded.value) {
    const lines = schemaText.value.trim().split('\n').length
    return `✅ Schema loaded (${lines} lines)`
  }
  return '⚠️ No schema provided yet'
})

// ---------------------------------------------------------
// Methods
// ---------------------------------------------------------

/**
 * Handle file upload for schema
 */
function handleFileUpload(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  
  if (!file) return
  
  const reader = new FileReader()
  reader.onload = (e) => {
    const content = e.target?.result as string
    if (content) {
      schemaText.value = content
    }
  }
  reader.readAsText(file)
  
  // Reset input so same file can be re-uploaded
  target.value = ''
}

/**
 * Scroll chat to bottom
 */
async function scrollToBottom() {
  await nextTick()
  if (chatContainerRef.value) {
    chatContainerRef.value.scrollTop = chatContainerRef.value.scrollHeight
  }
}

/**
 * Handle keyboard events in textarea
 */
function handleKeydown(event: KeyboardEvent) {
  // Enter without Shift sends the message
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    if (canSend.value) {
      sendMessage()
    }
  }
}

/**
 * Send message to backend
 */
async function sendMessage() {
  if (!canSend.value) return
  
  const userMessage = inputText.value.trim()
  
  // Add user message to chat
  messages.value.push({
    role: 'user',
    content: userMessage,
    isSql: false
  })
  
  // Clear input and set loading
  inputText.value = ''
  isLoading.value = true
  
  await scrollToBottom()
  
  // Build history for context (last 10 messages, excluding loading states)
  const history = messages.value
    .filter(m => m.content !== 'Generating SQL...')
    .slice(-10)
    .map(m => ({
      role: m.role,
      content: m.content
    }))
  
  // Build request
  const request: ChatRequest = {
    dialect: dialect.value,
    schema_text: schemaText.value,
    message: userMessage,
    history: history.slice(0, -1) // Exclude the message we just added
  }
  
  try {
    const response = await axios.post<ChatResponse>('/api/chat', request)
    const sql = response.data.sql
    
    // Determine if it's an error response
    const isError = sql.trim().startsWith('-- ERROR')
    
    messages.value.push({
      role: 'assistant',
      content: sql,
      isSql: !isError
    })
  } catch (error) {
    console.error('API Error:', error)
    messages.value.push({
      role: 'assistant',
      content: '-- ERROR: Failed to generate SQL. Please check your connection and try again.',
      isSql: false
    })
  } finally {
    isLoading.value = false
    await scrollToBottom()
  }
}

/**
 * Clear chat history
 */
function clearChat() {
  messages.value = []
}

// Initial welcome message
onMounted(() => {
  messages.value.push({
    role: 'assistant',
    content: 'Hello! I\'m your SQL assistant. Upload or paste your database schema on the left, then ask me questions in natural language, and I\'ll generate SQL queries for you.',
    isSql: false
  })
})
</script>

<template>
  <div class="app-container">
    <!-- Left Sidebar: Schema Input -->
    <aside class="sidebar">
      <div class="sidebar-header">
        <div class="logo">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 2C6.48 2 2 4.69 2 8v8c0 3.31 4.48 6 10 6s10-2.69 10-6V8c0-3.31-4.48-6-10-6z" stroke="currentColor" stroke-width="1.5" fill="none"/>
            <path d="M2 8c0 3.31 4.48 6 10 6s10-2.69 10-6" stroke="currentColor" stroke-width="1.5"/>
            <path d="M2 12c0 3.31 4.48 6 10 6s10-2.69 10-6" stroke="currentColor" stroke-width="1.5"/>
          </svg>
          <span>SQL Chat</span>
        </div>
      </div>

      <div class="sidebar-content">
        <div class="schema-card">
          <h3>Database Schema</h3>
          
          <!-- File Upload -->
          <div class="file-upload">
            <label class="file-upload-btn">
              <input
                type="file"
                accept=".sql,.txt"
                @change="handleFileUpload"
                hidden
              />
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
              Upload .sql or .txt
            </label>
          </div>
          
          <!-- Schema Textarea -->
          <div class="schema-textarea-wrapper">
            <textarea
              v-model="schemaText"
              class="schema-textarea"
              placeholder="Paste your CREATE TABLE statements here...

Example:
CREATE TABLE users (
  id SERIAL PRIMARY KEY,
  name VARCHAR(100),
  email VARCHAR(255) UNIQUE,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE orders (
  id SERIAL PRIMARY KEY,
  user_id INTEGER REFERENCES users(id),
  total_amount DECIMAL(10,2),
  order_date DATE
);"
              spellcheck="false"
            ></textarea>
          </div>
          
          <!-- Status -->
          <div class="schema-status" :class="{ loaded: schemaLoaded }">
            {{ statusText }}
          </div>
        </div>

        <!-- Dialect Selector -->
        <div class="dialect-card">
          <h3>SQL Dialect</h3>
          <select v-model="dialect" class="dialect-select">
            <option v-for="d in dialects" :key="d" :value="d">
              {{ d }}
            </option>
          </select>
        </div>

        <!-- Clear Chat Button -->
        <button class="clear-btn" @click="clearChat" :disabled="messages.length <= 1">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2m3 0v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6h14z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          Clear Chat
        </button>
      </div>
    </aside>

    <!-- Main Chat Area -->
    <main class="chat-main">
      <!-- Chat Header -->
      <header class="chat-header">
        <div class="chat-title">
          <h1>SQL Chat Assistant</h1>
          <p>Upload schema → Ask in natural language → Get SQL</p>
        </div>
        <div class="dialect-badge">
          {{ dialect }}
        </div>
      </header>

      <!-- Chat Messages -->
      <div class="chat-messages" ref="chatContainerRef">
        <div
          v-for="(msg, index) in messages"
          :key="index"
          class="message-wrapper"
          :class="{ 'user-message': msg.role === 'user' }"
        >
          <div class="message-label">
            {{ msg.role === 'user' ? 'You' : 'SQL Assistant' }}
          </div>
          <div
            class="message-bubble"
            :class="{
              'user-bubble': msg.role === 'user',
              'assistant-bubble': msg.role === 'assistant',
              'sql-bubble': msg.isSql
            }"
          >
            <pre v-if="msg.isSql || msg.content.startsWith('-- ERROR')">{{ msg.content }}</pre>
            <p v-else>{{ msg.content }}</p>
          </div>
        </div>

        <!-- Loading indicator -->
        <div v-if="isLoading" class="message-wrapper">
          <div class="message-label">SQL Assistant</div>
          <div class="message-bubble assistant-bubble loading-bubble">
            <div class="loading-dots">
              <span></span>
              <span></span>
              <span></span>
            </div>
            <span class="loading-text">Generating SQL...</span>
          </div>
        </div>
      </div>

      <!-- Input Area -->
      <div class="chat-input-area">
        <div class="input-container">
          <textarea
            v-model="inputText"
            @keydown="handleKeydown"
            class="message-input"
            placeholder="Ask a question about your data..."
            :disabled="isLoading"
            rows="1"
          ></textarea>
          <button
            class="send-btn"
            @click="sendMessage"
            :disabled="!canSend"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </button>
        </div>
        <div class="input-hint">
          Press <kbd>Enter</kbd> to send · <kbd>Shift+Enter</kbd> for new line · 
          Schema: <span :class="{ 'hint-success': schemaLoaded, 'hint-warning': !schemaLoaded }">
            {{ schemaLoaded ? 'loaded' : 'missing' }}
          </span>
        </div>
      </div>
    </main>
  </div>
</template>

<style scoped>
/* ---------------------------------------------------------
   Layout
--------------------------------------------------------- */
.app-container {
  display: flex;
  height: 100vh;
  background: var(--bg-primary);
}

/* ---------------------------------------------------------
   Sidebar
--------------------------------------------------------- */
.sidebar {
  width: 340px;
  min-width: 340px;
  background: var(--bg-sidebar);
  border-right: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
}

.sidebar-header {
  padding: 1.25rem 1.5rem;
  border-bottom: 1px solid var(--border-color);
}

.logo {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  color: var(--accent-primary);
  font-weight: 600;
  font-size: 1.25rem;
}

.sidebar-content {
  flex: 1;
  padding: 1.5rem;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

/* ---------------------------------------------------------
   Schema Card
--------------------------------------------------------- */
.schema-card,
.dialect-card {
  background: var(--bg-card);
  border-radius: 12px;
  padding: 1.25rem;
  border: 1px solid var(--border-color);
}

.schema-card h3,
.dialect-card h3 {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 1rem;
}

.file-upload {
  margin-bottom: 1rem;
}

.file-upload-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  background: var(--bg-hover);
  border: 2px dashed var(--border-color);
  border-radius: 8px;
  color: var(--text-secondary);
  font-size: 0.875rem;
  cursor: pointer;
  transition: all 0.2s ease;
  width: 100%;
}

.file-upload-btn:hover {
  border-color: var(--accent-primary);
  color: var(--accent-primary);
  background: var(--accent-bg);
}

.schema-textarea-wrapper {
  margin-bottom: 0.75rem;
}

.schema-textarea {
  width: 100%;
  height: 280px;
  padding: 0.875rem;
  background: var(--bg-input);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  color: var(--text-primary);
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.8rem;
  line-height: 1.5;
  resize: vertical;
  transition: border-color 0.2s ease;
}

.schema-textarea:focus {
  outline: none;
  border-color: var(--accent-primary);
}

.schema-textarea::placeholder {
  color: var(--text-muted);
}

.schema-status {
  font-size: 0.8rem;
  color: var(--text-warning);
  padding: 0.5rem 0.75rem;
  background: var(--warning-bg);
  border-radius: 6px;
}

.schema-status.loaded {
  color: var(--text-success);
  background: var(--success-bg);
}

/* ---------------------------------------------------------
   Dialect Selector
--------------------------------------------------------- */
.dialect-select {
  width: 100%;
  padding: 0.75rem 1rem;
  background: var(--bg-input);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 0.9rem;
  cursor: pointer;
  transition: border-color 0.2s ease;
}

.dialect-select:focus {
  outline: none;
  border-color: var(--accent-primary);
}

/* ---------------------------------------------------------
   Clear Button
--------------------------------------------------------- */
.clear-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  background: transparent;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  color: var(--text-secondary);
  font-size: 0.875rem;
  cursor: pointer;
  transition: all 0.2s ease;
  margin-top: auto;
}

.clear-btn:hover:not(:disabled) {
  border-color: var(--danger-color);
  color: var(--danger-color);
  background: var(--danger-bg);
}

.clear-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ---------------------------------------------------------
   Chat Main Area
--------------------------------------------------------- */
.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.chat-header {
  padding: 1.25rem 2rem;
  border-bottom: 1px solid var(--border-color);
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: var(--bg-primary);
}

.chat-title h1 {
  font-size: 1.35rem;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 0.25rem;
}

.chat-title p {
  font-size: 0.85rem;
  color: var(--text-secondary);
}

.dialect-badge {
  padding: 0.5rem 1rem;
  background: var(--accent-bg);
  color: var(--accent-primary);
  border-radius: 20px;
  font-size: 0.8rem;
  font-weight: 500;
}

/* ---------------------------------------------------------
   Chat Messages
--------------------------------------------------------- */
.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 2rem;
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.message-wrapper {
  display: flex;
  flex-direction: column;
  max-width: 75%;
  animation: fadeIn 0.3s ease;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.message-wrapper.user-message {
  align-self: flex-end;
}

.message-label {
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--text-muted);
  margin-bottom: 0.4rem;
  padding: 0 0.25rem;
}

.user-message .message-label {
  text-align: right;
}

.message-bubble {
  padding: 1rem 1.25rem;
  border-radius: 16px;
  line-height: 1.6;
}

.message-bubble p {
  margin: 0;
  white-space: pre-wrap;
  word-wrap: break-word;
}

.user-bubble {
  background: var(--accent-primary);
  color: white;
  border-bottom-right-radius: 4px;
}

.assistant-bubble {
  background: var(--bg-card);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
  border-bottom-left-radius: 4px;
}

.sql-bubble {
  background: var(--bg-code);
  border-color: var(--border-color);
}

.sql-bubble pre {
  margin: 0;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.85rem;
  line-height: 1.6;
  white-space: pre-wrap;
  word-wrap: break-word;
  color: var(--text-code);
}

/* Loading Animation */
.loading-bubble {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.loading-dots {
  display: flex;
  gap: 4px;
}

.loading-dots span {
  width: 8px;
  height: 8px;
  background: var(--accent-primary);
  border-radius: 50%;
  animation: bounce 1.4s infinite ease-in-out both;
}

.loading-dots span:nth-child(1) {
  animation-delay: -0.32s;
}

.loading-dots span:nth-child(2) {
  animation-delay: -0.16s;
}

@keyframes bounce {
  0%, 80%, 100% {
    transform: scale(0);
  }
  40% {
    transform: scale(1);
  }
}

.loading-text {
  color: var(--text-secondary);
  font-size: 0.9rem;
}

/* ---------------------------------------------------------
   Input Area
--------------------------------------------------------- */
.chat-input-area {
  padding: 1.5rem 2rem 2rem;
  border-top: 1px solid var(--border-color);
  background: var(--bg-primary);
}

.input-container {
  display: flex;
  gap: 0.75rem;
  align-items: flex-end;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 16px;
  padding: 0.75rem;
  transition: border-color 0.2s ease;
}

.input-container:focus-within {
  border-color: var(--accent-primary);
}

.message-input {
  flex: 1;
  padding: 0.5rem 0.75rem;
  background: transparent;
  border: none;
  color: var(--text-primary);
  font-size: 0.95rem;
  font-family: inherit;
  resize: none;
  min-height: 24px;
  max-height: 150px;
  line-height: 1.5;
}

.message-input:focus {
  outline: none;
}

.message-input::placeholder {
  color: var(--text-muted);
}

.message-input:disabled {
  opacity: 0.6;
}

.send-btn {
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--accent-primary);
  border: none;
  border-radius: 12px;
  color: white;
  cursor: pointer;
  transition: all 0.2s ease;
  flex-shrink: 0;
}

.send-btn:hover:not(:disabled) {
  background: var(--accent-hover);
  transform: scale(1.05);
}

.send-btn:disabled {
  background: var(--bg-hover);
  color: var(--text-muted);
  cursor: not-allowed;
}

.input-hint {
  margin-top: 0.75rem;
  font-size: 0.75rem;
  color: var(--text-muted);
  text-align: center;
}

.input-hint kbd {
  padding: 0.15rem 0.4rem;
  background: var(--bg-hover);
  border: 1px solid var(--border-color);
  border-radius: 4px;
  font-family: inherit;
  font-size: 0.7rem;
}

.hint-success {
  color: var(--text-success);
}

.hint-warning {
  color: var(--text-warning);
}

/* ---------------------------------------------------------
   Scrollbar Styling
--------------------------------------------------------- */
.chat-messages::-webkit-scrollbar,
.schema-textarea::-webkit-scrollbar,
.sidebar-content::-webkit-scrollbar {
  width: 8px;
}

.chat-messages::-webkit-scrollbar-track,
.schema-textarea::-webkit-scrollbar-track,
.sidebar-content::-webkit-scrollbar-track {
  background: transparent;
}

.chat-messages::-webkit-scrollbar-thumb,
.schema-textarea::-webkit-scrollbar-thumb,
.sidebar-content::-webkit-scrollbar-thumb {
  background: var(--border-color);
  border-radius: 4px;
}

.chat-messages::-webkit-scrollbar-thumb:hover,
.schema-textarea::-webkit-scrollbar-thumb:hover,
.sidebar-content::-webkit-scrollbar-thumb:hover {
  background: var(--text-muted);
}

/* ---------------------------------------------------------
   Responsive
--------------------------------------------------------- */
@media (max-width: 900px) {
  .app-container {
    flex-direction: column;
  }
  
  .sidebar {
    width: 100%;
    min-width: 100%;
    max-height: 45vh;
  }
  
  .schema-textarea {
    height: 120px;
  }
  
  .message-wrapper {
    max-width: 90%;
  }
}
</style>

