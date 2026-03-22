import React, { useState, useEffect } from 'react';
import ClusterStatus from './components/ClusterStatus';
import GPUHeatmap from './components/GPUHeatmap';
import IncidentTimeline from './components/IncidentTimeline';
import NaturalLanguageInput from './components/NaturalLanguageInput';
import RCAReport from './components/RCAReport';

/**
 * App -- Root layout for the InfraAgent dashboard.
 *
 * Arranges ClusterStatus, GPUHeatmap, IncidentTimeline, and RCAReport
 * in a responsive grid with the NaturalLanguageInput fixed at the bottom.
 * Adds bottom padding to ensure content is not hidden behind the input bar.
 */
export default function App() {
  const [rcaData, setRcaData] = useState(null);

  // Listen for RCA data broadcast over the page (from NL chat or WebSocket).
  // Components can dispatch a custom event with RCA payload.
  useEffect(() => {
    /** @param {CustomEvent} e */
    function handleRCA(e) {
      if (e.detail) {
        setRcaData(e.detail);
      }
    }

    window.addEventListener('infra-agent:rca', handleRCA);
    return () => window.removeEventListener('infra-agent:rca', handleRCA);
  }, []);

  return (
    <div className="min-h-screen bg-bg-primary p-6 pb-32">
      {/* Header */}
      <header className="mb-8">
        <h1 className="text-3xl font-display font-bold text-white">
          Infra<span className="text-accent-green">Agent</span>
        </h1>
        <p className="text-gray-400 mt-1 font-mono text-sm">
          Agentic AI Platform for Infrastructure Operations
        </p>
      </header>

      {/* Dashboard Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        <ClusterStatus />
        <GPUHeatmap />
        <IncidentTimeline />
        <RCAReport rcaData={rcaData} />
      </div>

      {/* Natural Language Input (fixed bottom) */}
      <NaturalLanguageInput />
    </div>
  );
}
