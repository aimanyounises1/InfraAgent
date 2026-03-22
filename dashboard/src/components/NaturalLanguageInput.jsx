import React, { useState, useRef, useEffect } from 'react';
import { Send, Loader2, Bot, User, Tag } from 'lucide-react';
import useInfraAgent from '../hooks/useInfraAgent';

/**
 * IntentBadge -- Color-coded badge for the classified query intent.
 *
 * @param {{ intent: string }} props
 */
function IntentBadge({ intent }) {
  const normalized = (intent || '').toLowerCase();

  if (normalized === 'kubernetes' || normalized === 'k8s') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-accent-blue/10 text-accent-blue">
        <Tag size={10} />
        kubernetes
      </span>
    );
  }

  if (normalized === 'gpu') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-accent-green/10 text-accent-green">
        <Tag size={10} />
        gpu
      </span>
    );
  }

  if (normalized === 'incident' || normalized === 'incidents') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-accent-red/10 text-accent-red">
        <Tag size={10} />
        incident
      </span>
    );
  }

  if (normalized === 'error') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-accent-red/10 text-accent-red">
        <Tag size={10} />
        error
      </span>
    );
  }

  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-gray-700/40 text-gray-400">
      <Tag size={10} />
      {intent || 'general'}
    </span>
  );
}

/**
 * ResponseCard -- Displays a single query/response pair in the chat history.
 *
 * @param {{ entry: { query: string, response: object } }} props
 */
function ResponseCard({ entry }) {
  const { query, response } = entry;

  return (
    <div className="space-y-2">
      {/* User Query */}
      <div className="flex items-start gap-2">
        <div className="shrink-0 w-6 h-6 rounded-full bg-accent-blue/10 flex items-center justify-center mt-0.5">
          <User size={12} className="text-accent-blue" />
        </div>
        <p className="text-sm text-gray-300 pt-0.5">{query}</p>
      </div>

      {/* Agent Response */}
      {response && (
        <div className="flex items-start gap-2">
          <div className="shrink-0 w-6 h-6 rounded-full bg-accent-green/10 flex items-center justify-center mt-0.5">
            <Bot size={12} className="text-accent-green" />
          </div>
          <div className="flex-1 min-w-0">
            {/* Intent Badge */}
            <div className="mb-1.5">
              <IntentBadge intent={response.intent} />
            </div>

            {/* Response Text */}
            <div className="bg-bg-tertiary rounded-lg p-3 border border-gray-800">
              <pre className="text-sm font-mono text-gray-200 whitespace-pre-wrap break-words">
                {response.response || 'No response content.'}
              </pre>
            </div>

            {/* Actions Taken */}
            {response.actions_taken && response.actions_taken.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {response.actions_taken.map((action, idx) => (
                  <span
                    key={idx}
                    className="inline-block px-2 py-0.5 rounded text-xs font-mono bg-bg-tertiary border border-gray-700 text-gray-400"
                  >
                    {action}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * NaturalLanguageInput -- Chat-like input for natural language infrastructure commands.
 *
 * Wired to POST /api/chat via the useInfraAgent hook. Maintains a scrollable
 * conversation history and displays intent badges, response text, and action tags.
 */
export default function NaturalLanguageInput() {
  const [query, setQuery] = useState('');
  const [history, setHistory] = useState([]);
  const { sendQuery, loading } = useInfraAgent();
  const historyEndRef = useRef(null);
  const inputRef = useRef(null);

  // Auto-scroll to bottom when history changes
  useEffect(() => {
    if (historyEndRef.current) {
      historyEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [history]);

  /**
   * Handle form submission: send the query and append to history.
   */
  const handleSubmit = async (e) => {
    e.preventDefault();

    const trimmed = query.trim();
    if (!trimmed || loading) return;

    // Optimistically add the query to history with no response yet
    const entryIndex = history.length;
    setHistory((prev) => [...prev, { query: trimmed, response: null }]);
    setQuery('');

    // Send query and update the history entry with the response
    const result = await sendQuery(trimmed);

    setHistory((prev) => {
      const updated = [...prev];
      if (updated[entryIndex]) {
        updated[entryIndex] = {
          ...updated[entryIndex],
          response: result || { response: 'Failed to get response.', intent: 'error', actions_taken: [] },
        };
      }
      return updated;
    });

    // Re-focus input
    if (inputRef.current) {
      inputRef.current.focus();
    }
  };

  return (
    <div className="fixed bottom-0 left-0 right-0 bg-bg-primary border-t border-gray-800 z-50">
      {/* Chat History (scrollable) */}
      {history.length > 0 && (
        <div className="max-w-4xl mx-auto px-4">
          <div className="max-h-64 overflow-y-auto py-3 space-y-4 scrollbar-thin">
            {history.map((entry, idx) => (
              <ResponseCard key={idx} entry={entry} />
            ))}
            <div ref={historyEndRef} />
          </div>
        </div>
      )}

      {/* Input Form */}
      <form onSubmit={handleSubmit} className="p-4">
        <div className="max-w-4xl mx-auto flex gap-3">
          <div className="relative flex-1">
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Ask InfraAgent... (e.g., 'Scale nginx to 5 replicas')"
              disabled={loading}
              className="w-full bg-bg-secondary border border-gray-700 rounded-lg px-4 py-3 text-sm font-mono text-white placeholder-gray-500 focus:outline-none focus:border-accent-green disabled:opacity-50 transition-colors"
            />
            {/* Loading indicator inside input */}
            {loading && (
              <div className="absolute right-3 top-1/2 -translate-y-1/2">
                <Loader2 size={16} className="text-accent-green animate-spin" />
              </div>
            )}
          </div>
          <button
            type="submit"
            disabled={loading || !query.trim()}
            className="bg-accent-green text-bg-primary font-semibold px-6 py-3 rounded-lg text-sm hover:opacity-90 transition disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {loading ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <Send size={16} />
            )}
            Send
          </button>
        </div>
      </form>
    </div>
  );
}
