const { Router } = require('express');
const { findMatches } = require('../services/matching.service');

const router = Router();

// Python matching API (deal-flow-matchmaker, uvicorn :8000) that owns the ranked composite /matches list.
const MATCHING_API_URL = process.env.MATCHING_API_URL || 'http://localhost:8000';

function parseLimit(value) {
  const n = Number(value) || 10;
  return Math.min(Math.max(n, 1), 50);
}

// Forward bare GET /matches (and its query string) to the Python API. nginx maps /api/matches here
// after stripping /api, so this is what dqplus.ddns.net/api/matches resolves to. The two
// /matches/{role} routes below are unaffected.
router.get('/matches', async (req, res, next) => {
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

router.get('/matches/founders/:userId/investors', async (req, res, next) => {
  try {
    const result = await findMatches({
      userId: req.params.userId,
      targetRole: 'investor',
      limit: parseLimit(req.query.limit),
      filters: { sector: req.query.sector, stage: req.query.stage, region: req.query.region },
    });
    res.json(result);
  } catch (err) {
    next(err);
  }
});

router.get('/matches/investors/:userId/founders', async (req, res, next) => {
  try {
    const result = await findMatches({
      userId: req.params.userId,
      targetRole: 'founder',
      limit: parseLimit(req.query.limit),
      filters: { sector: req.query.sector, stage: req.query.stage, region: req.query.region },
    });
    res.json(result);
  } catch (err) {
    next(err);
  }
});

module.exports = router;
