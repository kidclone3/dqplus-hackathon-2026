const { Router } = require('express');

const router = Router();

// Python matching API (deal-flow-matchmaker, uvicorn :8000) that owns the ranked composite /matches list.
const MATCHING_API_URL = process.env.MATCHING_API_URL || 'http://localhost:8000';

// Forward GET /matches (and its query string, e.g. ?startup_id=...) to the Python API.
router.get('/', async (req, res, next) => {
  try {
    const search = req.originalUrl.includes('?')
      ? req.originalUrl.slice(req.originalUrl.indexOf('?'))
      : '';
    const upstream = await fetch(`${MATCHING_API_URL}/matches${search}`, {
      headers: { Accept: 'application/json' },
      signal: AbortSignal.timeout(8000),
    });
    const body = await upstream.text();
    res
      .status(upstream.status)
      .type(upstream.headers.get('content-type') || 'application/json')
      .send(body);
  } catch (err) {
    next(err);
  }
});

module.exports = router;
