import React, { useEffect, useRef } from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import { Cpu, Thermometer, Zap, HardDrive, XCircle } from 'lucide-react';
import useInfraAgent from '../hooks/useInfraAgent';

/** Threshold-based color for GPU utilization percentage. */
function getUtilColor(pct) {
  if (pct < 50) return '#00FF88';  // accent-green
  if (pct <= 80) return '#FFB800'; // accent-amber
  return '#FF3366';                // accent-red
}

/**
 * Custom tooltip for the utilization bar chart.
 */
function UtilTooltip({ active, payload }) {
  if (!active || !payload || payload.length === 0) return null;

  const data = payload[0].payload;
  return (
    <div className="bg-bg-tertiary border border-gray-700 rounded-lg px-3 py-2 shadow-lg">
      <p className="text-xs font-mono text-white mb-1">{data.fullName || data.name}</p>
      <p className="text-xs text-gray-400">
        Utilization:{' '}
        <span className="font-semibold" style={{ color: getUtilColor(data.utilization) }}>
          {data.utilization}%
        </span>
      </p>
    </div>
  );
}

/**
 * GpuStatCard -- Compact stat card for a single GPU device.
 *
 * @param {{ gpu: object, index: number }} props
 */
function GpuStatCard({ gpu, index }) {
  const tempColor =
    gpu.temperature_c > 85
      ? 'text-accent-red'
      : gpu.temperature_c > 70
        ? 'text-accent-amber'
        : 'text-accent-green';

  const memUsedMb = gpu.memory_used_mb ?? 0;
  const memTotalMb = gpu.memory_total_mb ?? 0;
  const memUsedGb = (memUsedMb / 1024).toFixed(1);
  const memTotalGb = (memTotalMb / 1024).toFixed(1);

  return (
    <div className="bg-bg-tertiary rounded-lg p-3 border border-gray-800">
      <p className="text-xs font-mono text-gray-400 mb-2 truncate" title={gpu.name}>
        GPU {index}
      </p>
      <div className="space-y-1.5 text-xs">
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-1 text-gray-500">
            <Thermometer size={12} /> Temp
          </span>
          <span className={`font-mono font-medium ${tempColor}`}>
            {gpu.temperature_c}C
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-1 text-gray-500">
            <HardDrive size={12} /> VRAM
          </span>
          <span className="font-mono text-gray-300">
            {memUsedGb}/{memTotalGb} GB
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-1 text-gray-500">
            <Zap size={12} /> Power
          </span>
          <span className="font-mono text-gray-300">
            {gpu.power_draw_w}W / {gpu.power_limit_w}W
          </span>
        </div>
      </div>
    </div>
  );
}

/**
 * LoadingSkeleton -- Pulsing placeholder while GPU data loads.
 */
function LoadingSkeleton() {
  return (
    <div className="space-y-4">
      <div className="h-48 bg-bg-tertiary rounded-lg animate-pulse" />
      <div className="grid grid-cols-2 gap-3">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="h-24 bg-bg-tertiary rounded-lg animate-pulse" />
        ))}
      </div>
    </div>
  );
}

/**
 * GPUHeatmap -- Recharts bar chart showing GPU utilization across devices,
 * plus per-GPU stat cards for temperature, memory, and power.
 *
 * Fetches GPU status data on mount and polls every 10 seconds.
 */
export default function GPUHeatmap() {
  const { gpuStatus, loading, error, fetchGpuStatus } = useInfraAgent();
  const intervalRef = useRef(null);

  useEffect(() => {
    fetchGpuStatus();

    intervalRef.current = setInterval(() => {
      fetchGpuStatus();
    }, 3000);  // Poll every 3s for real-time GPU monitoring

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [fetchGpuStatus]);

  // The API may return { devices: [...] } (cluster summary) or a flat structure.
  // Normalize to an array of device objects.
  const devices = Array.isArray(gpuStatus)
    ? gpuStatus
    : Array.isArray(gpuStatus?.devices)
      ? gpuStatus.devices
      : [];

  const isLoading = loading && devices.length === 0;

  // Prepare chart data from device list
  const chartData = devices.map((gpu, idx) => {
    const shortName = `GPU ${gpu.device_index ?? idx}`;
    return {
      name: shortName,
      fullName: gpu.name || shortName,
      utilization: gpu.gpu_utilization_pct ?? 0,
    };
  });

  return (
    <div className="bg-bg-secondary rounded-lg border border-gray-800 p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-display font-semibold text-white">
          GPU Utilization
        </h2>
        {devices.length > 0 && (
          <span className="text-xs font-mono text-gray-500">
            {devices.length} device{devices.length !== 1 ? 's' : ''}
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
      {!isLoading && devices.length > 0 && (
        <>
          {/* Bar Chart */}
          <div className="mb-4" style={{ width: '100%', height: 200 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 5, right: 10, left: -10, bottom: 5 }}>
                <XAxis
                  dataKey="name"
                  tick={{ fill: '#9CA3AF', fontSize: 11, fontFamily: 'JetBrains Mono, monospace' }}
                  axisLine={{ stroke: '#374151' }}
                  tickLine={false}
                />
                <YAxis
                  domain={[0, 100]}
                  tick={{ fill: '#9CA3AF', fontSize: 11, fontFamily: 'JetBrains Mono, monospace' }}
                  axisLine={{ stroke: '#374151' }}
                  tickLine={false}
                  tickFormatter={(val) => `${val}%`}
                />
                <Tooltip content={<UtilTooltip />} cursor={{ fill: 'rgba(255,255,255,0.03)' }} />
                <Bar dataKey="utilization" radius={[4, 4, 0, 0]} maxBarSize={60}>
                  {chartData.map((entry, idx) => (
                    <Cell key={idx} fill={getUtilColor(entry.utilization)} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Per-GPU Stats */}
          <div className="grid grid-cols-2 gap-3">
            {devices.map((gpu, idx) => (
              <GpuStatCard key={gpu.device_index ?? idx} gpu={gpu} index={gpu.device_index ?? idx} />
            ))}
          </div>
        </>
      )}

      {/* Empty State */}
      {!isLoading && devices.length === 0 && !error && (
        <div className="text-center py-8">
          <Cpu size={32} className="mx-auto text-gray-600 mb-2" />
          <p className="text-sm text-gray-500">No GPU devices detected</p>
        </div>
      )}
    </div>
  );
}
