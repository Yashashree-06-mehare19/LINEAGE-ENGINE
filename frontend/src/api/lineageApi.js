import axios from 'axios';

// Since FastAPI is running on port 8000
const API = axios.create({ 
  baseURL: 'http://localhost:8000',
  timeout: 10000,
});

export const getUpstream = async (datasetUri, depth = 5) => {
  const res = await API.get(`/lineage/upstream/${encodeURIComponent(datasetUri)}`, { params: { depth } });
  return res.data;
};

export const getDownstream = async (datasetUri, depth = 5) => {
  const res = await API.get(`/lineage/downstream/${encodeURIComponent(datasetUri)}`, { params: { depth } });
  return res.data;
};

export const getRuns = async (jobId) => {
  const res = await API.get(`/lineage/runs/${encodeURIComponent(jobId)}`);
  return res.data;
};

export const getDatasets = async () => {
  const res = await API.get('/lineage/datasets');
  return res.data;
};

export const getGlobalRuns = async (limit = 100) => {
  const res = await API.get('/lineage/runs/global', { params: { limit } });
  return res.data;
};

export const getImpact = async (datasetUri) => {
  const res = await API.get(`/lineage/impact/${encodeURIComponent(datasetUri)}`);
  return res.data;
};

export const propagatePii = async () => {
  const res = await API.post('/lineage/admin/propagate-pii');
  return res.data;
};

// ── Stage 10: Column-Level Lineage ────────────────────────────────────────────

export const getDatasetColumns = async (datasetUri) => {
  const res = await API.get(`/lineage/columns/${encodeURIComponent(datasetUri)}`);
  return res.data;
};

export const getColumnUpstream = async (columnUri) => {
  const res = await API.get(`/lineage/column-upstream/${encodeURIComponent(columnUri)}`);
  return res.data;
};

export const getColumnImpact = async (columnUri) => {
  const res = await API.get(`/lineage/column-impact/${encodeURIComponent(columnUri)}`);
  return res.data;
};
