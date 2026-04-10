import React, { useState } from 'react';
import { Search, ArrowUp, ArrowDown, Layers } from 'lucide-react';

export const SearchBar = ({ onSearch, isLoading }) => {
  const [uri, setUri] = useState('postgres://prod:5432/reporting.order_summary');
  const [depth, setDepth] = useState(5);

  const handleUpstream = (e) => {
    e.preventDefault();
    if (uri) onSearch(uri, depth, 'upstream');
  };

  const handleDownstream = (e) => {
    e.preventDefault();
    if (uri) onSearch(uri, depth, 'downstream');
  };

  return (
    <div className="absolute top-4 left-1/2 -translate-x-1/2 z-50 w-full max-w-2xl px-4">
      <div className="glass-panel p-3 flex flex-col gap-3 shadow-2xl">
        <div className="flex gap-2 items-center">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={18} />
            <input
              type="text"
              value={uri}
              onChange={(e) => setUri(e.target.value)}
              placeholder="Enter Dataset URI (e.g. duckdb://jaffle_shop/raw_orders)"
              className="w-full bg-black/30 border border-white/10 rounded-lg py-2.5 pl-10 pr-4 text-sm text-white placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500/50 transition-all font-mono"
            />
          </div>
        </div>
        
        <div className="flex items-center justify-between gap-4 px-1">
          <div className="flex items-center gap-3 bg-black/20 px-3 py-1.5 rounded-lg border border-white/5">
            <Layers size={16} className="text-gray-400" />
            <span className="text-xs text-gray-400 font-semibold uppercase tracking-wider">Hops</span>
            <input 
              type="range" 
              min="1" 
              max="10" 
              value={depth} 
              onChange={(e) => setDepth(Number(e.target.value))}
              className="w-24 accent-blue-500"
            />
            <span className="text-white text-sm font-bold min-w-[20px] text-center">{depth}</span>
          </div>

          <div className="flex gap-2">
            <button
              onClick={handleUpstream}
              disabled={isLoading || !uri}
              className="flex items-center gap-2 bg-white/10 hover:bg-white/20 disabled:opacity-50 text-white px-4 py-1.5 rounded-lg text-sm font-semibold transition-colors border border-white/10"
            >
              <ArrowUp size={16} className="-rotate-45" />
              Upstream
            </button>
            <button
              onClick={handleDownstream}
              disabled={isLoading || !uri}
              className="flex items-center gap-2 bg-blue-600/80 hover:bg-blue-500 text-white px-4 py-1.5 rounded-lg text-sm font-semibold transition-colors shadow-[0_0_15px_rgba(37,99,235,0.4)]"
            >
              <ArrowDown size={16} className="rotate-45" />
              Downstream
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
