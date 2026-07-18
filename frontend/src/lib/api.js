const BASE = import.meta.env.VITE_API_BASE || '/api';

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
  const res = await fetch(BASE + path, {
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
  return request('/auth/login', { method: 'POST', body: { username: email, password } });
}

export function register({ email, password, role }) {
  return request('/auth/register', {
    method: 'POST',
    body: { username: email, password, role: role === 'investor' ? 'investor' : 'founder' },
  });
}

export function getProfile(token, id) {
  return request('/profiles/' + id, { token });
}

export function saveProfile(token, profileId, payload) {
  if (profileId) {
    return request('/profiles/' + profileId, { method: 'PATCH', token, body: payload });
  }
  return request('/profiles', { method: 'POST', token, body: payload });
}

export function toProfilePayload(form) {
  return {
    company_name: form.name,
    country: form.country || null,
    stage: form.stage,
    num_of_employees: form.numEmployees === '' ? null : Number(form.numEmployees),
    industry: form.sectors.join(','),
    target_region: form.targetRegion || null,
    arr: form.arr === '' ? null : Number(form.arr),
    where_you_operate: form.geography,
    website: form.website.split(',').map((s) => s.trim()).filter(Boolean),
    description_product: form.need,
  };
}

export function fromProfile(p) {
  return {
    name: p.company_name || '',
    website: (p.website || []).join(', '),
    stage: p.stage || '',
    geography: p.where_you_operate || '',
    country: p.country || '',
    targetRegion: p.target_region || '',
    numEmployees: p.num_of_employees == null ? '' : String(p.num_of_employees),
    arr: p.arr == null ? '' : String(p.arr),
    sectors: p.industry ? p.industry.split(',') : [],
    need: p.description_product || '',
    consent: false,
  };
}
