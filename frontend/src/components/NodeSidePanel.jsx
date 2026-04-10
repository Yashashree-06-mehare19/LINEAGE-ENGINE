import React from 'react';
import { X, ExternalLink, Box, Activity, Database, Key } from 'lucide-react';

export const NodeSidePanel = ({ node, onClose, onExplore, onViewRuns }) => {
  if (!node) return null;

  const isDataset = node.label === 'Dataset';
  const data = node.properties || {};

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

        </div>
      </div>

      {/* Actions Footer */}
      <div className="px-5 py-4 border-t border-white/10 bg-black/20 rounded-b-xl flex flex-col gap-2">
        {isDataset ? (
           <>
             <button 
               onClick={() => onExplore(node.id, 'upstream')}
               className="w-full flex items-center justify-center gap-2 py-2 bg-blue-500/20 hover:bg-blue-500/30 text-blue-300 rounded-lg text-sm font-semibold transition-colors border border-blue-500/30"
             >
               <ExternalLink size={16} className="-scale-x-100" />
               Explore Upstream
             </button>
             <button 
               onClick={() => onExplore(node.id, 'downstream')}
               className="w-full flex items-center justify-center gap-2 py-2 bg-indigo-500/20 hover:bg-indigo-500/30 text-indigo-300 rounded-lg text-sm font-semibold transition-colors border border-indigo-500/30"
             >
               Explore Downstream
               <ExternalLink size={16} />
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

    </div>
  );
};
