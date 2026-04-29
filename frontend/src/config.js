// Centralised app config. Backend base URL is injected by webpack at build
// time from config/{dev,prod}.env.js (DefinePlugin sets process.env.API_BASE).
// Override at build time:  API_BASE=https://api.example.com npm run build

export const API_BASE =
  (typeof process !== 'undefined' && process.env && process.env.API_BASE) ||
  'http://127.0.0.1:8080';

export const api = (path) => `${API_BASE}${path}`;
