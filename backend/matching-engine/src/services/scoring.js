function jaccard(a = [], b = []) {
  if (!a.length || !b.length) return 0;
  const setA = new Set(a.map((s) => String(s).toLowerCase()));
  const setB = new Set(b.map((s) => String(s).toLowerCase()));
  const intersection = [...setA].filter((x) => setB.has(x));
  const union = new Set([...setA, ...setB]);
  return intersection.length / union.size;
}

function intersect(a = [], b = []) {
  const setB = new Set(b.map((s) => String(s).toLowerCase()));
  return a.map((s) => String(s).toLowerCase()).filter((x) => setB.has(x));
}

// founderAttrs: industry[], stage, target_regions[], funding_ask_usd
// investorAttrs: sectors[], stages[], geographies[], check_size_min_usd, check_size_max_usd
function scoreAttributes(founderAttrs, investorAttrs) {
  const reasons = [];
  let score = 0;

  const sectorOverlap = jaccard(founderAttrs.industry, investorAttrs.sectors);
  if (sectorOverlap > 0) {
    score += 0.4 * sectorOverlap;
    reasons.push(`sector overlap: ${intersect(founderAttrs.industry, investorAttrs.sectors).join(', ')}`);
  }

  if (founderAttrs.stage && (investorAttrs.stages || []).map((s) => String(s).toLowerCase()).includes(String(founderAttrs.stage).toLowerCase())) {
    score += 0.3;
    reasons.push(`stage match: ${founderAttrs.stage}`);
  }

  const geos = (investorAttrs.geographies || []).map((s) => String(s).toLowerCase());
  const regions = (founderAttrs.target_regions || []).map((s) => String(s).toLowerCase());
  if (geos.includes('global') && regions.length) {
    score += 0.2;
    reasons.push('investor invests globally');
  } else {
    const geoOverlap = intersect(regions, geos);
    if (geoOverlap.length) {
      score += 0.2;
      reasons.push(`geography match: ${geoOverlap.join(', ')}`);
    }
  }

  const ask = founderAttrs.funding_ask_usd;
  const min = investorAttrs.check_size_min_usd;
  const max = investorAttrs.check_size_max_usd;
  if (ask != null && (min != null || max != null)) {
    const aboveMin = min == null || ask >= min;
    const belowMax = max == null || ask <= max;
    if (aboveMin && belowMax) {
      score += min != null && max != null ? 0.1 : 0.05;
      reasons.push('check size fits funding ask');
    }
  }

  return { attributeScore: Math.min(score, 1), reasons };
}

function scoreMatch(requesterRole, requesterAttrs, candidateAttrs) {
  return requesterRole === 'founder'
    ? scoreAttributes(requesterAttrs, candidateAttrs)
    : scoreAttributes(candidateAttrs, requesterAttrs);
}

module.exports = { scoreMatch, scoreAttributes, jaccard };
