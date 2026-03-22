import React, { useState, useEffect } from 'react';
import ClusterStatus from './components/ClusterStatus';
import GPUHeatmap from './components/GPUHeatmap';
import IncidentTimeline from './components/IncidentTimeline';
import NaturalLanguageInput from './components/NaturalLanguageInput';
import RCAReport from './components/RCAReport';

/**
 * App -- Root layout for the InfraAgent dashboard.
 *
 * Two-column layout on large screens:
 *   - Left (flex-1): Dashboard panels in a 2x2 grid with header
 *   - Right (fixed 450px): Full-height chatbot panel
 *
 * On smaller screens the chat panel collapses below the dashboard.
 */
export default function App() {
  const [rcaData, setRcaData] = useState(null);

  // Listen for RCA data broadcast over the page (from NL chat or WebSocket).
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
    <div className="h-screen bg-bg-primary flex flex-col lg:flex-row overflow-hidden">
      {/* Left: Dashboard Panels */}
      <div className="flex-1 min-w-0 flex flex-col overflow-y-auto">
        {/* Header */}
        <header className="shrink-0 px-6 pt-6 pb-2">
          <h1 className="text-3xl font-display font-bold text-white">
            Infra<span className="text-accent-green">Agent</span>
          </h1>
          <p className="text-gray-400 mt-1 font-mono text-sm">
            Agentic AI Platform for Infrastructure Operations
          </p>
        </header>

        {/* Dashboard Grid */}
        <div className="flex-1 px-6 pb-6 pt-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <ClusterStatus />
            <GPUHeatmap />
            <IncidentTimeline />
            <RCAReport rcaData={rcaData} />
          </div>
        </div>
      </div>

      {/* Right: Chat Panel */}
      <div className="w-full lg:w-[450px] shrink-0 border-t lg:border-t-0 lg:border-l border-gray-800/80 flex flex-col bg-bg-secondary h-[50vh] lg:h-full">
        <NaturalLanguageInput />
      </div>
    </div>
  );
}
