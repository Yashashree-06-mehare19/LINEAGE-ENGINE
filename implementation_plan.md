# Stage 2 (Week 2): Custom React Lineage Dashboard

This implementation plan covers the frontend visualization tool for the Lineage Engine, replacing the standard Neo4j browser with an interactive, specialized, pipeline-aware UI. We will use Vite, React Flow, and Tailwind CSS to create a premium, dynamic interface.

## Goal Description

We have fully ingested our DAG logic (dbt + Airflow models) and tested our REST APIs (`upstream`, `downstream`, and `runs`). Now we need a Frontend React Dashboard that consumes this REST data and renders left-to-right DAG graphs, interactive node panels, and execution run history screens.

In alignment with our design aesthetics rules, this app will not be a basic tool—it will feature **Rich Aesthetics (glassmorphism UI patterns, modern typography 'Inter', dynamic dark mode elements)** to make the data visualization pop.

> [!IMPORTANT]
> **User Review Required**  
> We need to scaffold the React frontend inside a new folder `/frontend`. If approved, I will use `npm create vite@latest frontend -- --template react` to scaffold the project structure. Are you okay with TailwindCSS being utilized for the premium aesthetics? 

## Proposed Architecture & Changes

### 1. Project Scaffolding
- Using Vite with React template mode.
- Install dependencies: `reactflow`, `dagre`, `axios`, `lucide-react` (icons), `tailwindcss`, `clsx`, `tailwind-merge` (for glassmorphism utility merging).

### 2. Design System Setup (TailwindCSS)
- Constructing `index.css` for background glassmorphism variables, dark space palettes (e.g. rich cosmic blue/black), and sleek dynamic utilities for hovering.
- Styling React Flow container overlays transparently over the dark backdrop.

### 3. Core Components

#### [NEW] `src/api/lineageApi.js`
- Axios wrapper exposing `getUpstream`, `getDownstream`, and `getRuns` endpoints mapped to `http://localhost:8000`.

#### [NEW] `src/utils/graphLayout.js` & `nodeStyles.js`
- Dagre configuration logic enforcing `LR` (Left-to-Right) alignments dynamically calculating tree depth.
- `nodeStyles.js`: Specialized rich visual styling differentiating **Dataset Nodes** (glowy blue hues) and **Job Nodes** (fiery orange schemas) incorporating micro-animations.

#### [NEW] `src/components/LineageGraph.jsx`
- The React Flow render canvas holding viewport controls. 

#### [NEW] `src/components/NodeSidePanel.jsx` & `RunsPanel.jsx`
- Sliding drawer built with glassmorphism layout rendering:
  - Node properties (Owner, Tags, Namespace, URI).
  - Navigation queries: Explore Up/Down.
  - View Run History button pointing to `RunsPanel`.
- Popover/Modal overlay mapping Run status logs natively with green/red dynamic badging.

#### [NEW] `src/components/SearchBar.jsx`
- Futuristic hero-positioned input box taking a Dataset URI. Options to trigger Depth and target Upstream vs Downstream modes.

## Open Questions

> [!WARNING]
> Do you have any specific color themes you'd prefer beyond "Vibrant Dark-Mode/Glassmorphism"?
> By default, I will configure the FastAPI server to support CORS locally so our `localhost:5173` Vite server can make calls securely. Is this fine?

## Verification Plan

### Automated Tests
1. Scaffold frontend completely without errors.
2. We will `npm run dev` and ensure the server boots silently locally.

### Manual Verification
- We will boot up both `uvicorn app.main:app` and `npm run dev` side-by-side. 
- Open the browser at `http://localhost:5173`, search for `reporting.order_summary`, and ensure the left-to-right Directed Acyclic Graph (DAG) expands perfectly on screen.
- Verify sliding panels react without lag.
