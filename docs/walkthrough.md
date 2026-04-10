# Walkthrough: Stage 2 Lineage Web Dashboard

Our Lineage Engine graph interface is no longer restricted to Neo4j Developer Tools! Here's a brief tour of everything successfully implemented in the new UI.

## What Was Completed

1. **Vite + React Integration**
   - Booted an `npm run dev` container actively pulling backend state.
   - Built a custom fetching service wrapping `axios` that hooks directly into `http://localhost:8000/lineage` API Endpoints seamlessly.

2. **Graph Visualization Component (`LineageGraph.jsx`)**
   - Configured `React Flow` with embedded native pan/zoom tools and minimaps.
   - Wired `@dagrejs/dagre` traversing utilities ensuring all lineage cascades accurately **Left-to-Right** down the tree layers.
   - Built dual distinct UI nodes: `Database` wrappers for tables, and `Activity` layers for jobs.

3. **Dynamic Sidebars (`NodeSidePanel.jsx` & `RunsPanel.jsx`)**
   - Clickable interfaces sliding into frame with rich layout formatting.
   - View property data (tags, URI metadata) and click to shift your canvas rendering deep up/down lineages interactively.
   - An isolated pop-up executing independent DB fetches against `PostgreSQL` to list real, color-status-coded job histories (`run_ids`).

4. **Sleek Aesthetics Styling**
   - Utilized pure `TailwindCSS` with active configurations for glowing border offsets `shadow-xl`, frosted `backdrop-blur` UI panels, and deep cosmic spacing `darkspace` colors.

## Running It Yourself
Simply hit down your local Vite engine:
> Open [http://localhost:5173](http://localhost:5173) in your browser.
Search exactly: `postgres://prod:5432/reporting.order_summary` with `Upstream` hit, or `postgres://prod:5432/raw.orders` with `Downstream` hit to experiment with the pipelines you seeded previously.
