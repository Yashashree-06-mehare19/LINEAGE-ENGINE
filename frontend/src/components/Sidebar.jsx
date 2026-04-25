import React, { useState } from 'react';
import { NavLink } from 'react-router-dom';
import { Network, Database, Activity, Hexagon, ShieldAlert, Loader2, Check } from 'lucide-react';
import { clsx } from 'clsx';
import { propagatePii } from '../api/lineageApi';

export const Sidebar = () => {
  const [isPropagating, setIsPropagating] = useState(false);
  const [propagateResult, setPropagateResult] = useState(null);

  const links = [
    { to: '/', label: 'Lineage Map', icon: Network },
    { to: '/directory', label: 'Dataset Directory', icon: Database },
    { to: '/system-runs', label: 'Global Pipeline Runs', icon: Activity },
  ];

  const handlePropagatePii = async () => {
    setIsPropagating(true);
    setPropagateResult(null);
    try {
      const res = await propagatePii();
      setPropagateResult({ success: true, count: res.datasets_updated });
      setTimeout(() => setPropagateResult(null), 5000);
    } catch (e) {
      console.error(e);
      setPropagateResult({ success: false });
      setTimeout(() => setPropagateResult(null), 5000);
    } finally {
      setIsPropagating(false);
    }
  };

  return (
    <aside className="w-64 h-full bg-darkglass backdrop-blur-xl border-r border-white/10 flex flex-col z-50">
      <div className="p-6 flex items-center gap-3 border-b border-white/10">
        <div className="w-10 h-10 rounded-lg shadow-lg bg-blue-600/20 border border-blue-500/50 flex items-center justify-center">
          <Hexagon className="text-blue-400" size={24} />
        </div>
        <h1 className="text-xl font-bold tracking-tight text-white/90">Lineage</h1>
      </div>

      <nav className="flex-1 p-4 flex flex-col gap-2">
        {links.map((link) => {
          const Icon = link.icon;
          return (
            <NavLink
              key={link.to}
              to={link.to}
              className={({ isActive }) => clsx(
                "flex items-center gap-3 px-4 py-3 rounded-lg transition-all duration-300",
                isActive 
                  ? "bg-blue-600/20 text-blue-400 border border-blue-500/30 shadow-[0_0_15px_rgba(59,130,246,0.15)]" 
                  : "text-white/60 hover:text-white/90 hover:bg-white/5 border border-transparent"
              )}
            >
              <Icon size={20} />
              <span className="font-medium text-sm">{link.label}</span>
            </NavLink>
          );
        })}
      </nav>

      <div className="p-4 border-t border-white/10 space-y-4">
        <div className="px-4 py-3 bg-red-500/10 rounded-lg border border-red-500/20">
          <p className="text-[10px] text-red-400/80 uppercase font-bold tracking-widest flex items-center gap-1 mb-2">
            <ShieldAlert size={12} /> Admin Tools
          </p>
          <button 
            onClick={handlePropagatePii}
            disabled={isPropagating}
            className="w-full flex justify-center items-center gap-2 py-1.5 px-3 bg-red-500/20 hover:bg-red-500/30 text-red-300 text-xs font-semibold rounded transition-colors disabled:opacity-50"
          >
            {isPropagating ? (
              <><Loader2 size={14} className="animate-spin" /> Propagating...</>
            ) : (
              "Propagate PII Tags"
            )}
          </button>
          {propagateResult && (
            <div className="mt-2 text-[10px] text-center">
              {propagateResult.success ? (
                <span className="text-green-400 flex items-center justify-center gap-1"><Check size={12}/> Updated {propagateResult.count} datasets</span>
              ) : (
                <span className="text-red-400">Failed to propagate</span>
              )}
            </div>
          )}
        </div>

        <div className="px-4 py-3 bg-white/5 rounded-lg border border-white/5">
          <p className="text-[10px] text-white/40 uppercase font-bold tracking-widest mb-1">Status</p>
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.6)]"></span>
            <span className="text-sm font-medium text-green-400">Live Streaming</span>
          </div>
        </div>
      </div>
    </aside>
  );
};
