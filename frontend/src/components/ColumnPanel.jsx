import React, { useState, useEffect } from 'react';
import { X, Columns, ArrowUpLeft, AlertTriangle, Loader2, ChevronRight } from 'lucide-react';
import { getDatasetColumns, getColumnUpstream, getColumnImpact } from '../api/lineageApi';

/**
 * Stage 10 — Column-Level Lineage Panel
 *
 * Shown when the user clicks "Column Lineage" on a Dataset node.
 * Displays all columns for the dataset and lets the user drill into
 * upstream sources or downstream impact for any individual column.
 */
export const ColumnPanel = ({ datasetUri, onClose }) => {
  const [columns, setColumns]         = useState([]);
  const [loading, setLoading]         = useState(true);
  const [error, setError]             = useState(null);
  const [selectedCol, setSelectedCol] = useState(null);  // { uri, name }
  const [traceMode, setTraceMode]     = useState(null);  // "upstream" | "impact"
  const [traceData, setTraceData]     = useState(null);
  const [traceLoading, setTraceLoading] = useState(false);

  // Load columns on mount / dataset change
  useEffect(() => {
    if (!datasetUri) return;
    setLoading(true);
    setError(null);
    setSelectedCol(null);
    setTraceData(null);
    getDatasetColumns(datasetUri)
      .then(data => setColumns(data.columns || []))
      .catch(() => setError('Failed to load columns. Has Stage 10 data been ingested?'))
      .finally(() => setLoading(false));
  }, [datasetUri]);

  // Fetch trace when user clicks a trace button
  useEffect(() => {
    if (!selectedCol || !traceMode) return;
    setTraceLoading(true);
    setTraceData(null);
    const fn = traceMode === 'upstream' ? getColumnUpstream : getColumnImpact;
    fn(selectedCol.uri)
      .then(data => setTraceData(data))
      .catch(() => setTraceData({ error: 'Trace failed.' }))
      .finally(() => setTraceLoading(false));
  }, [selectedCol, traceMode]);

  const handleTrace = (col, mode) => {
    if (selectedCol?.uri === col.uri && traceMode === mode) {
      // Toggle off
      setSelectedCol(null);
      setTraceMode(null);
    } else {
      setSelectedCol(col);
      setTraceMode(mode);
    }
  };

  const traceList = traceMode === 'upstream'
    ? (traceData?.upstream_columns || [])
    : (traceData?.impacted_columns || []);

  return (
    <div className="absolute top-4 right-4 z-50 w-96 max-h-[90vh] glass-panel shadow-2xl flex flex-col text-white">
      {/* Header */}
      <div className="px-5 py-4 border-b border-white/10 flex items-center justify-between flex-shrink-0">
        <h2 className="font-semibold text-lg flex items-center gap-2">
          <Columns size={18} className="text-cyan-400" />
          Column Lineage
        </h2>
        <button onClick={onClose} className="p-1 hover:bg-white/10 rounded-md transition-colors">
          <X size={18} />
        </button>
      </div>

      {/* Dataset URI badge */}
      <div className="px-5 py-2 border-b border-white/5 bg-black/20 flex-shrink-0">
        <div className="text-[10px] uppercase text-gray-500 font-bold tracking-wider mb-0.5">Dataset</div>
        <div className="text-xs font-mono text-cyan-300/80 break-all">{datasetUri}</div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {/* Loading state */}
        {loading && (
          <div className="flex items-center justify-center p-8 text-cyan-300/60 gap-2">
            <Loader2 size={16} className="animate-spin" /> Loading columns...
          </div>
        )}

        {/* Error state */}
        {error && (
          <div className="m-4 text-xs text-red-400 p-3 bg-red-900/30 rounded border border-red-500/30">
            {error}
          </div>
        )}

        {/* No columns */}
        {!loading && !error && columns.length === 0 && (
          <div className="p-5 text-center text-xs text-gray-500">
            <Columns size={32} className="mx-auto mb-2 opacity-30" />
            No column lineage data yet.<br />
            <span className="text-gray-600">Post events with a <code>columnLineage</code> facet to populate this.</span>
          </div>
        )}

        {/* Column list */}
        {!loading && columns.length > 0 && (
          <div className="p-4 space-y-2">
            <div className="text-[10px] uppercase text-gray-500 font-bold tracking-wider mb-3">
              {columns.length} Column{columns.length !== 1 ? 's' : ''}
            </div>
            {columns.map(col => {
              const isSelected = selectedCol?.uri === col.uri;
              return (
                <div
                  key={col.uri}
                  className={`rounded-lg border transition-all ${
                    isSelected
                      ? 'border-cyan-500/50 bg-cyan-900/20'
                      : 'border-white/5 bg-white/5'
                  }`}
                >
                  {/* Column name row */}
                  <div className="px-3 py-2 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <ChevronRight size={12} className="text-cyan-400/60" />
                      <span className="text-sm font-mono text-gray-100">{col.name}</span>
                    </div>
                    <div className="flex gap-1">
                      <button
                        title="Trace upstream sources of this column"
                        onClick={() => handleTrace(col, 'upstream')}
                        className={`px-2 py-0.5 rounded text-[10px] font-semibold transition-colors ${
                          isSelected && traceMode === 'upstream'
                            ? 'bg-blue-500/40 text-blue-200 border border-blue-400/40'
                            : 'bg-blue-500/10 hover:bg-blue-500/20 text-blue-300 border border-blue-500/20'
                        }`}
                      >
                        <ArrowUpLeft size={10} className="inline mr-0.5" />
                        Upstream
                      </button>
                      <button
                        title="See what this column impacts downstream"
                        onClick={() => handleTrace(col, 'impact')}
                        className={`px-2 py-0.5 rounded text-[10px] font-semibold transition-colors ${
                          isSelected && traceMode === 'impact'
                            ? 'bg-orange-500/40 text-orange-200 border border-orange-400/40'
                            : 'bg-orange-500/10 hover:bg-orange-500/20 text-orange-300 border border-orange-500/20'
                        }`}
                      >
                        <AlertTriangle size={10} className="inline mr-0.5" />
                        Impact
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Trace results panel */}
        {selectedCol && (
          <div className="mx-4 mb-4 rounded-xl border border-white/10 bg-black/30">
            <div className="px-4 py-3 border-b border-white/5">
              <div className="text-[10px] uppercase font-bold tracking-wider text-gray-400">
                {traceMode === 'upstream' ? '← Upstream Sources' : '→ Downstream Impact'}
              </div>
              <div className="text-xs font-mono text-cyan-300/70 mt-0.5">{selectedCol.name}</div>
            </div>

            {traceLoading && (
              <div className="flex items-center justify-center p-4 text-white/40 gap-2 text-xs">
                <Loader2 size={14} className="animate-spin" /> Tracing...
              </div>
            )}

            {traceData?.error && (
              <div className="p-3 text-xs text-red-400">{traceData.error}</div>
            )}

            {!traceLoading && traceData && !traceData.error && traceList.length === 0 && (
              <div className="p-4 text-xs text-gray-500 text-center">
                {traceMode === 'upstream'
                  ? 'No upstream sources found — this may be a source column.'
                  : 'No downstream impact — this is a leaf column.'}
              </div>
            )}

            {!traceLoading && traceList.length > 0 && (
              <div className="p-3 space-y-2">
                {traceMode === 'impact' && (
                  <div className="flex justify-between items-center text-[10px] text-orange-300/60 font-semibold mb-2">
                    <span>Impact Score</span>
                    <span className="bg-orange-500 text-white px-2 py-0.5 rounded-full font-bold">
                      {traceList.length}
                    </span>
                  </div>
                )}
                {traceList.map((entry, i) => (
                  <div key={i} className="bg-white/5 rounded-lg px-3 py-2 border border-white/5">
                    <div className="text-xs font-mono text-gray-100">{entry.name}</div>
                    <div className="text-[10px] text-gray-500 font-mono truncate">{entry.dataset_uri}</div>
                    {entry.via_job && (
                      <div className="text-[10px] text-orange-400/60 mt-0.5">
                        via <span className="font-semibold">{entry.via_job}</span>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
