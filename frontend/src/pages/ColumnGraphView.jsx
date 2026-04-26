import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import ReactFlow, { Background, Controls, MarkerType } from 'reactflow';
import 'reactflow/dist/style.css';
import dagre from 'dagre';
import { ArrowLeft, Loader2, Columns, AlertTriangle, Hexagon } from 'lucide-react';
import { getColumnUpstream, getColumnImpact, getDatasetColumns } from '../api/lineageApi';
import { ColumnNode } from '../components/ColumnNode';

const nodeTypes = { columnNode: ColumnNode };

export const ColumnGraphView = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const datasetUri = searchParams.get('dataset');
  const focalColUri = searchParams.get('col');
  const mode = searchParams.get('mode') || 'upstream'; // 'upstream' or 'impact'

  const [nodes, setNodes] = useState([]);
  const [edges, setEdges] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [datasetName, setDatasetName] = useState('');

  // 1. Fetch Data
  useEffect(() => {
    if (!datasetUri && !focalColUri) {
      setError('No dataset or column specified.');
      return;
    }

    let isMounted = true;
    setLoading(true);
    setError(null);

    const fetchData = async () => {
      try {
        let items = [];
        let edgesData = [];
        let currentDatasetName = '';

        if (focalColUri) {
          // Trace specific column
          const res = mode === 'upstream'
            ? await getColumnUpstream(focalColUri)
            : await getColumnImpact(focalColUri);

          const list = mode === 'upstream' ? res.upstream_columns : res.impacted_columns;
          
          // The focal column itself
          const focalName = focalColUri.split('/').pop();
          const focalDatasetUri = focalColUri.substring(0, focalColUri.lastIndexOf('/'));
          currentDatasetName = focalDatasetUri.split('//').pop();

          items.push({ uri: focalColUri, name: focalName, dataset_uri: focalDatasetUri, isFocal: true });

          list.forEach(item => {
            items.push({ uri: item.uri, name: item.name, dataset_uri: item.dataset_uri, isFocal: false });
            // Build edge depending on mode
            if (mode === 'upstream') {
              edgesData.push({ source: item.uri, target: focalColUri, label: item.via_job });
            } else {
              edgesData.push({ source: focalColUri, target: item.uri, label: item.via_job });
            }
          });
        } else if (datasetUri) {
          // Just list columns for a dataset
          const res = await getDatasetColumns(datasetUri);
          currentDatasetName = datasetUri.split('//').pop();
          res.columns.forEach(col => {
            items.push({ uri: col.uri, name: col.name, dataset_uri: datasetUri, isFocal: true });
          });
        }

        if (isMounted) {
          setDatasetName(currentDatasetName);
          buildGraph(items, edgesData);
        }
      } catch (err) {
        if (isMounted) {
          console.error(err);
          setError(err.message || 'Failed to load column lineage graph');
        }
      } finally {
        if (isMounted) setLoading(false);
      }
    };

    fetchData();
    return () => { isMounted = false; };
  }, [datasetUri, focalColUri, mode]);

  // 2. Build Layout with Dagre
  const buildGraph = (items, edgesData) => {
    if (items.length === 0) {
      setNodes([]);
      setEdges([]);
      return;
    }

    const g = new dagre.graphlib.Graph({ compound: true });
    g.setGraph({ rankdir: 'LR', align: 'UL', ranker: 'longest-path', nodesep: 30, ranksep: 200 });
    g.setDefaultEdgeLabel(() => ({}));

    // Generate unique colors for different datasets
    const datasets = [...new Set(items.map(i => i.dataset_uri))];
    const colors = ['#2563eb', '#16a34a', '#d97706', '#9333ea', '#db2777', '#0891b2', '#ea580c'];
    const dsColors = {};
    datasets.forEach((ds, i) => { dsColors[ds] = colors[i % colors.length]; });

    // Deduplicate nodes
    const uniqueItems = [];
    const seen = new Set();
    items.forEach(i => {
      if (!seen.has(i.uri)) {
        seen.add(i.uri);
        uniqueItems.push(i);
      }
    });

    // Create groups for datasets
    const reactFlowNodes = [];
    datasets.forEach(ds => {
      const dsName = ds.split('//').pop();
      reactFlowNodes.push({
        id: `group-${ds}`,
        type: 'group',
        data: { label: dsName },
        className: 'bg-black/40 border border-white/10 rounded-xl',
        style: { width: 220, padding: 20 },
        position: { x: 0, y: 0 } // dagre will set this
      });
      g.setNode(`group-${ds}`, { width: 220, height: 100 });
    });

    uniqueItems.forEach((item) => {
      g.setNode(item.uri, { width: 180, height: 40 });
      // Tell dagre that this node is inside a parent
      g.setParent(item.uri, `group-${item.dataset_uri}`);
      
      reactFlowNodes.push({
        id: item.uri,
        type: 'columnNode',
        data: { name: item.name, dataset_uri: item.dataset_uri, is_focal: item.isFocal },
        parentNode: `group-${item.dataset_uri}`,
        extent: 'parent',
        position: { x: 0, y: 0 }
      });
    });

    const reactFlowEdges = [];
    edgesData.forEach((edge, i) => {
      const edgeId = `${edge.source}->${edge.target}`;
      g.setEdge(edge.source, edge.target);
      reactFlowEdges.push({
        id: edgeId,
        source: edge.source,
        target: edge.target,
        animated: true,
        label: edge.label,
        labelStyle: { fill: '#cbd5e1', fontSize: 10, fontFamily: 'monospace' },
        labelBgStyle: { fill: '#0f172a', stroke: '#334155' },
        labelBgPadding: [4, 2],
        labelBgBorderRadius: 4,
        style: { stroke: '#475569', strokeWidth: 1.5 },
        markerEnd: { type: MarkerType.ArrowClosed, color: '#475569', width: 15, height: 15 }
      });
    });

    dagre.layout(g);

    // Apply layout
    const layoutedNodes = reactFlowNodes.map((node) => {
      if (node.type === 'group') {
        const dNode = g.node(node.id);
        node.position = { x: dNode.x - dNode.width / 2, y: dNode.y - dNode.height / 2 };
        node.style.width = dNode.width;
        node.style.height = dNode.height;
      } else {
        const dNode = g.node(node.id);
        const parentNode = g.node(`group-${node.data.dataset_uri}`);
        // React Flow parent-relative coordinates
        node.position = {
          x: dNode.x - parentNode.x + parentNode.width / 2 - dNode.width / 2,
          y: dNode.y - parentNode.y + parentNode.height / 2 - dNode.height / 2
        };
      }
      return node;
    });

    setNodes(layoutedNodes);
    setEdges(reactFlowEdges);
  };

  return (
    <div className="flex-1 w-full h-full relative flex flex-col bg-[#0b101e]">
      {/* Header */}
      <div className="absolute top-4 left-4 z-50 flex items-center gap-4 glass-panel px-4 py-2 shadow-xl">
        <button 
          onClick={() => navigate(-1)} 
          className="p-1.5 hover:bg-white/10 rounded-lg text-gray-300 hover:text-white transition-colors border border-transparent hover:border-white/10"
          title="Back to Dataset Graph"
        >
          <ArrowLeft size={18} />
        </button>
        <div className="h-6 w-px bg-white/10"></div>
        <div className="flex flex-col">
          <div className="flex items-center gap-2 text-sm font-semibold text-white">
            <Columns size={16} className="text-cyan-400" />
            Column Lineage Graph
          </div>
          <div className="text-[10px] text-gray-400 font-mono mt-0.5">
            {datasetName} {focalColUri && `> ${focalColUri.split('/').pop()}`}
          </div>
        </div>
      </div>

      <div className="flex-1 w-full h-full relative">
        {loading && (
          <div className="absolute inset-0 z-40 bg-darkspace/60 backdrop-blur-sm flex items-center justify-center">
            <div className="flex flex-col items-center gap-4">
              <div className="w-12 h-12 rounded-full border-4 border-cyan-500/30 border-t-cyan-500 animate-spin" />
              <div className="text-cyan-400 font-semibold tracking-widest text-sm uppercase">Mapping Columns…</div>
            </div>
          </div>
        )}

        {error && (
          <div className="absolute top-24 left-1/2 -translate-x-1/2 z-50 bg-red-950/80 border border-red-500/50 text-red-200 px-6 py-4 rounded-xl shadow-2xl flex items-center gap-3 backdrop-blur-md">
            <AlertTriangle size={24} className="text-red-400" />
            <p className="text-sm">{error}</p>
          </div>
        )}

        {!loading && !error && nodes.length === 0 && (
          <div className="absolute inset-0 flex flex-col items-center justify-center text-white/50">
            <Hexagon size={64} className="mb-4 opacity-30 text-cyan-400" />
            <h2 className="text-xl font-bold tracking-tight mb-2">No Column Data</h2>
            <p className="text-sm">There are no columns or transformations available for this request.</p>
          </div>
        )}

        {nodes.length > 0 && (
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            fitView
            fitViewOptions={{ padding: 0.2 }}
            minZoom={0.2}
            maxZoom={2}
            proOptions={{ hideAttribution: true }}
          >
            <Background color="#1e293b" gap={20} size={1} />
            <Controls className="bg-black/50 border-white/10 fill-white" />
          </ReactFlow>
        )}
      </div>
    </div>
  );
};
