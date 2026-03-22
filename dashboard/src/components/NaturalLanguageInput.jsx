import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Send, Loader2, Bot, User, Tag, Sparkles, ArrowDown } from 'lucide-react';
import useInfraAgent from '../hooks/useInfraAgent';

// ---------------------------------------------------------------------------
// Unique ID generator for chat messages
// ---------------------------------------------------------------------------
let _msgId = 0;
function nextId() {
  _msgId += 1;
  return `msg-${_msgId}-${Date.now()}`;
}

// ---------------------------------------------------------------------------
// IntentBadge -- Color-coded pill showing the classified query intent.
// ---------------------------------------------------------------------------
function IntentBadge({ intent }) {
  const normalized = (intent || '').toLowerCase();

  const config = {
    kubernetes: { bg: 'bg-accent-blue/15', text: 'text-accent-blue', label: 'kubernetes' },
    k8s:        { bg: 'bg-accent-blue/15', text: 'text-accent-blue', label: 'kubernetes' },
    gpu:        { bg: 'bg-accent-green/15', text: 'text-accent-green', label: 'gpu' },
    incident:   { bg: 'bg-accent-red/15', text: 'text-accent-red', label: 'incident' },
    incidents:  { bg: 'bg-accent-red/15', text: 'text-accent-red', label: 'incident' },
    error:      { bg: 'bg-accent-red/15', text: 'text-accent-red', label: 'error' },
  };

  const c = config[normalized] || {
    bg: 'bg-gray-700/30',
    text: 'text-gray-400',
    label: intent || 'general',
  };

  return (
    <span
      className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-semibold uppercase tracking-wide ${c.bg} ${c.text}`}
    >
      <Tag size={10} />
      {c.label}
    </span>
  );
}

// ---------------------------------------------------------------------------
// renderMarkdown -- Lightweight converter from InfraAgent response text to
// React elements.  Handles the subset of markdown the backend emits without
// pulling in a full markdown library.
// ---------------------------------------------------------------------------
function renderMarkdown(text) {
  if (!text || typeof text !== 'string') {
    return <p className="text-sm text-gray-400">No response content.</p>;
  }

  const lines = text.split('\n');
  const elements = [];
  let listBuffer = [];
  let listKey = 0;

  /** Flush any accumulated list items into a <ul>. */
  function flushList() {
    if (listBuffer.length === 0) return;
    elements.push(
      <ul key={`list-${listKey}`} className="space-y-1 my-1.5 ml-4">
        {listBuffer.map((item, i) => (
          <li
            key={i}
            className="text-sm text-gray-300 list-disc list-outside leading-relaxed"
          >
            {renderInline(item)}
          </li>
        ))}
      </ul>,
    );
    listBuffer = [];
    listKey += 1;
  }

  /**
   * Render inline formatting:  **bold**, `code`, [OK], [WARN] / [WARNING].
   *
   * @param {string} line
   * @returns {React.ReactNode}
   */
  function renderInline(line) {
    // Split into segments by bold / code markers
    const parts = [];
    let remaining = line;
    let safetyCounter = 0;

    while (remaining.length > 0 && safetyCounter < 200) {
      safetyCounter += 1;

      // Inline code `...`
      const codeMatch = remaining.match(/^(.*?)`([^`]+)`(.*)$/s);
      if (codeMatch) {
        if (codeMatch[1]) parts.push(codeMatch[1]);
        parts.push(
          <code
            key={`c-${parts.length}`}
            className="px-1.5 py-0.5 rounded bg-bg-primary/60 text-accent-green text-xs font-mono"
          >
            {codeMatch[2]}
          </code>,
        );
        remaining = codeMatch[3];
        continue;
      }

      // Bold **...**
      const boldMatch = remaining.match(/^(.*?)\*\*([^*]+)\*\*(.*)$/s);
      if (boldMatch) {
        if (boldMatch[1]) parts.push(boldMatch[1]);
        parts.push(
          <strong key={`b-${parts.length}`} className="font-semibold text-white">
            {boldMatch[2]}
          </strong>,
        );
        remaining = boldMatch[3];
        continue;
      }

      // No more inline markers -- push the rest as-is
      parts.push(remaining);
      break;
    }

    return parts;
  }

  for (let i = 0; i < lines.length; i++) {
    const raw = lines[i];
    const key = `ln-${i}`;

    // --- Horizontal rule ---
    if (/^-{3,}$/.test(raw.trim())) {
      flushList();
      elements.push(<hr key={key} className="border-gray-700/60 my-3" />);
      continue;
    }

    // --- H2 header ---
    if (raw.startsWith('## ')) {
      flushList();
      elements.push(
        <h2 key={key} className="text-[15px] font-bold text-white mt-3 mb-1.5 leading-snug">
          {renderInline(raw.slice(3))}
        </h2>,
      );
      continue;
    }

    // --- H3 header ---
    if (raw.startsWith('### ')) {
      flushList();
      elements.push(
        <h3 key={key} className="text-sm font-semibold text-gray-300 mt-2.5 mb-1 leading-snug">
          {renderInline(raw.slice(4))}
        </h3>,
      );
      continue;
    }

    // --- H1 header (rare, but handle it) ---
    if (raw.startsWith('# ')) {
      flushList();
      elements.push(
        <h2 key={key} className="text-base font-bold text-white mt-3 mb-1.5 leading-snug">
          {renderInline(raw.slice(2))}
        </h2>,
      );
      continue;
    }

    // --- Status lines: [OK], [WARN], [WARNING], [ERROR], [CRITICAL] ---
    if (/\[OK\]/i.test(raw)) {
      flushList();
      elements.push(
        <p key={key} className="text-sm text-accent-green font-mono leading-relaxed">
          {renderInline(raw)}
        </p>,
      );
      continue;
    }
    if (/\[WARN(ING)?\]/i.test(raw)) {
      flushList();
      elements.push(
        <p key={key} className="text-sm text-accent-amber font-mono leading-relaxed">
          {renderInline(raw)}
        </p>,
      );
      continue;
    }
    if (/\[ERROR\]|\[CRITICAL\]/i.test(raw)) {
      flushList();
      elements.push(
        <p key={key} className="text-sm text-accent-red font-mono leading-relaxed">
          {renderInline(raw)}
        </p>,
      );
      continue;
    }

    // --- Bullet list items (starting with "  - ", " - ", "- ", or "* ") ---
    const listMatch = raw.match(/^\s*[-*]\s+(.*)$/);
    if (listMatch) {
      listBuffer.push(listMatch[1]);
      continue;
    }

    // --- Empty line ---
    if (raw.trim() === '') {
      flushList();
      elements.push(<div key={key} className="h-1.5" />);
      continue;
    }

    // --- Code-fence lines (``` blocks) ---
    if (raw.trim().startsWith('```')) {
      flushList();
      // Consume lines until closing fence
      const codeLines = [];
      let j = i + 1;
      while (j < lines.length && !lines[j].trim().startsWith('```')) {
        codeLines.push(lines[j]);
        j++;
      }
      elements.push(
        <pre
          key={key}
          className="text-xs font-mono text-gray-300 bg-bg-primary/50 rounded-lg p-3 my-2 overflow-x-auto border border-gray-800/60"
        >
          {codeLines.join('\n')}
        </pre>,
      );
      i = j; // skip closing fence
      continue;
    }

    // --- Default paragraph ---
    flushList();
    elements.push(
      <p key={key} className="text-sm text-gray-300 leading-relaxed">
        {renderInline(raw)}
      </p>,
    );
  }

  // Flush any remaining list items
  flushList();

  return elements;
}

// ---------------------------------------------------------------------------
// TypingIndicator -- Three pulsing dots shown while waiting for AI response.
// ---------------------------------------------------------------------------
function TypingIndicator() {
  return (
    <div className="flex items-start gap-3 max-w-[85%]">
      <div className="shrink-0 w-8 h-8 rounded-full bg-accent-green/10 flex items-center justify-center mt-0.5">
        <Bot size={16} className="text-accent-green" />
      </div>
      <div className="bg-bg-tertiary rounded-2xl rounded-tl-sm px-4 py-3 border border-gray-800/60">
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 bg-accent-green/60 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
          <span className="w-2 h-2 bg-accent-green/60 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
          <span className="w-2 h-2 bg-accent-green/60 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// UserBubble -- Right-aligned chat bubble for user messages.
// ---------------------------------------------------------------------------
function UserBubble({ content, timestamp }) {
  return (
    <div className="flex items-start gap-3 justify-end">
      <div className="max-w-[85%] flex flex-col items-end">
        <div className="bg-accent-blue/15 border border-accent-blue/20 text-white rounded-2xl rounded-tr-sm px-4 py-2.5">
          <p className="text-sm font-mono leading-relaxed">{content}</p>
        </div>
        {timestamp && (
          <span className="text-[10px] text-gray-600 mt-1 mr-1">
            {timestamp}
          </span>
        )}
      </div>
      <div className="shrink-0 w-8 h-8 rounded-full bg-accent-blue/10 flex items-center justify-center mt-0.5">
        <User size={16} className="text-accent-blue" />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// AssistantBubble -- Left-aligned chat bubble for AI responses.
// ---------------------------------------------------------------------------
function AssistantBubble({ content, intent, actions_taken, timestamp }) {
  return (
    <div className="flex items-start gap-3 max-w-[85%]">
      <div className="shrink-0 w-8 h-8 rounded-full bg-accent-green/10 flex items-center justify-center mt-0.5">
        <Bot size={16} className="text-accent-green" />
      </div>
      <div className="flex-1 min-w-0 flex flex-col">
        {/* Response card */}
        <div className="bg-bg-tertiary rounded-2xl rounded-tl-sm px-4 py-3 border border-gray-800/60">
          {/* Intent badge */}
          {intent && (
            <div className="mb-2.5">
              <IntentBadge intent={intent} />
            </div>
          )}

          {/* Rendered markdown content */}
          <div className="space-y-0.5">{renderMarkdown(content)}</div>

          {/* Actions taken */}
          {actions_taken && actions_taken.length > 0 && (
            <div className="mt-3 pt-2.5 border-t border-gray-700/40">
              <p className="text-[10px] uppercase tracking-wider text-gray-500 font-semibold mb-1.5">
                Actions taken
              </p>
              <div className="flex flex-wrap gap-1.5">
                {actions_taken.map((action, idx) => (
                  <span
                    key={idx}
                    className="inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-mono bg-accent-green/10 text-accent-green border border-accent-green/20"
                  >
                    {action}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Timestamp */}
        {timestamp && (
          <span className="text-[10px] text-gray-600 mt-1 ml-1">
            {timestamp}
          </span>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// WelcomeScreen -- Shown when there are no messages yet.
// ---------------------------------------------------------------------------
function WelcomeScreen() {
  const suggestions = [
    'Show cluster status',
    'Check GPU health',
    'List active incidents',
    'Scale nginx to 5 replicas',
  ];

  return (
    <div className="flex-1 flex flex-col items-center justify-center px-6 text-center">
      <div className="w-14 h-14 rounded-2xl bg-accent-green/10 border border-accent-green/20 flex items-center justify-center mb-5">
        <Sparkles size={28} className="text-accent-green" />
      </div>
      <h2 className="text-lg font-display font-semibold text-white mb-1.5">
        How can I help?
      </h2>
      <p className="text-sm text-gray-500 max-w-[280px] leading-relaxed">
        Ask me about your Kubernetes clusters, GPU health, or active incidents.
      </p>
      <div className="mt-6 flex flex-wrap justify-center gap-2">
        {suggestions.map((s) => (
          <button
            key={s}
            type="button"
            className="px-3 py-1.5 rounded-lg text-xs font-mono text-gray-400 bg-bg-tertiary/60 border border-gray-800/60 hover:border-accent-green/30 hover:text-accent-green transition-colors cursor-default"
            tabIndex={-1}
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// NaturalLanguageInput -- Full-height chatbot panel for the InfraAgent.
//
// Renders a scrollable conversation history with user/assistant bubbles,
// an inline markdown renderer, and a bottom-pinned input area.
// ---------------------------------------------------------------------------
export default function NaturalLanguageInput() {
  const [query, setQuery] = useState('');
  const [messages, setMessages] = useState([]);
  const { sendQuery, loading } = useInfraAgent();

  const messagesEndRef = useRef(null);
  const scrollContainerRef = useRef(null);
  const inputRef = useRef(null);
  const [showScrollBtn, setShowScrollBtn] = useState(false);

  // -------------------------------------------------------------------------
  // Auto-scroll to the bottom when new messages arrive
  // -------------------------------------------------------------------------
  const scrollToBottom = useCallback((behavior = 'smooth') => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior });
    }
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading, scrollToBottom]);

  // -------------------------------------------------------------------------
  // Show / hide "scroll to bottom" button
  // -------------------------------------------------------------------------
  const handleScroll = useCallback(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    setShowScrollBtn(distanceFromBottom > 120);
  }, []);

  // -------------------------------------------------------------------------
  // Format current time for timestamps
  // -------------------------------------------------------------------------
  function timeNow() {
    return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  // -------------------------------------------------------------------------
  // Submit handler
  // -------------------------------------------------------------------------
  const handleSubmit = async (e) => {
    e.preventDefault();
    const trimmed = query.trim();
    if (!trimmed || loading) return;

    const userMsg = {
      id: nextId(),
      role: 'user',
      content: trimmed,
      timestamp: timeNow(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setQuery('');

    // Send to API
    const result = await sendQuery(trimmed);

    const assistantMsg = {
      id: nextId(),
      role: 'assistant',
      content: result?.response || 'Failed to get a response. Please try again.',
      intent: result?.intent || 'error',
      actions_taken: result?.actions_taken || [],
      timestamp: timeNow(),
    };

    setMessages((prev) => [...prev, assistantMsg]);

    // Re-focus input after response
    if (inputRef.current) {
      inputRef.current.focus();
    }
  };

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------
  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Chat header */}
      <div className="shrink-0 px-5 py-4 border-b border-gray-800/80">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-accent-green/10 border border-accent-green/20 flex items-center justify-center">
            <Bot size={18} className="text-accent-green" />
          </div>
          <div>
            <h2 className="text-sm font-display font-semibold text-white leading-tight">
              InfraAgent Chat
            </h2>
            <p className="text-[11px] text-gray-500 font-mono leading-tight mt-0.5">
              Powered by NVIDIA Nemotron via Ollama
            </p>
          </div>
        </div>
      </div>

      {/* Messages area */}
      <div
        ref={scrollContainerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto scrollbar-thin relative"
      >
        {messages.length === 0 && !loading ? (
          <WelcomeScreen />
        ) : (
          <div className="px-4 py-4 space-y-4">
            {messages.map((msg) =>
              msg.role === 'user' ? (
                <UserBubble
                  key={msg.id}
                  content={msg.content}
                  timestamp={msg.timestamp}
                />
              ) : (
                <AssistantBubble
                  key={msg.id}
                  content={msg.content}
                  intent={msg.intent}
                  actions_taken={msg.actions_taken}
                  timestamp={msg.timestamp}
                />
              ),
            )}
            {loading && <TypingIndicator />}
            <div ref={messagesEndRef} />
          </div>
        )}

        {/* Scroll-to-bottom FAB */}
        {showScrollBtn && (
          <button
            type="button"
            onClick={() => scrollToBottom()}
            className="sticky bottom-3 left-1/2 -translate-x-1/2 z-10 w-8 h-8 rounded-full bg-bg-tertiary border border-gray-700 flex items-center justify-center shadow-lg hover:border-accent-green/40 transition-colors"
            aria-label="Scroll to bottom"
          >
            <ArrowDown size={14} className="text-gray-400" />
          </button>
        )}
      </div>

      {/* Input area */}
      <div className="shrink-0 border-t border-gray-800/80 px-4 py-3 bg-bg-secondary">
        <form onSubmit={handleSubmit} className="flex items-end gap-2">
          <div className="relative flex-1">
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Ask InfraAgent..."
              disabled={loading}
              className="w-full bg-bg-tertiary/60 border border-gray-700/60 rounded-xl px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-accent-green/50 focus:ring-1 focus:ring-accent-green/20 disabled:opacity-50 transition-all font-mono"
            />
          </div>
          <button
            type="submit"
            disabled={loading || !query.trim()}
            className="shrink-0 w-10 h-10 rounded-xl bg-accent-green flex items-center justify-center text-bg-primary hover:opacity-90 transition-opacity disabled:opacity-30 disabled:cursor-not-allowed"
            aria-label="Send message"
          >
            {loading ? (
              <Loader2 size={18} className="animate-spin" />
            ) : (
              <Send size={18} />
            )}
          </button>
        </form>
      </div>
    </div>
  );
}
