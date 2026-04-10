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
