import React, { useState } from 'react';
import { SearchBar } from './components/SearchBar';
import { LineageGraph } from './components/LineageGraph';
import { NodeSidePanel } from './components/NodeSidePanel';
import { RunsPanel } from './components/RunsPanel';
import { getUpstream, getDownstream } from './api/lineageApi';
import { AlertCircle, Hexagon } from 'lucide-react';

function App() {
  const [nodes, setNodes] = useState([]);
  const [edges, setEdges] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  
  const [activeNode, setActiveNode] = useState(null);
  const [activeJobRuns, setActiveJobRuns] = useState(null);

  const fetchGraph = async (uri, depth, direction) => {
    setIsLoading(true);
    setError(null);
    setActiveNode(null);
    setActiveJobRuns(null);

    try {
      const data = direction === 'upstream' 
        ? await getUpstream(uri, depth)
        : await getDownstream(uri, depth);

      setNodes(data.nodes || []);
      setEdges(data.edges || []);
      
      if (!data.nodes || data.nodes.length === 0) {
        setError("Warning: No graph nodes returned. Dataset may exist but have no lineage.");
      }
    } catch (err) {
      if (err.response?.status === 404) {
        setError(`Dataset not found: ${uri}`);
      } else {
        setError(`Error fetching lineage: ${err.message}`);
      }
      setNodes([]);
      setEdges([]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSearch = (uri, depth, direction) => {
    fetchGraph(uri, depth, direction);
  };

  const handleExplore = (datasetUri, direction) => {
    // Retain depth roughly 5 as default for deep exploration
    fetchGraph(datasetUri, 5, direction);
  };

  return (
    <div className="w-screen h-screen flex flex-col relative overflow-hidden bg-darkspace">
      <SearchBar onSearch={handleSearch} isLoading={isLoading} />

      {/* Main Graph Area */}
      <div className="flex-1 w-full h-full relative">
        {nodes.length > 0 ? (
          <LineageGraph 
            nodes={nodes} 
            edges={edges} 
            onNodeClick={setActiveNode} 
          />
        ) : !isLoading && !error && (
          <div className="absolute inset-0 flex flex-col items-center justify-center text-white/50 pointer-events-none">
            <Hexagon size={64} className="mb-4 opacity-50" />
            <h1 className="text-3xl font-bold tracking-tight mb-2 text-white/80">Lineage Engine</h1>
            <p className="max-w-md text-center text-sm">
              Map and explore your Data Workflows dynamically. Start by entering a dataset URI above and selecting an exploration direction.
            </p>
          </div>
        )}

        {/* Global Loading Overlay */}
        {isLoading && (
          <div className="absolute inset-0 z-40 bg-darkspace/50 backdrop-blur-sm flex items-center justify-center">
            <div className="flex flex-col items-center gap-4">
              <div className="w-12 h-12 rounded-full border-4 border-blue-500/30 border-t-blue-500 animate-spin"></div>
              <div className="text-blue-400 font-semibold tracking-widest text-sm uppercase">Calculating Traversal...</div>
            </div>
          </div>
        )}

        {/* Global Error Popover */}
        {error && (
          <div className="absolute top-24 left-1/2 -translate-x-1/2 z-50 bg-red-950/80 border border-red-500/50 text-red-200 px-6 py-4 rounded-xl shadow-2xl flex items-center gap-3 backdrop-blur-md max-w-xl">
            <AlertCircle size={24} className="text-red-400 flex-shrink-0" />
            <p className="text-sm">{error}</p>
          </div>
        )}

        {/* Side Panels */}
        <NodeSidePanel 
          node={activeNode} 
          onClose={() => setActiveNode(null)} 
          onExplore={handleExplore}
          onViewRuns={(jobName) => setActiveJobRuns(jobName)}
        />

        {activeJobRuns && (
          <RunsPanel 
            jobName={activeJobRuns} 
            onClose={() => setActiveJobRuns(null)} 
          />
        )}
      </div>
    </div>
  );
}

export default App;
