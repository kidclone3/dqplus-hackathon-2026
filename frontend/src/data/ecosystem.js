export const SECTORS = [
  { id: 'ai', label: 'AI' }, { id: 'fintech', label: 'Fintech' }, { id: 'agritech', label: 'Agritech' },
  { id: 'healthtech', label: 'Healthtech' }, { id: 'cleantech', label: 'Cleantech' }, { id: 'deeptech', label: 'Deep Tech' },
  { id: 'edtech', label: 'EdTech' }, { id: 'logistics', label: 'Logistics' }, { id: 'saas', label: 'SaaS' },
];

export const CANDIDATES = [
  { name: 'Touchstone Partners', type: 'Venture Capital', dot: '#b08636', score: 89, sectors: ['Agritech', 'Cleantech'], rationale: 'Early-stage climate thesis with a Vietnam focus — the closest fit to your raise.', sources: [{ label: 'touchstone.vc', url: 'https://touchstone.vc' }, { label: 'techinasia.com', url: 'https://www.techinasia.com' }] },
  { name: 'Do Ventures', type: 'Venture Capital', dot: '#b08636', score: 84, sectors: ['Agritech', 'SaaS'], rationale: 'Seed–Series A fund with an agritech and impact portfolio.', sources: [{ label: 'doventures.vc', url: 'https://doventures.vc' }] },
  { name: 'VNU Materials Lab', type: 'University', dot: '#7a5aa6', score: 81, sectors: ['Deep Tech', 'Cleantech'], rationale: 'Four licensable soil-science patents that directly match your roadmap.', sources: [{ label: 'vnu.edu.vn', url: 'https://vnu.edu.vn' }] },
  { name: 'Mekong Capital', type: 'Venture Capital', dot: '#b08636', score: 77, sectors: ['Fintech', 'Logistics'], rationale: 'Strong operational value-add, though agritech is adjacent to their core.', sources: [{ label: 'mekongcapital.com', url: 'https://mekongcapital.com' }] },
  { name: 'FPT Corporation', type: 'Corporation', dot: '#3f6c9c', score: 73, sectors: ['AI', 'SaaS'], rationale: 'Distribution and pilot capacity; no active agritech mandate this quarter.', sources: [{ label: 'fpt.com', url: 'https://fpt.com' }] },
  { name: 'VinAI Research', type: 'Research', dot: '#3f8f8f', score: 70, sectors: ['AI', 'Deep Tech'], rationale: 'Strong ML talent for sensor intelligence; less commercial alignment.', sources: [] },
  { name: 'Vingroup', type: 'Corporation', dot: '#3f6c9c', score: 66, sectors: ['Cleantech', 'Logistics'], rationale: 'Large-scale pilots are possible, but decision cycles are long.', sources: [{ label: 'vingroup.net', url: 'https://vingroup.net' }] },
  { name: 'NIC', type: 'Government', dot: '#a65a6b', score: 62, sectors: ['AI', 'Deep Tech'], rationale: 'Ecosystem access and grants; indirect to your immediate raise.', sources: [{ label: 'nic.gov.vn', url: 'https://nic.gov.vn' }], draftError: true },
  { name: 'ThinkZone Ventures', type: 'Venture Capital', dot: '#b08636', score: 58, sectors: ['SaaS', 'Fintech'], rationale: 'Early-stage generalist; sector fit is moderate.', sources: [{ label: 'thinkzone.vn', url: 'https://thinkzone.vn' }] },
  { name: 'HUST Research Institute', type: 'Research', dot: '#3f8f8f', score: 54, sectors: ['Deep Tech', 'Cleantech'], rationale: 'Relevant materials expertise; engagement setup takes time.', sources: [{ label: 'hust.edu.vn', url: 'https://hust.edu.vn' }] },
];

export const PARTNERS = [
  { name: 'VNU Materials Lab', type: 'University', dot: '#7a5aa6', score: 88, sectors: ['Agritech', 'Cleantech'], rationale: 'Licensable soil-science IP and a lab team open to joint R&D on your roadmap.', sources: [{ label: 'vnu.edu.vn', url: 'https://vnu.edu.vn' }], people: [{ name: 'Dr. Nguyễn Văn An', role: 'Head of Technology Transfer' }, { name: 'Dr. Trần Thu Hà', role: 'Soil Science Lead' }] },
  { name: 'Dr. Lê Minh — Mentor Network', type: 'Mentor', dot: '#7a5aa6', score: 84, sectors: ['Agritech', 'Deep Tech'], rationale: 'Two-time agritech founder; mentors seed teams on hardware go-to-market.', sources: [{ label: 'linkedin.com', url: 'https://linkedin.com' }], people: [{ name: 'Dr. Lê Minh', role: 'Seed-stage mentor · GTM & hardware' }] },
  { name: 'VinAI Research', type: 'Research', dot: '#3f8f8f', score: 80, sectors: ['AI', 'Deep Tech'], rationale: 'ML research partner for sensor intelligence and model tuning.', sources: [], people: [{ name: 'Dr. Trần Quốc Bảo', role: 'Research Lead · Applied ML' }] },
  { name: 'HUST Research Institute', type: 'Research', dot: '#3f8f8f', score: 74, sectors: ['Deep Tech', 'Cleantech'], rationale: 'Materials characterisation and testing facilities for field pilots.', sources: [{ label: 'hust.edu.vn', url: 'https://hust.edu.vn' }], people: [{ name: 'Dr. Phạm Thị Hương', role: 'Materials Lab Director' }] },
  { name: 'Mekong Agri Accelerator', type: 'Accelerator', dot: '#b08636', score: 70, sectors: ['Agritech', 'SaaS'], rationale: 'Structured mentorship cohort with corporate and grant connections.', sources: [{ label: 'mekongagri.vn', url: 'https://mekongagri.vn' }], people: [{ name: 'Ms. Vũ Lan', role: 'Program Director · Mentorship' }] },
];

export const CUSTOMERS = [
  { name: 'Lộc Trời Group', type: 'Corporation', dot: '#3f6c9c', score: 86, sectors: ['Agritech', 'Logistics'], rationale: 'Large rice producer that needs emissions measurement for export compliance.', sources: [{ label: 'loctroigroup.com', url: 'https://loctroigroup.com' }] },
  { name: 'Vinamilk', type: 'Corporation', dot: '#3f6c9c', score: 80, sectors: ['Agritech', 'Cleantech'], rationale: 'Dairy supply chain piloting sustainability-data tools with suppliers.', sources: [{ label: 'vinamilk.com.vn', url: 'https://vinamilk.com.vn' }] },
  { name: 'Nutifood', type: 'Corporation', dot: '#3f6c9c', score: 74, sectors: ['Agritech'], rationale: 'Sourcing programs need farm-level traceability data.', sources: [] },
  { name: 'An Giang Co-op Union', type: 'Cooperative', dot: '#3f6c9c', score: 71, sectors: ['Agritech'], rationale: 'Cooperative network seeking precise fertiliser advisory for members.', sources: [{ label: 'angiang.gov.vn', url: 'https://angiang.gov.vn' }] },
  { name: 'Olam Vietnam', type: 'Corporation', dot: '#3f6c9c', score: 68, sectors: ['Agritech', 'Logistics'], rationale: 'Agri-commodity buyer with MRV requirements across its supply base.', sources: [{ label: 'olamgroup.com', url: 'https://olamgroup.com' }] },
];

export const TALENT = [
  { name: 'Trần Quốc Anh', type: 'IoT Engineer', dot: '#3f8f6b', score: 85, sectors: ['Hardware', 'Sensors'], rationale: 'Built agri-sensor systems at two startups; open to seed-stage roles.', sources: [{ label: 'linkedin.com', url: 'https://linkedin.com' }] },
  { name: 'Phạm Thu Hà', type: 'ML Engineer', dot: '#3f8f6b', score: 82, sectors: ['AI', 'Agritech'], rationale: 'Soil and crop modelling experience; seeking a mission-driven team.', sources: [{ label: 'github.com', url: 'https://github.com' }] },
  { name: 'Nguyễn Đức', type: 'Full-stack Engineer', dot: '#3f8f6b', score: 78, sectors: ['SaaS', 'Web'], rationale: 'Ships fast; prior farmer-facing app experience.', sources: [] },
  { name: 'Lê Hoàng', type: 'Field Ops Lead', dot: '#3f8f6b', score: 72, sectors: ['Agritech', 'Operations'], rationale: 'Ran provincial pilot rollouts across the Mekong Delta.', sources: [{ label: 'linkedin.com', url: 'https://linkedin.com' }] },
  { name: 'Đỗ Mai', type: 'Product Designer', dot: '#3f8f6b', score: 69, sectors: ['SaaS', 'Design'], rationale: 'Designs for low-literacy rural users; strong field-research habit.', sources: [] },
];

export const STARTUPS = [
  { name: 'enfarm', type: 'Startup · Seed', dot: '#3f8f6b', score: 90, sectors: ['Agritech', 'Cleantech'], rationale: 'Soil-intelligence hardware with three provincial pilots and export-driven demand.', sources: [{ label: 'enfarm.vn', url: 'https://enfarm.vn' }] },
  { name: 'GreenLoop', type: 'Startup · Seed', dot: '#3f8f6b', score: 85, sectors: ['Agritech', 'Cleantech'], rationale: 'MRV platform monetising rice-emissions credits; early cooperative traction.', sources: [{ label: 'greenloop.vn', url: 'https://greenloop.vn' }] },
  { name: 'AquaSense', type: 'Startup · Pre-seed', dot: '#3f8f6b', score: 79, sectors: ['Agritech', 'IoT'], rationale: 'Water-quality sensors for aquaculture; strong founder-market fit.', sources: [] },
  { name: 'FarmLedger', type: 'Startup · Seed', dot: '#3f8f6b', score: 74, sectors: ['Fintech', 'Agritech'], rationale: 'Embedded financing for smallholder input purchases.', sources: [{ label: 'farmledger.vn', url: 'https://farmledger.vn' }] },
  { name: 'CropMind', type: 'Startup · Pre-seed', dot: '#3f8f6b', score: 70, sectors: ['AI', 'Agritech'], rationale: 'Vision models for pest detection; pilots underway with two co-ops.', sources: [] },
];

export const DATASETS = { investors: CANDIDATES, partners: PARTNERS, customers: CUSTOMERS, talent: TALENT };

export const INTENTS = [
  { id: 'investors', tab: 'Investment Fund', title: 'Investment funds that fit your raise.', sub: 'Capital partners ranked by fit with {p}.' },
  { id: 'customers', tab: 'Potential customers', title: 'Businesses that need what you build.', sub: 'Companies with demand in {p}’s sector, ranked by fit.' },
  { id: 'partners', tab: 'Partners & mentors', title: 'Partners & mentors for your R&D.', sub: 'Research partners and mentors in {p}’s sector, ranked by fit.' },
  { id: 'talent', tab: 'Talent', title: 'People who fit your team.', sub: 'Candidates in {p}’s sector, ranked by fit.' },
];

export const WHY_NOW = {
  investors: 'Actively deploying this quarter — and the Q1 R&D tax-credit window makes co-investment materially cheaper.',
  partners: 'Research and mentorship capacity is open this cycle — engaging now lines up with your next product milestone.',
  customers: 'Annual budgets are being set now; early conversations put you on the roadmap before procurement locks.',
  talent: 'Strong candidates in this space are exploring moves this quarter — reaching out early wins their attention.',
};

export const STAGES = [
  { value: 'pre_seed', label: 'Pre-seed' },
  { value: 'seed', label: 'Seed' },
  { value: 'series_a', label: 'Series A' },
  { value: 'series_b', label: 'Series B+' },
  { value: 'growth', label: 'Growth' },
];
