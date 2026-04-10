import React, { useCallback, useEffect } from 'react';
import ReactFlow, { 
  Background, 
  Controls, 
  MiniMap,
  useNodesState,
  useEdgesState,
  MarkerType
} from 'reactflow';
import 'reactflow/dist/style.css';
import { nodeTypes } from './CustomNodes';
import { getLayoutedElements } from '../utils/graphLayout';

export const LineageGraph = ({ nodes, edges, onNodeClick }) => {
  const [rfNodes, setNodes, onNodesChange] = useNodesState([]);
  const [rfEdges, setEdges, onEdgesChange] = useEdgesState([]);

  useEffect(() => {
    // Add default React Flow shapes to our API nodes
    const formattedNodes = nodes.map(n => ({
      id: String(n.id),
      type: n.label, // 'Job' or 'Dataset'
      data: { ...n.properties, label: n.label },
      position: { x: 0, y: 0 },
    }));

    // Format edges
    const formattedEdges = edges.map(e => ({
      id: `${e.source_id}-${e.target_id}`,
      source: String(e.source_id),
      target: String(e.target_id),
      type: 'smoothstep',
      animated: true,
      style: { stroke: 'rgba(255, 255, 255, 0.4)', strokeWidth: 2 },
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: 'rgba(255, 255, 255, 0.6)',
      },
    }));

    // Apply layout
    const layouted = getLayoutedElements(formattedNodes, formattedEdges);
    setNodes([...layouted.nodes]);
    setEdges([...layouted.edges]);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, edges]);

  const handleNodeClick = useCallback((event, node) => {
    // Find original node structure from props to pass to sidepanel
    const originalNode = nodes.find(n => String(n.id) === node.id);
    if (originalNode && onNodeClick) {
      onNodeClick(originalNode);
    }
  }, [nodes, onNodeClick]);

  const handlePaneClick = useCallback(() => {
    if (onNodeClick) onNodeClick(null);
  }, [onNodeClick]);

  return (
    <div style={{ width: '100%', height: '100%' }}>
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        onPaneClick={handlePaneClick}
        nodeTypes={nodeTypes}
        fitView
        attributionPosition="bottom-left"
        minZoom={0.1}
        maxZoom={1.5}
      >
        <Background gap={24} size={2} color="#ffffff" style={{ opacity: 0.05 }} />
        <Controls 
          className="bg-black/50 border border-white/10 rounded-lg overflow-hidden backdrop-blur" 
          showInteractive={false}
        />
        <MiniMap 
          nodeColor={(n) => n.type === 'Dataset' ? '#3B82F6' : '#F97316'}
          maskColor="rgba(0,0,0, 0.8)"
          className="bg-black/50 border border-white/10 rounded-lg overflow-hidden backdrop-blur-md"
        />
      </ReactFlow>
    </div>
  );
};
