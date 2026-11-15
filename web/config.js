// Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team.

// API base URL.
//  - Production (Firebase Hosting rewrites /api/** to Cloud Run): same origin, "/api".
//  - Local dev (localhost / 127.0.0.1): the public Cloud Run API (it allows CORS from localhost).
//  - Override anywhere by defining window.LUNASCOUT_API before this file loads, e.g. a local API:
//      window.LUNASCOUT_API = "http://localhost:8000/api";
(function () {
  if (window.LUNASCOUT_API) return;
  var local = location.hostname === "localhost" || location.hostname === "127.0.0.1" || location.protocol === "file:";
  window.LUNASCOUT_API = local
    ? "https://lunascout-api-855190992553.southamerica-east1.run.app/api"
    : "/api";
})();
