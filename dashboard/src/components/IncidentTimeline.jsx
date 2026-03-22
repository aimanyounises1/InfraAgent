import React, { useEffect, useRef } from 'react';
import {
  AlertTriangle,
  Bell,
  CheckCircle2,
  XCircle,
  Clock,
  BarChart3,
  Activity,
} from 'lucide-react';
import useInfraAgent from '../hooks/useInfraAgent';

/**
 * Format a timestamp into a relative time string (e.g., "5m ago", "2h ago").
 *
 * @param {string} timestamp - ISO 8601 timestamp or epoch-compatible string.
 * @returns {string} Relative time description.
 */
function relativeTime(timestamp) {
  if (!timestamp) return 'Unknown';

  const now = Date.now();
  const then = new Date(timestamp).getTime();

  if (isNaN(then)) return 'Unknown';

  const diffMs = now - then;
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHr = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHr / 24);

  if (diffSec < 60) return `${diffSec}s ago`;
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffHr < 24) return `${diffHr}h ago`;
  return `${diffDay}d ago`;
}

/**
 * SeverityBadge -- Color-coded severity indicator.
 *
 * Maps severity levels to accent colors:
 * - Critical / Highest -> red
 * - High / high urgency -> amber
 * - Medium / warning -> blue
 * - Low / Info -> gray
 */
function SeverityBadge({ severity }) {
  const normalized = (severity || '').toLowerCase();

  if (normalized === 'critical' || normalized === 'highest') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-accent-red/10 text-accent-red">
        <XCircle size={10} />
        Critical
      </span>
    );
  }

  if (normalized === 'high') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-accent-amber/10 text-accent-amber">
        <AlertTriangle size={10} />
        High
      </span>
    );
  }

  if (normalized === 'medium' || normalized === 'warning') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-accent-blue/10 text-accent-blue">
        <Activity size={10} />
        Medium
      </span>
    );
  }

  // Low / info / unknown
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-gray-700/40 text-gray-400">
      <Bell size={10} />
      {severity || 'Low'}
    </span>
  );
}

/**
 * StatusIndicator -- Shows the current incident status with color coding.
 */
function StatusIndicator({ status }) {
  const normalized = (status || '').toLowerCase();

  if (normalized === 'triggered' || normalized === 'firing') {
    return (
      <span className="text-xs font-mono text-accent-red">
        triggered
      </span>
    );
  }

  if (normalized === 'acknowledged' || normalized === 'pending') {
    return (
      <span className="text-xs font-mono text-accent-amber">
        acknowledged
      </span>
    );
  }

  if (normalized === 'resolved' || normalized === 'ok') {
    return (
      <span className="text-xs font-mono text-accent-green">
        resolved
      </span>
    );
  }

  return (
    <span className="text-xs font-mono text-gray-500">
      {status || 'unknown'}
    </span>
  );
}

/**
 * SourceIcon -- Renders an icon representing the alert source.
 */
function SourceIcon({ source }) {
  const normalized = (source || '').toLowerCase();

  if (normalized.includes('pagerduty') || normalized.includes('pager')) {
    return <Bell size={12} className="text-accent-green" title="PagerDuty" />;
  }

  if (normalized.includes('grafana') || normalized.includes('prometheus')) {
    return <BarChart3 size={12} className="text-accent-amber" title="Grafana" />;
  }

  return <Activity size={12} className="text-gray-500" title={source || 'Unknown'} />;
}

/**
 * Determine the severity of an incident from its urgency or title.
 *
 * PagerDuty incidents use "urgency" (high/low), and may encode severity
 * in the title prefix (CRITICAL:, WARNING:, INFO:).
 */
function deriveSeverity(incident) {
  // Check for explicit severity field
  if (incident.severity) return incident.severity;

  // Check title prefix
  const title = (incident.title || '').toUpperCase();
  if (title.startsWith('CRITICAL')) return 'Critical';
  if (title.startsWith('WARNING') || title.startsWith('WARN')) return 'High';
  if (title.startsWith('INFO')) return 'Low';

  // Fall back to urgency
  const urgency = (incident.urgency || '').toLowerCase();
  if (urgency === 'high') return 'High';
  if (urgency === 'low') return 'Low';

  return 'Medium';
}

/**
 * Determine the source string from incident data.
 */
function deriveSource(incident) {
  if (incident.source) return incident.source;
  if (incident.service?.summary) return incident.service.summary;
  if (incident.html_url && incident.html_url.includes('pagerduty')) return 'PagerDuty';
  if (incident.labels?.alertname) return 'Grafana';
  return 'Unknown';
}

/**
 * Determine the timestamp to sort/display from incident data.
 */
function deriveTimestamp(incident) {
  return incident.created_at || incident.activeAt || incident.updated_at || '';
}

/**
 * IncidentCard -- A single incident entry in the timeline.
 */
function IncidentCard({ incident }) {
  const severity = deriveSeverity(incident);
  const source = deriveSource(incident);
  const timestamp = deriveTimestamp(incident);
  const title = incident.title || incident.annotations?.summary || 'Untitled Incident';
  const status = incident.status || incident.state || 'unknown';

  return (
    <div className="bg-bg-tertiary rounded-lg p-3 border border-gray-800 hover:border-gray-700 transition-colors">
      <div className="flex items-start justify-between mb-2">
        <SeverityBadge severity={severity} />
        <div className="flex items-center gap-2">
          <SourceIcon source={source} />
          <StatusIndicator status={status} />
        </div>
      </div>
      <p className="text-sm text-white mb-2 leading-snug">{title}</p>
      <div className="flex items-center justify-between text-xs text-gray-500">
        <span className="truncate max-w-[160px]" title={source}>{source}</span>
        <span className="flex items-center gap-1 shrink-0">
          <Clock size={10} />
          {relativeTime(timestamp)}
        </span>
      </div>
    </div>
  );
}

/**
 * TimelineDot -- The dot and connecting line in the vertical timeline.
 */
function TimelineDot({ isLast }) {
  return (
    <div className="flex flex-col items-center mr-3">
      <div className="w-2.5 h-2.5 rounded-full bg-accent-blue border-2 border-bg-secondary shrink-0" />
      {!isLast && <div className="w-0.5 flex-1 bg-gray-800 min-h-[16px]" />}
    </div>
  );
}

/**
 * LoadingSkeleton -- Pulsing placeholder while incident data loads.
 */
function LoadingSkeleton() {
  return (
    <div className="space-y-3">
      {[0, 1, 2].map((i) => (
        <div key={i} className="bg-bg-tertiary rounded-lg p-3 border border-gray-800 animate-pulse">
          <div className="h-4 bg-gray-700 rounded w-1/3 mb-2" />
          <div className="h-3 bg-gray-700 rounded w-full mb-1" />
          <div className="h-3 bg-gray-700 rounded w-1/2" />
        </div>
      ))}
    </div>
  );
}

/**
 * IncidentTimeline -- Vertical timeline of incidents with severity badges.
 *
 * Fetches active incidents on mount and polls every 30 seconds.
 */
export default function IncidentTimeline() {
  const { incidents, loading, error, fetchIncidents } = useInfraAgent();
  const intervalRef = useRef(null);

  useEffect(() => {
    fetchIncidents();

    intervalRef.current = setInterval(() => {
      fetchIncidents();
    }, 30000);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [fetchIncidents]);

  // Normalize incidents data: API may return { incidents: [...] } or flat array
  const incidentList = Array.isArray(incidents)
    ? incidents
    : Array.isArray(incidents?.incidents)
      ? incidents.incidents
      : [];

  // Sort by timestamp descending (most recent first)
  const sortedIncidents = [...incidentList].sort((a, b) => {
    const tsA = new Date(deriveTimestamp(a)).getTime() || 0;
    const tsB = new Date(deriveTimestamp(b)).getTime() || 0;
    return tsB - tsA;
  });

  const isLoading = loading && incidentList.length === 0;

  return (
    <div className="bg-bg-secondary rounded-lg border border-gray-800 p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-display font-semibold text-white">
          Incident Timeline
        </h2>
        {sortedIncidents.length > 0 && (
          <span className="text-xs font-mono text-gray-500">
            {sortedIncidents.length} active
          </span>
        )}
      </div>

      {/* Error State */}
      {error && (
        <div className="mb-4 p-3 rounded-md bg-accent-red/10 border border-accent-red/20">
          <p className="text-sm text-accent-red flex items-center gap-2">
            <XCircle size={14} />
            {error}
          </p>
        </div>
      )}

      {/* Loading State */}
      {isLoading && <LoadingSkeleton />}

      {/* Timeline Content */}
      {!isLoading && sortedIncidents.length > 0 && (
        <div className="space-y-0">
          {sortedIncidents.map((incident, idx) => {
            const key = incident.id || incident.incident_number || idx;
            const isLast = idx === sortedIncidents.length - 1;

            return (
              <div key={key} className="flex">
                <TimelineDot isLast={isLast} />
                <div className="flex-1 pb-3">
                  <IncidentCard incident={incident} />
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Empty State */}
      {!isLoading && sortedIncidents.length === 0 && !error && (
        <div className="text-center py-8">
          <CheckCircle2 size={32} className="mx-auto text-accent-green mb-2" />
          <p className="text-sm text-gray-500">No active incidents</p>
          <p className="text-xs text-gray-600 mt-1">All systems operational</p>
        </div>
      )}
    </div>
  );
}
