const pool = require('../config/db');
const { scoreMatch } = require('./scoring');

const VECTOR_WEIGHT = Number(process.env.MATCH_VECTOR_WEIGHT) || 0.7;
const ATTR_WEIGHT = Number(process.env.MATCH_ATTR_WEIGHT) || 0.3;
const CANDIDATE_POOL = Number(process.env.MATCH_CANDIDATE_POOL) || 50;

async function findMatches({ userId, targetRole, limit, filters = {} }) {
  const { rows: meRows } = await pool.query(
    'SELECT role, attributes FROM extracted_profiles WHERE user_id = $1',
    [userId]
  );
  if (!meRows.length) {
    const err = new Error('No extracted profile for user; run extraction first');
    err.status = 404;
    throw err;
  }
  const me = meRows[0];

  const conditions = ['ep.role = $2', 'ep.user_id <> $1'];
  const params = [userId, targetRole];

  const sectorKey = targetRole === 'investor' ? 'sectors' : 'industry';
  const stageKey = targetRole === 'investor' ? 'stages' : 'stage';
  const regionKey = targetRole === 'investor' ? 'geographies' : 'target_regions';

  if (filters.sector) {
    params.push(filters.sector.toLowerCase());
    conditions.push(`ep.attributes->'${sectorKey}' ? $${params.length}`);
  }
  if (filters.stage) {
    params.push(filters.stage.toLowerCase());
    conditions.push(
      targetRole === 'investor'
        ? `ep.attributes->'${stageKey}' ? $${params.length}`
        : `ep.attributes->>'${stageKey}' = $${params.length}`
    );
  }
  if (filters.region) {
    params.push(filters.region.toLowerCase());
    conditions.push(`ep.attributes->'${regionKey}' ? $${params.length}`);
  }

  const { rows: candidates } = await pool.query(
    `WITH me AS (
       SELECT embedding FROM extracted_profiles WHERE user_id = $1
     )
     SELECT ep.user_id, ep.attributes,
            1 - (ep.embedding <=> me.embedding) AS vector_score
     FROM extracted_profiles ep, me
     WHERE ${conditions.join(' AND ')}
     ORDER BY ep.embedding <=> me.embedding
     LIMIT ${CANDIDATE_POOL}`,
    params
  );

  const matches = candidates
    .map((c) => {
      const vectorScore = Number(c.vector_score);
      const { attributeScore, reasons } = scoreMatch(me.role, me.attributes, c.attributes);
      return {
        userId: c.user_id,
        score: Number((VECTOR_WEIGHT * vectorScore + ATTR_WEIGHT * attributeScore).toFixed(4)),
        vectorScore: Number(vectorScore.toFixed(4)),
        attributeScore: Number(attributeScore.toFixed(4)),
        attributes: c.attributes,
        reasons,
      };
    })
    .sort((a, b) => b.score - a.score)
    .slice(0, limit);

  return { userId, role: me.role, matches };
}

module.exports = { findMatches };
