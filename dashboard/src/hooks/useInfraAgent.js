import { useState, useCallback, useEffect, useRef } from 'react';

/**
 * useInfraAgent -- Custom hook for communicating with the InfraAgent API.
 *
 * Provides:
 *  - sendQuery(text) -> POST /api/chat
 *  - fetchPods(namespace) -> GET /api/k8s/pods
 *  - fetchDeployments(namespace) -> GET /api/k8s/deployments
 *  - fetchGpuStatus() -> GET /api/gpu/status
 *  - fetchGpuHealth() -> GET /api/gpu/health
 *  - fetchIncidents() -> GET /api/incidents/active
 *  - Real-time WebSocket updates
 *  - Loading/error state for each domain
 */
export default function useInfraAgent() {
  // --- Chat state ---
  const [response, setResponse] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // --- Domain state ---
  const [pods, setPods] = useState(null);
  const [deployments, setDeployments] = useState(null);
  const [gpuStatus, setGpuStatus] = useState(null);
  const [gpuHealth, setGpuHealth] = useState(null);
  const [incidents, setIncidents] = useState(null);

  // --- WebSocket ref ---
  const wsRef = useRef(null);
  const reconnectTimerRef = useRef(null);

  // ---------------------------------------------------------------------------
  // POST /api/chat
  // ---------------------------------------------------------------------------
  const sendQuery = useCallback(async (query) => {
    if (!query || typeof query !== 'string' || query.trim().length === 0) {
      setError('Query must be a non-empty string');
      return null;
    }

    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: query.trim() }),
      });
      if (!res.ok) {
        throw new Error(`API error: ${res.status} ${res.statusText}`);
      }
      const data = await res.json();
      setResponse(data);
      return data;
    } catch (err) {
      setError(err.message);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  // ---------------------------------------------------------------------------
  // GET /api/k8s/pods?namespace=...
  // ---------------------------------------------------------------------------
  const fetchPods = useCallback(async (namespace = 'default') => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ namespace });
      const res = await fetch(`/api/k8s/pods?${params}`);
      if (!res.ok) {
        throw new Error(`Failed to fetch pods: ${res.status} ${res.statusText}`);
      }
      const data = await res.json();
      setPods(data);
      return data;
    } catch (err) {
      setError(err.message);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  // ---------------------------------------------------------------------------
  // GET /api/k8s/deployments?namespace=...
  // ---------------------------------------------------------------------------
  const fetchDeployments = useCallback(async (namespace = 'default') => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ namespace });
      const res = await fetch(`/api/k8s/deployments?${params}`);
      if (!res.ok) {
        throw new Error(`Failed to fetch deployments: ${res.status} ${res.statusText}`);
      }
      const data = await res.json();
      setDeployments(data);
      return data;
    } catch (err) {
      setError(err.message);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  // ---------------------------------------------------------------------------
  // GET /api/gpu/status
  // ---------------------------------------------------------------------------
  const fetchGpuStatus = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/gpu/status');
      if (!res.ok) {
        throw new Error(`Failed to fetch GPU status: ${res.status} ${res.statusText}`);
      }
      const data = await res.json();
      setGpuStatus(data);
      return data;
    } catch (err) {
      setError(err.message);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  // ---------------------------------------------------------------------------
  // GET /api/gpu/health
  // ---------------------------------------------------------------------------
  const fetchGpuHealth = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/gpu/health');
      if (!res.ok) {
        throw new Error(`Failed to fetch GPU health: ${res.status} ${res.statusText}`);
      }
      const data = await res.json();
      setGpuHealth(data);
      return data;
    } catch (err) {
      setError(err.message);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  // ---------------------------------------------------------------------------
  // GET /api/incidents/active
  // ---------------------------------------------------------------------------
  const fetchIncidents = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/incidents/active');
      if (!res.ok) {
        throw new Error(`Failed to fetch incidents: ${res.status} ${res.statusText}`);
      }
      const data = await res.json();
      setIncidents(data);
      return data;
    } catch (err) {
      setError(err.message);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  // ---------------------------------------------------------------------------
  // WebSocket connection for real-time updates
  // ---------------------------------------------------------------------------
  useEffect(() => {
    /** Connect to the WebSocket endpoint and handle incoming messages. */
    function connect() {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${protocol}//${window.location.host}/ws/updates`;

      try {
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
          // Clear any pending reconnect timer on successful connection
          if (reconnectTimerRef.current) {
            clearTimeout(reconnectTimerRef.current);
            reconnectTimerRef.current = null;
          }
        };

        ws.onmessage = (event) => {
          try {
            const message = JSON.parse(event.data);
            if (!message || typeof message.type !== 'string') {
              return;
            }

            switch (message.type) {
              case 'chat_response':
                setResponse({
                  response: message.response,
                  intent: message.intent,
                  actions_taken: message.actions_taken || [],
                });
                break;

              case 'chat_error':
                setError(message.error || 'Unknown WebSocket error');
                break;

              case 'pod_update':
                setPods(message.data);
                break;

              case 'deployment_update':
                setDeployments(message.data);
                break;

              case 'gpu_update':
                setGpuStatus(message.data);
                break;

              case 'gpu_health_update':
                setGpuHealth(message.data);
                break;

              case 'incident_update':
                setIncidents(message.data);
                break;

              default:
                // Unrecognized message type -- silently ignore
                break;
            }
          } catch {
            // Malformed JSON -- ignore silently
          }
        };

        ws.onerror = () => {
          // Error handling is delegated to onclose for reconnection
        };

        ws.onclose = () => {
          wsRef.current = null;
          // Attempt reconnection after 5 seconds
          reconnectTimerRef.current = setTimeout(connect, 5000);
        };
      } catch {
        // WebSocket construction failed -- retry after delay
        reconnectTimerRef.current = setTimeout(connect, 5000);
      }
    }

    connect();

    return () => {
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, []);

  return {
    // Chat
    response,
    loading,
    error,
    sendQuery,

    // Kubernetes
    pods,
    deployments,
    fetchPods,
    fetchDeployments,

    // GPU
    gpuStatus,
    gpuHealth,
    fetchGpuStatus,
    fetchGpuHealth,

    // Incidents
    incidents,
    fetchIncidents,
  };
}
