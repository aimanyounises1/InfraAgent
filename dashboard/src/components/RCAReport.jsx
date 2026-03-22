import React, { useState } from 'react';
import {
  ChevronDown,
  ChevronRight,
  FileText,
  Clock,
  Search,
  Shield,
  Wrench,
  AlertTriangle,
} from 'lucide-react';

/**
 * CollapsibleSection -- A section header that expands/collapses its content on click.
 *
 * @param {{ title: string, icon: React.ComponentType, defaultOpen?: boolean, children: React.ReactNode }} props
 */
function CollapsibleSection({ title, icon: Icon, defaultOpen = false, children }) {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  return (
    <div className="border border-gray-800 rounded-lg overflow-hidden">
      <button
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        className="w-full flex items-center gap-2 px-4 py-3 bg-bg-tertiary hover:bg-gray-800/60 transition-colors text-left"
      >
        {isOpen ? (
          <ChevronDown size={14} className="text-gray-400 shrink-0" />
        ) : (
          <ChevronRight size={14} className="text-gray-400 shrink-0" />
        )}
        <Icon size={14} className="text-accent-blue shrink-0" />
        <span className="text-sm font-display font-medium text-white">{title}</span>
      </button>
      {isOpen && (
        <div className="px-4 py-3 bg-bg-secondary text-sm text-gray-300">
          {children}
        </div>
      )}
    </div>
  );
}

/**
 * Parse the Markdown RCA report into structured sections.
 *
 * The RCA tool generates a Markdown report with known headings.
 * This parser extracts content under each heading for structured display.
 *
 * @param {string} markdown - Raw Markdown RCA report.
 * @returns {object} Parsed sections.
 */
function parseRCAReport(markdown) {
  if (!markdown || typeof markdown !== 'string') {
    return null;
  }

  const sections = {
    summary: '',
    timeline: [],
    rootCause: '',
    impact: [],
    remediation: [],
    prevention: [],
  };

  // Extract summary section
  const summaryMatch = markdown.match(/## Summary\s*\n([\s\S]*?)(?=\n---|\n## )/);
  if (summaryMatch) {
    sections.summary = summaryMatch[1].trim();
  }

  // Extract timeline (from the Investigation section table, or Timeline of Events)
  const timelineMatch = markdown.match(/### Timeline of Events\s*\n([\s\S]*?)(?=\n---|\n## |\n### )/);
  if (timelineMatch) {
    const rows = timelineMatch[1].split('\n').filter((line) => line.startsWith('|') && !line.includes('---'));
    // Skip header row
    const dataRows = rows.slice(1);
    sections.timeline = dataRows.map((row) => {
      const cells = row.split('|').map((c) => c.trim()).filter(Boolean);
      return { time: cells[0] || '', event: cells[1] || '' };
    });
  }

  // Extract root cause section
  const rootCauseMatch = markdown.match(/## Root Cause\s*\n([\s\S]*?)(?=\n---|\n## )/);
  if (rootCauseMatch) {
    sections.rootCause = rootCauseMatch[1].trim();
  }

  // Extract impact assessment
  const impactMatch = markdown.match(/## Impact Assessment\s*\n([\s\S]*?)(?=\n---|\n## )/);
  if (impactMatch) {
    // Extract table rows as impact items
    const impactLines = impactMatch[1].split('\n').filter((line) => line.startsWith('|') && !line.includes('---'));
    const dataRows = impactLines.slice(1); // Skip header
    sections.impact = dataRows.map((row) => {
      const cells = row.split('|').map((c) => c.trim()).filter(Boolean);
      return { dimension: (cells[0] || '').replace(/\*\*/g, ''), assessment: (cells[1] || '').replace(/\*\*/g, '') };
    });
  }

  // Extract remediation steps
  const remediationMatch = markdown.match(/## Remediation Steps\s*\n([\s\S]*?)(?=\n---|\n## )/);
  if (remediationMatch) {
    // Extract numbered items and sub-items
    const lines = remediationMatch[1].split('\n').filter((l) => l.trim());
    sections.remediation = lines.map((l) => l.replace(/^\d+\.\s*/, '').replace(/^\s*-\s*/, '  - ').trim());
  }

  // Extract prevention section
  const preventionMatch = markdown.match(/## Prevention\s*\n([\s\S]*?)(?=\n---|\n\*|$)/);
  if (preventionMatch) {
    const lines = preventionMatch[1].split('\n').filter((l) => l.trim().startsWith('-'));
    sections.prevention = lines.map((l) => l.replace(/^-\s*/, '').replace(/\*\*/g, '').trim());
  }

  return sections;
}

/**
 * RCAReport -- Formatted auto-generated Root Cause Analysis display.
 *
 * Accepts RCA data either as:
 * - A Markdown string (from the incident_generate_rca tool)
 * - A structured object with { summary, timeline, root_cause, impact, remediation, prevention }
 *
 * @param {{ rcaData?: string | object }} props
 */
export default function RCAReport({ rcaData = null }) {
  // Parse the RCA data
  let sections = null;

  if (typeof rcaData === 'string' && rcaData.trim().length > 0) {
    sections = parseRCAReport(rcaData);
  } else if (rcaData && typeof rcaData === 'object') {
    // Structured RCA data object
    sections = {
      summary: rcaData.summary || '',
      timeline: Array.isArray(rcaData.timeline) ? rcaData.timeline : [],
      rootCause: rcaData.root_cause || rcaData.rootCause || '',
      impact: Array.isArray(rcaData.impact) ? rcaData.impact : [],
      remediation: Array.isArray(rcaData.remediation) ? rcaData.remediation : [],
      prevention: Array.isArray(rcaData.prevention) ? rcaData.prevention : [],
    };
  }

  const hasContent = sections && (
    sections.summary ||
    sections.timeline.length > 0 ||
    sections.rootCause ||
    sections.impact.length > 0 ||
    sections.remediation.length > 0 ||
    sections.prevention.length > 0
  );

  return (
    <div className="bg-bg-secondary rounded-lg border border-gray-800 p-6">
      <h2 className="text-lg font-display font-semibold text-white mb-4">
        Root Cause Analysis
      </h2>

      {/* Empty State */}
      {!hasContent && (
        <div className="text-center py-8">
          <FileText size={32} className="mx-auto text-gray-600 mb-2" />
          <p className="text-sm text-gray-500">No RCA reports generated yet</p>
          <p className="text-xs text-gray-600 mt-1">
            RCA reports will appear here when incidents are analyzed
          </p>
        </div>
      )}

      {/* Structured RCA Content */}
      {hasContent && (
        <div className="space-y-3">
          {/* Summary */}
          {sections.summary && (
            <CollapsibleSection title="Summary" icon={FileText} defaultOpen={true}>
              <div className="bg-accent-blue/5 border border-accent-blue/20 rounded-md p-3">
                <p className="text-sm text-gray-200 leading-relaxed whitespace-pre-wrap">
                  {sections.summary}
                </p>
              </div>
            </CollapsibleSection>
          )}

          {/* Timeline */}
          {sections.timeline.length > 0 && (
            <CollapsibleSection title="Timeline" icon={Clock} defaultOpen={false}>
              <ol className="space-y-2">
                {sections.timeline.map((entry, idx) => (
                  <li key={idx} className="flex items-start gap-3">
                    <span className="text-xs font-mono text-accent-blue bg-accent-blue/10 px-2 py-0.5 rounded shrink-0">
                      {entry.time || entry.timestamp || `#${idx + 1}`}
                    </span>
                    <span className="text-sm text-gray-300">
                      {entry.event || entry.description || String(entry)}
                    </span>
                  </li>
                ))}
              </ol>
            </CollapsibleSection>
          )}

          {/* Root Cause */}
          {sections.rootCause && (
            <CollapsibleSection title="Root Cause" icon={Search} defaultOpen={true}>
              <div className="bg-accent-red/5 border border-accent-red/20 rounded-md p-3">
                <p className="text-sm text-gray-200 leading-relaxed whitespace-pre-wrap font-medium">
                  {sections.rootCause}
                </p>
              </div>
            </CollapsibleSection>
          )}

          {/* Impact */}
          {sections.impact.length > 0 && (
            <CollapsibleSection title="Impact Assessment" icon={AlertTriangle} defaultOpen={false}>
              <ul className="space-y-1.5">
                {sections.impact.map((item, idx) => (
                  <li key={idx} className="flex items-start gap-2 text-sm">
                    <span className="text-accent-amber mt-0.5 shrink-0">-</span>
                    <span className="text-gray-300">
                      {typeof item === 'string'
                        ? item
                        : `${item.dimension}: ${item.assessment}`}
                    </span>
                  </li>
                ))}
              </ul>
            </CollapsibleSection>
          )}

          {/* Remediation Steps */}
          {sections.remediation.length > 0 && (
            <CollapsibleSection title="Remediation Steps" icon={Wrench} defaultOpen={false}>
              <ol className="space-y-1.5 list-decimal list-inside">
                {sections.remediation.map((step, idx) => (
                  <li key={idx} className="text-sm text-gray-300 leading-relaxed">
                    {step}
                  </li>
                ))}
              </ol>
            </CollapsibleSection>
          )}

          {/* Prevention */}
          {sections.prevention.length > 0 && (
            <CollapsibleSection title="Prevention" icon={Shield} defaultOpen={false}>
              <ul className="space-y-1.5">
                {sections.prevention.map((item, idx) => (
                  <li key={idx} className="flex items-start gap-2 text-sm">
                    <span className="text-accent-green mt-0.5 shrink-0">-</span>
                    <span className="text-gray-300">{item}</span>
                  </li>
                ))}
              </ul>
            </CollapsibleSection>
          )}
        </div>
      )}
    </div>
  );
}
