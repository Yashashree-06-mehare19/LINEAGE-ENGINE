import axios from 'axios';

// Since FastAPI is running on port 8000
const API = axios.create({ 
  baseURL: 'http://localhost:8000',
  timeout: 10000,
});

export const getUpstream = async (datasetUri, depth = 5) => {
  const res = await API.get(`/lineage/upstream/${datasetUri}`, { params: { depth } });
  return res.data;
};

export const getDownstream = async (datasetUri, depth = 5) => {
  const res = await API.get(`/lineage/downstream/${datasetUri}`, { params: { depth } });
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
  const res = await API.get(`/lineage/impact/${datasetUri}`);
  return res.data;
};

export const propagatePii = async () => {
  const res = await API.post('/lineage/admin/propagate-pii');
  return res.data;
};
