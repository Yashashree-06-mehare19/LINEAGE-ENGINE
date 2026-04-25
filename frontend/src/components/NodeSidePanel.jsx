import React, { useState, useEffect } from 'react';
import { X, ExternalLink, Box, Activity, Database, Key, AlertTriangle, Loader2, Columns } from 'lucide-react';
import { getImpact } from '../api/lineageApi';
import { ColumnPanel } from './ColumnPanel';

export const NodeSidePanel = ({ node, onClose, onExplore, onViewRuns }) => {
  const [impactData, setImpactData]   = useState(null);
  const [loadingImpact, setLoadingImpact] = useState(false);
  const [showColumns, setShowColumns] = useState(false);  // Stage 10

  // Reset impact data and column panel when the node changes
  useEffect(() => {
    setImpactData(null);
    setLoadingImpact(false);
    setShowColumns(false);
  }, [node]);

  if (!node) return null;

  const isDataset = node.label === 'Dataset';
  const data = node.properties || {};

  const handleCalculateImpact = async () => {
    setLoadingImpact(true);
    try {
      const result = await getImpact(data.uri);
      setImpactData(result);
    } catch (e) {
      console.error("Failed to calculate impact", e);
      setImpactData({ error: "Failed to calculate impact. Ensure backend is running." });
    } finally {
      setLoadingImpact(false);
    }
  };

  return (
    <div className="absolute top-4 left-4 z-50 w-80 max-h-[90vh] glass-panel shadow-2xl flex flex-col text-white transform transition-transform duration-300">
      <div className="px-5 py-4 border-b border-white/10 flex items-center justify-between">
        <h2 className="font-semibold text-lg flex items-center gap-2">
          {isDataset ? <Database size={18} className="text-blue-400"/> : <Activity size={18} className="text-orange-400"/>}
          {isDataset ? 'Dataset Details' : 'Job Details'}
        </h2>
        <button onClick={onClose} className="p-1 hover:bg-white/10 rounded-md transition-colors">
          <X size={18} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-5 scrollbar-thin">
        <div className="space-y-6">
          
          {/* Identity Section */}
          <div>
            <h3 className="text-[10px] uppercase font-bold text-gray-500 tracking-wider mb-2">Display Name</h3>
            <div className="font-mono text-sm break-all font-medium text-white/90">
              {data.name || 'Unknown'}
            </div>
            {isDataset && data.tags && data.tags.includes('pii') && (
              <div className="mt-2 inline-flex items-center gap-1.5 px-2 py-1 rounded bg-red-500/20 text-red-400 border border-red-500/30 text-xs font-bold uppercase">
                <Key size={12} /> Contains PII
              </div>
            )}
          </div>

          {/* Properties Section */}
          <div>
            <h3 className="text-[10px] uppercase font-bold text-gray-500 tracking-wider mb-2 flex items-center gap-1">
              <Box size={14} /> Properties
            </h3>
            <div className="space-y-3 bg-black/20 p-3 rounded-lg border border-white/5">
              {Object.entries(data).map(([key, value]) => {
                if (key === 'tags' && Array.isArray(value)) {
                  return (
                    <div key={key}>
                      <div className="text-xs text-gray-500 capitalize">{key}</div>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {value.length === 0 ? <span className="text-xs text-gray-600">None</span> : 
                          value.map(t => (
                            <span key={t} className="px-1.5 py-0.5 rounded bg-white/10 text-xs text-gray-300">{t}</span>
                          ))
                        }
                      </div>
                    </div>
                  );
                }
                
                return (
                  <div key={key} className="break-all">
                    <div className="text-xs text-gray-500 capitalize">{key.replace('_', ' ')}</div>
                    <div className="text-sm font-mono text-gray-200">{String(value || '—')}</div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Impact Analysis Section */}
          {isDataset && (
            <div>
              <h3 className="text-[10px] uppercase font-bold text-gray-500 tracking-wider mb-2 flex items-center gap-1">
                <AlertTriangle size={14} /> Impact Analysis
              </h3>
              {!impactData && !loadingImpact && (
                <button 
                  onClick={handleCalculateImpact}
                  className="w-full flex items-center justify-center gap-2 py-1.5 bg-red-500/10 hover:bg-red-500/20 text-red-300 rounded text-xs font-semibold transition-colors border border-red-500/30"
                >
                  Calculate Downstream Impact
                </button>
              )}
              
              {loadingImpact && (
                <div className="flex items-center justify-center p-3 text-red-300/70 text-xs gap-2">
                  <Loader2 size={14} className="animate-spin" /> Calculating...
                </div>
              )}

              {impactData && !impactData.error && (
                <div className="bg-red-950/40 p-3 rounded-lg border border-red-500/20 space-y-2">
                  <div className="text-xs text-red-200 flex justify-between items-center border-b border-red-500/20 pb-1 mb-2">
                    <span className="font-bold uppercase tracking-wider">Impact Score</span>
                    <span className="bg-red-500 text-white font-bold px-2 py-0.5 rounded-full">{impactData.impact_score}</span>
                  </div>
                  
                  {impactData.impact_score === 0 ? (
                    <div className="text-xs text-green-400 font-medium">Safe to change! No downstream dependencies.</div>
                  ) : (
                    <>
                      <div>
                        <div className="text-[10px] uppercase text-red-300/70 font-semibold mb-1">Affected Jobs ({impactData.affected_jobs?.length || 0})</div>
                        <div className="text-xs font-mono text-red-200 truncate">{impactData.affected_jobs?.join(', ') || 'None'}</div>
                      </div>
                      <div>
                        <div className="text-[10px] uppercase text-red-300/70 font-semibold mb-1">Affected Datasets ({impactData.affected_datasets?.length || 0})</div>
                        <div className="text-xs font-mono text-red-200 truncate">{impactData.affected_datasets?.map(u => u.split('//').pop()).join(', ') || 'None'}</div>
                      </div>
                    </>
                  )}
                </div>
              )}
              
              {impactData?.error && (
                <div className="text-xs text-red-400 p-2 bg-red-900/30 rounded border border-red-500/30">
                  {impactData.error}
                </div>
              )}
            </div>
          )}

        </div>
      </div>

      {/* Actions Footer */}
      <div className="px-5 py-4 border-t border-white/10 bg-black/20 rounded-b-xl flex flex-col gap-2">
        {isDataset ? (
           <>
             <button 
               onClick={() => onExplore(data.uri, 'upstream')}
               className="w-full flex items-center justify-center gap-2 py-2 bg-blue-500/20 hover:bg-blue-500/30 text-blue-300 rounded-lg text-sm font-semibold transition-colors border border-blue-500/30"
             >
               <ExternalLink size={16} className="-scale-x-100" />
               Explore Upstream
             </button>
             <button 
               onClick={() => onExplore(data.uri, 'downstream')}
               className="w-full flex items-center justify-center gap-2 py-2 bg-indigo-500/20 hover:bg-indigo-500/30 text-indigo-300 rounded-lg text-sm font-semibold transition-colors border border-indigo-500/30"
             >
               Explore Downstream
               <ExternalLink size={16} />
             </button>
             {/* Stage 10: Column Lineage button */}
             <button
               onClick={() => setShowColumns(prev => !prev)}
               className={`w-full flex items-center justify-center gap-2 py-2 rounded-lg text-sm font-semibold transition-colors border ${
                 showColumns
                   ? 'bg-cyan-500/30 text-cyan-200 border-cyan-400/40'
                   : 'bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-300 border-cyan-500/30'
               }`}
             >
               <Columns size={16} />
               {showColumns ? 'Hide Column Lineage' : 'Column Lineage'}
             </button>
           </>
        ) : (
           <button 
             onClick={() => onViewRuns(data.name)}
             className="w-full flex items-center justify-center gap-2 py-2 bg-orange-500/20 hover:bg-orange-500/30 text-orange-300 rounded-lg text-sm font-semibold transition-colors border border-orange-500/30"
           >
             <Activity size={16} />
             View Run History
           </button>
        )}
      </div>

      {/* Stage 10: Column Panel — renders on the right side */}
      {showColumns && isDataset && (
        <ColumnPanel
          datasetUri={data.uri}
          onClose={() => setShowColumns(false)}
        />
      )}

    </div>
  );
};
