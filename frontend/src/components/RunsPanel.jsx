import React, { useEffect, useState } from 'react';
import { getRuns } from '../api/lineageApi';
import { X, Play, CheckCircle, XCircle, Clock } from 'lucide-react';
import { formatDistanceToNow, formatDistance } from 'date-fns';

export const RunsPanel = ({ jobName, onClose }) => {
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!jobName) return;
    
    let isMounted = true;
    setLoading(true);
    
    getRuns(jobName)
      .then((data) => {
        if (isMounted) {
          setRuns(data.runs || []);
          setError(null);
        }
      })
      .catch((err) => {
        if (isMounted) {
          setError(err.message || 'Failed to fetch runs');
          setRuns([]);
        }
      })
      .finally(() => {
        if (isMounted) setLoading(false);
      });
      
    return () => { isMounted = false; };
  }, [jobName]);

  return (
    <div className="absolute top-4 right-4 z-50 w-96 max-h-[90vh] glass-panel shadow-2xl flex flex-col text-white transform transition-transform duration-300">
      <div className="px-5 py-4 border-b border-white/10 flex items-center justify-between bg-white/5 rounded-t-xl">
        <h2 className="font-semibold text-lg flex items-center gap-2">
          <Play size={18} className="text-orange-400"/>
          Run History
        </h2>
        <button onClick={onClose} className="p-1 hover:bg-white/10 rounded-md transition-colors">
          <X size={18} />
        </button>
      </div>

      <div className="px-5 py-3 border-b border-white/10 text-xs text-gray-400 bg-black/20">
        Job: <span className="text-white font-mono">{jobName}</span>
      </div>

      <div className="flex-1 overflow-y-auto p-2">
        {loading && (
          <div className="p-8 text-center text-gray-400 animate-pulse">Loading runs...</div>
        )}
        
        {error && (
          <div className="p-4 m-2 bg-red-900/40 border border-red-500/30 rounded-lg text-red-200 text-sm">
            {error}
          </div>
        )}
        
        {!loading && !error && runs.length === 0 && (
          <div className="p-8 text-center text-gray-500 text-sm">
            No runs recorded for this job yet.
          </div>
        )}

        {!loading && !error && runs.length > 0 && (
          <div className="flex flex-col gap-2">
            {runs.map((run, idx) => {
              const isSuccess = run.status === 'COMPLETE';
              const isFail = run.status === 'FAIL';
              
              let duration = 'N/A';
              if (run.start_time && run.end_time) {
                duration = formatDistance(new Date(run.end_time), new Date(run.start_time));
              }

              return (
                <div key={idx} className="bg-black/30 border border-white/5 rounded-lg p-3 hover:bg-black/50 transition-colors">
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-mono text-xs text-gray-400 truncate w-32" title={run.run_id}>
                      {run.run_id.split('-')[0]}...
                    </span>
                    <span className={`flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold tracking-wider ${
                      isSuccess ? 'bg-green-500/20 text-green-400 border border-green-500/30' : 
                      isFail ? 'bg-red-500/20 text-red-400 border border-red-500/30' : 
                      'bg-yellow-500/20 text-yellow-400 border border-yellow-500/30'
                    }`}>
                      {isSuccess ? <CheckCircle size={12}/> : isFail ? <XCircle size={12}/> : <Clock size={12}/>}
                      {run.status}
                    </span>
                  </div>
                  
                  <div className="text-xs text-gray-300 grid grid-cols-2 gap-y-1">
                    <div className="text-gray-500">Started:</div>
                    <div className="text-right">{run.start_time ? formatDistanceToNow(new Date(run.start_time), {addSuffix: true}) : 'Unknown'}</div>
                    <div className="text-gray-500">Duration:</div>
                    <div className="text-right font-mono text-[11px]">{duration}</div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
