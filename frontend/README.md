# Village Pond Planning frontend

This React/Vite client presents screening controls, provenance, data-quality warnings, optional results, and geospatial overlays. It requires an explicit user confirmation before analysis and never labels RGB-derived surface appearance as ownership or final suitability.

```powershell
npm ci
Copy-Item .env.example .env
npm run dev
```

Quality gates:

```powershell
npm run lint
npm run test
npm run build
npm audit --audit-level=high
```

`VITE_API_BASE_URL` defaults to `/api`. The protected history endpoint is intentionally not exposed in the public client because its administrator key must never be compiled into browser code. Imagery URL and attribution are compile-time settings; if an operator changes the imagery origin, the Nginx content-security policy must be updated as well.

See the repository-level README for deployment and scientific limitations.
