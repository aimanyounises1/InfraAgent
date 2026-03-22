import React, { useEffect, useRef } from 'react';
import { CheckCircle2, AlertTriangle, XCircle, Circle, Server, RefreshCw } from 'lucide-react';
import useInfraAgent from '../hooks/useInfraAgent';

/**
 * StatusBadge -- Renders a color-coded status indicator for a pod.
 *
 * @param {{ status: string }} props
 */
function StatusBadge({ status }) {
  const normalized = (status || '').toLowerCase();

  if (normalized === 'running') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-accent-green/10 text-accent-green">
        <CheckCircle2 size={12} />
        Running
      </span>
    );
  }

  if (normalized === 'failed' || normalized === 'crashloopbackoff') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-accent-red/10 text-accent-red">
        <XCircle size={12} />
        {status}
      </span>
    );
  }

  if (normalized === 'pending') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-accent-amber/10 text-accent-amber">
        <AlertTriangle size={12} />
        Pending
      </span>
    );
  }

  // Unknown or other status
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-gray-700/40 text-gray-400">
      <Circle size={12} />
      {status || 'Unknown'}
    </span>
  );
}

/**
 * DeploymentSummary -- Shows a single deployment row with ready/total replicas.
 *
 * @param {{ deployment: object }} props
 */
function DeploymentSummary({ deployment }) {
  const ready = deployment.ready_replicas ?? 0;
  const total = deployment.replicas ?? 0;
  const isHealthy = ready === total && total > 0;

  return (
    <div className="flex items-center justify-between bg-bg-tertiary rounded-md px-3 py-2">
      <div className="flex items-center gap-2">
        <Server size={14} className={isHealthy ? 'text-accent-green' : 'text-accent-amber'} />
        <span className="text-sm font-mono text-white">{deployment.name}</span>
      </div>
      <span className={`text-xs font-mono ${isHealthy ? 'text-accent-green' : 'text-accent-amber'}`}>
        {ready}/{total} ready
      </span>
    </div>
  );
}

/**
 * PodCard -- Displays a single pod's status information.
 *
 * @param {{ pod: object }} props
 */
function PodCard({ pod }) {
  const totalRestarts = (pod.containers || []).reduce(
    (sum, c) => sum + (c.restart_count || 0),
    0
  );

  return (
    <div className="bg-bg-tertiary rounded-lg p-3 border border-gray-800 hover:border-gray-700 transition-colors">
      <div className="flex items-start justify-between mb-2">
        <p className="text-sm font-mono text-white truncate max-w-[200px]" title={pod.name}>
          {pod.name}
        </p>
        <StatusBadge status={pod.status} />
      </div>
      <div className="space-y-1 text-xs text-gray-400">
        <p>
          <span className="text-gray-500">Namespace:</span>{' '}
          <span className="text-gray-300">{pod.namespace}</span>
        </p>
        {pod.node && (
          <p>
            <span className="text-gray-500">Node:</span>{' '}
            <span className="text-gray-300">{pod.node}</span>
          </p>
        )}
        {totalRestarts > 0 && (
          <p className="text-accent-amber">
            <RefreshCw size={10} className="inline mr-1" />
            {totalRestarts} restart{totalRestarts !== 1 ? 's' : ''}
          </p>
        )}
      </div>
    </div>
  );
}

/**
 * LoadingSkeleton -- Pulsing placeholder while data loads.
 */
function LoadingSkeleton() {
  return (
    <div className="space-y-3">
      {[0, 1, 2].map((i) => (
        <div key={i} className="bg-bg-tertiary rounded-lg p-3 border border-gray-800 animate-pulse">
          <div className="h-4 bg-gray-700 rounded w-3/4 mb-2" />
          <div className="h-3 bg-gray-700 rounded w-1/2 mb-1" />
          <div className="h-3 bg-gray-700 rounded w-1/3" />
        </div>
      ))}
    </div>
  );
}

/**
 * ClusterStatus -- Grid of pods/nodes with color-coded health status.
 *
 * Fetches pod and deployment data from the API on mount and polls every 30s.
 */
export default function ClusterStatus() {
  const { pods, deployments, loading, error, fetchPods, fetchDeployments } = useInfraAgent();
  const intervalRef = useRef(null);

  useEffect(() => {
    // Initial fetch
    fetchPods();
    fetchDeployments();

    // Poll every 30 seconds
    intervalRef.current = setInterval(() => {
      fetchPods();
      fetchDeployments();
    }, 30000);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [fetchPods, fetchDeployments]);

  // Normalize pods data: the API may return an array or { pods: [...] } or { status: "not_implemented" }
  const podList = Array.isArray(pods)
    ? pods
    : Array.isArray(pods?.pods)
      ? pods.pods
      : [];

  const deploymentList = Array.isArray(deployments)
    ? deployments
    : Array.isArray(deployments?.deployments)
      ? deployments.deployments
      : [];

  const isLoading = loading && podList.length === 0;

  return (
    <div className="bg-bg-secondary rounded-lg border border-gray-800 p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-display font-semibold text-white">
          Cluster Status
        </h2>
        {podList.length > 0 && (
          <span className="text-xs font-mono text-gray-500">
            {podList.length} pod{podList.length !== 1 ? 's' : ''}
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

      {/* Content */}
      {!isLoading && (
        <>
          {/* Deployment Summary */}
          {deploymentList.length > 0 && (
            <div className="mb-4 space-y-2">
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
                Deployments
              </h3>
              {deploymentList.map((dep) => (
                <DeploymentSummary key={`${dep.namespace}-${dep.name}`} deployment={dep} />
              ))}
            </div>
          )}

          {/* Pod Grid */}
          {podList.length > 0 ? (
            <div>
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
                Pods
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {podList.map((pod) => (
                  <PodCard key={`${pod.namespace}-${pod.name}`} pod={pod} />
                ))}
              </div>
            </div>
          ) : (
            !error && (
              <div className="text-center py-8">
                <Server size={32} className="mx-auto text-gray-600 mb-2" />
                <p className="text-sm text-gray-500">No pods found in this namespace</p>
              </div>
            )
          )}
        </>
      )}
    </div>
  );
}
