import React from 'react';
import { Handle, Position } from 'reactflow';
import { Database, Activity } from 'lucide-react';
import clsx from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs) {
  return twMerge(clsx(inputs));
}

// React Flow needs standard handle wrapper setup for styling overrides
export const DatasetNode = ({ data, selected }) => {
  return (
    <div className={cn(
      "px-4 py-2 rounded-lg shadow-lg border-2 min-w-[180px] bg-[#1a2235]/90 backdrop-blur text-white flex flex-col justify-center",
      selected ? "border-blue-400 shadow-blue-500/50" : "border-blue-700/50"
    )}>
      <Handle type="target" position={Position.Left} className="w-2 h-4 bg-blue-400 rounded-sm border-none" />
      
      <div className="flex items-center gap-2 mb-1">
        <Database size={16} className="text-blue-400" />
        <span className="text-xs font-bold uppercase tracking-wider text-blue-300">Dataset</span>
        {data.tags && data.tags.includes('pii') && (
          <span className="ml-auto bg-red-500/20 text-red-400 text-[10px] px-1.5 py-0.5 rounded font-bold uppercase border border-red-500/30">PII</span>
        )}
      </div>
      
      <div className="font-semibold text-sm truncate" title={data.name}>
        {data.name}
      </div>
      <div className="text-[10px] text-gray-400 truncate opacity-80" title={data.namespace}>
        {data.namespace}
      </div>

      <Handle type="source" position={Position.Right} className="w-2 h-4 bg-blue-400 rounded-sm border-none" />
    </div>
  );
};

export const JobNode = ({ data, selected }) => {
  return (
    <div className={cn(
      "px-4 py-2 rounded-lg shadow-lg border-2 min-w-[180px] bg-[#2a1b14]/90 backdrop-blur text-white flex flex-col justify-center",
      selected ? "border-orange-400 shadow-orange-500/50" : "border-orange-700/50"
    )}>
      <Handle type="target" position={Position.Left} className="w-2 h-4 bg-orange-400 rounded-sm border-none" />
      
      <div className="flex items-center gap-2 mb-1">
        <Activity size={16} className="text-orange-400" />
        <span className="text-xs font-bold uppercase tracking-wider text-orange-300">Job</span>
      </div>
      
      <div className="font-semibold text-sm truncate" title={data.name}>
        {data.name}
      </div>
      <div className="text-[10px] text-gray-400 truncate opacity-80 uppercase" title={data.orchestrator}>
        {data.orchestrator || 'Airflow'}
      </div>

      <Handle type="source" position={Position.Right} className="w-2 h-4 bg-orange-400 rounded-sm border-none" />
    </div>
  );
};

export const nodeTypes = {
  Dataset: DatasetNode,
  Job: JobNode,
};
