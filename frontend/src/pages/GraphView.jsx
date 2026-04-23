import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { SearchBar } from '../components/SearchBar';
import { LineageGraph } from '../components/LineageGraph';
import { NodeSidePanel } from '../components/NodeSidePanel';
import { RunsPanel } from '../components/RunsPanel';
import { getUpstream, getDownstream } from '../api/lineageApi';
import { AlertCircle, Hexagon, RefreshCw } from 'lucide-react';

// How often (ms) to silently re-fetch the graph while it's active and loading
const LIVE_POLL_INTERVAL_MS = 4000;

export const GraphView = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const [nodes, setNodes] = useState([]);
  const [edges, setEdges] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isPolling, setIsPolling] = useState(false);   // silent background refresh
  const [error, setError] = useState(null);
  const [activeNode, setActiveNode] = useState(null);
  const [activeJobRuns, setActiveJobRuns] = useState(null);

  // Keep track of current search so the poll knows what to re-fetch
  const activeSearch = useRef(null);
  const pollTimer = useRef(null);

  // ── Core fetch ──────────────────────────────────────────────────────────────
  const fetchGraph = useCallback(async (uri, depth, direction, silent = false) => {
    if (!silent) {
      setIsLoading(true);
      setError(null);
      setActiveNode(null);
      setActiveJobRuns(null);
    } else {
      setIsPolling(true);
    }

    activeSearch.current = { uri, depth, direction };

    // Sync URL params only on explicit (non-silent) searches
    if (!silent && searchParams.get('uri') !== uri) {
      setSearchParams({ uri, depth: String(depth), direction });
    }

    try {
      const data = direction === 'upstream'
        ? await getUpstream(uri, depth)
        : await getDownstream(uri, depth);

      setNodes(data.nodes || []);
      setEdges(data.edges || []);

      if (!silent && (!data.nodes || data.nodes.length === 0)) {
        setError('No lineage nodes found for this dataset yet.');
      } else {
        setError(null);
      }
    } catch (err) {
      if (!silent) {
        if (err.response?.status === 404) {
          setError(`Dataset not found: ${uri}`);
        } else {
          setError(`Error: ${err.message}`);
        }
        setNodes([]);
        setEdges([]);
      }
    } finally {
      if (!silent) setIsLoading(false);
      setIsPolling(false);
    }
  }, [searchParams, setSearchParams]);

  // ── Live polling: re-fetch every 4s whenever a search is active ─────────────
  useEffect(() => {
    clearInterval(pollTimer.current);
    if (activeSearch.current) {
      pollTimer.current = setInterval(() => {
        const s = activeSearch.current;
        if (s) fetchGraph(s.uri, s.depth, s.direction, true);
      }, LIVE_POLL_INTERVAL_MS);
    }
    return () => clearInterval(pollTimer.current);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes.length]); // restart poll when node count changes so we catch new arrivals

  // ── Deep-link: if URL has ?uri=… on mount, auto-search ──────────────────────
  useEffect(() => {
    const uri = searchParams.get('uri');
    if (uri && !activeSearch.current) {
      const depth = parseInt(searchParams.get('depth') || '5');
      const direction = searchParams.get('direction') || 'upstream';
      fetchGraph(uri, depth, direction);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSearch   = (uri, depth, direction) => fetchGraph(uri, depth, direction);
  const handleExplore  = (uri, direction)         => fetchGraph(uri, 5, direction);
  const runDefaultDemo = ()                        => fetchGraph('duckdb://jaffle_shop/raw_customers', 5, 'downstream');

  return (
    <div className="flex-1 w-full h-full relative flex flex-col">
      <SearchBar onSearch={handleSearch} isLoading={isLoading} initialValue={searchParams.get('uri') || ''} />

      {/* Live-poll indicator */}
      {isPolling && (
        <div className="absolute top-20 right-6 z-30 flex items-center gap-2 text-xs text-blue-300/70 bg-blue-900/30 border border-blue-500/20 px-3 py-1.5 rounded-full backdrop-blur">
          <RefreshCw size={12} className="animate-spin" />
          Live updating…
        </div>
      )}

      {/* Direction explanation banner — shown when a graph is active */}
      {nodes.length > 0 && (
        <div className="absolute top-20 left-1/2 -translate-x-1/2 z-20 flex gap-3 text-xs pointer-events-none">
          <span className="bg-black/60 border border-green-500/20 text-green-400/80 px-3 py-1 rounded-full backdrop-blur">
            ← <strong>Upstream</strong>: what <em>created</em> this data
          </span>
          <span className="bg-black/60 border border-orange-500/20 text-orange-400/80 px-3 py-1 rounded-full backdrop-blur">
            <strong>Downstream</strong> →: what this data <em>feeds into</em>
          </span>
        </div>
      )}

      <div className="flex-1 w-full h-full relative">
        {nodes.length > 0 ? (
          <LineageGraph nodes={nodes} edges={edges} onNodeClick={setActiveNode} />
        ) : !isLoading && !error && (
          <div className="absolute inset-0 flex flex-col items-center justify-center text-white/50 pointer-events-none">
            <Hexagon size={64} className="mb-4 opacity-50 text-blue-400" />
            <h1 className="text-3xl font-bold tracking-tight mb-2 text-white/80 pointer-events-auto">Graph Workbench</h1>
            <p className="max-w-md text-center text-sm pointer-events-auto">
              Enter a dataset URI above, then click <strong>Upstream</strong> or <strong>Downstream</strong> to explore.
            </p>
            <div className="pointer-events-auto mt-4 flex flex-col items-center gap-3 text-xs text-white/40 max-w-sm text-center">
              <div className="bg-white/5 border border-white/10 rounded-xl p-4 space-y-2 text-left">
                <p><strong className="text-green-400">Upstream</strong> — traces <em>backwards</em>: "What raw data and jobs created this dataset?"</p>
                <p><strong className="text-orange-400">Downstream</strong> — traces <em>forwards</em>: "Which jobs and reports depend on this dataset?"</p>
              </div>
            </div>
            <button
              onClick={runDefaultDemo}
              className="pointer-events-auto mt-6 bg-blue-600/20 hover:bg-blue-600/40 text-blue-300 px-6 py-2 rounded-full font-medium transition-all border border-blue-500/30 hover:shadow-[0_0_20px_rgba(59,130,246,0.2)]"
            >
              ▶ Try Simulator Default Pipeline
            </button>
          </div>
        )}

        {/* Full loading overlay (first fetch only) */}
        {isLoading && (
          <div className="absolute inset-0 z-40 bg-darkspace/60 backdrop-blur-sm flex items-center justify-center">
            <div className="flex flex-col items-center gap-4">
              <div className="w-12 h-12 rounded-full border-4 border-blue-500/30 border-t-blue-500 animate-spin" />
              <div className="text-blue-400 font-semibold tracking-widest text-sm uppercase">Traversing Graph…</div>
            </div>
          </div>
        )}

        {/* Error banner */}
        {error && (
          <div className="absolute top-28 left-1/2 -translate-x-1/2 z-50 bg-red-950/80 border border-red-500/50 text-red-200 px-6 py-4 rounded-xl shadow-2xl flex items-center gap-3 backdrop-blur-md max-w-xl">
            <AlertCircle size={24} className="text-red-400 flex-shrink-0" />
            <p className="text-sm">{error}</p>
          </div>
        )}

        {/* Side panels */}
        <NodeSidePanel
          node={activeNode}
          onClose={() => setActiveNode(null)}
          onExplore={handleExplore}
          onViewRuns={(jobName) => setActiveJobRuns(jobName)}
        />

        {activeJobRuns && (
          <RunsPanel jobName={activeJobRuns} onClose={() => setActiveJobRuns(null)} />
        )}
      </div>
    </div>
  );
};
