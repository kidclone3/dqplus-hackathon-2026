// Per-service bases mirror the nginx/vite proxy routing:
// /api/backend → gateway, /api/agents → extract agent, /api/matches → matching engine.
const ROOT = import.meta.env.VITE_API_BASE || '/api';
const BACKEND = ROOT + '/backend';
const AGENTS = ROOT + '/agents';

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

export function isNetworkError(e) {
  return e instanceof TypeError || (e && (e.name === 'TimeoutError' || e.name === 'AbortError'));
}

async function request(path, { method = 'GET', token, body } = {}) {
  const res = await fetch(path, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: 'Bearer ' + token } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(8000),
  });
  let data = null;
  try {
    data = await res.json();
  } catch (e) {
    data = null;
  }
  if (!res.ok) {
    throw new ApiError((data && data.error) || 'Request failed', res.status);
  }
  return data;
}

export function login({ email, password }) {
  return request(BACKEND + '/auth/login', { method: 'POST', body: { username: email, password } });
}

export function register({ email, password, role }) {
  return request(BACKEND + '/auth/register', {
    method: 'POST',
    body: { username: email, password, role: role === 'investor' ? 'investor' : 'founder' },
  });
}

export function getProfile(token, id) {
  return request(BACKEND + '/profiles/' + id, { token });
}

export function saveProfile(token, profileId, payload) {
  if (profileId) {
    return request(BACKEND + '/profiles/' + profileId, { method: 'PATCH', token, body: payload });
  }
  return request(BACKEND + '/profiles', { method: 'POST', token, body: payload });
}

export function toProfilePayload(form) {
  return {
    company_name: form.name,
    stage: form.stage,
    industry: form.sectors.join(','),
    where_you_operate: form.geography,
    website: form.website.split(',').map((s) => s.trim()).filter(Boolean),
    description_product: form.need,
    email: form.email || null,
    phone_number: form.phone || null,
    avg_initial_investment: form.avgInitialInvestment === '' ? null : Number(form.avgInitialInvestment),
    annual_investment_count: form.annualInvestmentCount === '' ? null : Number(form.annualInvestmentCount),
    avg_holding_period: form.avgHoldingPeriod === '' ? null : Number(form.avgHoldingPeriod),
    year_founded: form.yearFounded === '' ? null : Number(form.yearFounded),
    num_of_employees: form.companySize === '' ? null : Number(form.companySize),
  };
}

export function extractProfile(userId) {
  return request(AGENTS + '/extract/profile', { method: 'POST', body: { userId } });
}

export function getMatches({ userId, role }) {
  const path = role === 'investor'
    ? ROOT + '/matches/investors/' + userId + '/founders'
    : ROOT + '/matches/founders/' + userId + '/investors';
  return request(path + '?limit=50');
}

// Composite ranked list, forwarded by the gateway to the Python matching API
// (ai-data-platform), as opposed to the role-specific pgvector + attribute scoring above.
export function getAllMatches({ startupId } = {}) {
  const query = startupId ? '?startup_id=' + encodeURIComponent(startupId) : '';
  return request(BACKEND + '/matches' + query);
}

const INVESTOR_TYPES = {
  vc: 'Venture Capital',
  angel: 'Angel Investor',
  cvc: 'Corporate VC',
  pe: 'Private Equity',
  'family-office': 'Family Office',
};

const cap = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);

export function matchToCandidate(m, role) {
  const a = m.attributes || {};
  const reasons = m.reasons || [];
  const base = {
    userId: m.userId,
    score: Math.round(m.score * 100),
    vectorScore: Math.round(m.vectorScore * 100),
    attributeScore: Math.round(m.attributeScore * 100),
    reasons,
    rationale: reasons.length
      ? cap(reasons.join(' · '))
      : 'Ranked by semantic similarity between both profiles.',
  };
  if (role === 'investor') {
    return {
      ...base,
      name: a.company_name || 'Unnamed startup',
      type: 'Startup' + (a.stage ? ' · ' + cap(a.stage) : ''),
      dot: '#3f8f6b',
      sectors: (a.industry || []).map(cap),
    };
  }
  return {
    ...base,
    name: a.firm_name || 'Unnamed investor',
    type: INVESTOR_TYPES[a.investor_type] || 'Investor',
    dot: '#b08636',
    sectors: (a.sectors || []).map(cap),
  };
}

export function fromProfile(p) {
  return {
    name: p.company_name || '',
    website: (p.website || []).join(', '),
    stage: p.stage || '',
    geography: p.where_you_operate || '',
    sectors: p.industry ? p.industry.split(',') : [],
    need: p.description_product || '',
    email: p.email || '',
    phone: p.phone_number || '',
    avgInitialInvestment: p.avg_initial_investment == null ? '' : String(p.avg_initial_investment),
    annualInvestmentCount: p.annual_investment_count == null ? '' : String(p.annual_investment_count),
    avgHoldingPeriod: p.avg_holding_period == null ? '' : String(p.avg_holding_period),
    yearFounded: p.year_founded == null ? '' : String(p.year_founded),
    companySize: p.num_of_employees == null ? '' : String(p.num_of_employees),
    consent: false,
  };
}
