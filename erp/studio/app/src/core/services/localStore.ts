/**
 * Local Store - Lightweight localStorage persistence for modules without backend API
 * Provides CRUD operations with zustand-like API backed by localStorage
 * Used for: Campaigns, Tickets, Pipelines, Deployments, Ledger, Payables, etc.
 */

import { create } from 'zustand';

// Generic CRUD store factory
export function createLocalCrudStore<T extends { id: string }>(
  storageKey: string,
  defaultData: T[] = []
) {
  function load(): T[] {
    try {
      const stored = localStorage.getItem(storageKey);
      if (stored) return JSON.parse(stored);
      // Initialize with defaults on first load
      localStorage.setItem(storageKey, JSON.stringify(defaultData));
      return defaultData;
    } catch {
      return defaultData;
    }
  }

  function save(items: T[]) {
    try {
      localStorage.setItem(storageKey, JSON.stringify(items));
    } catch {
      // Storage full
    }
  }

  return create<{
    items: T[];
    isLoading: boolean;
    add: (item: Omit<T, 'id'>) => T;
    update: (id: string, data: Partial<T>) => void;
    remove: (id: string) => void;
    reload: () => void;
  }>((set, get) => ({
    items: load(),
    isLoading: false,

    add: (data) => {
      const newItem = {
        ...data,
        id: `${storageKey}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      } as T;
      const updated = [...get().items, newItem];
      save(updated);
      set({ items: updated });
      return newItem;
    },

    update: (id, data) => {
      const updated = get().items.map((item) =>
        item.id === id ? { ...item, ...data } : item
      );
      save(updated);
      set({ items: updated });
    },

    remove: (id) => {
      const updated = get().items.filter((item) => item.id !== id);
      save(updated);
      set({ items: updated });
    },

    reload: () => {
      set({ items: load() });
    },
  }));
}

// ============================================================================
// Campaign Store
// ============================================================================

export interface Campaign {
  id: string;
  name: string;
  type: 'email' | 'social' | 'ads' | 'content' | 'event';
  status: 'draft' | 'active' | 'paused' | 'completed';
  budget: number;
  spent: number;
  startDate: string;
  endDate: string;
  reach: number;
  conversions: number;
  roi: number;
  description?: string;
  createdAt: string;
}

export const useCampaignStore = createLocalCrudStore<Campaign>('singularity-campaigns', [
  {
    id: 'camp-1',
    name: 'Q1 Product Launch',
    type: 'email',
    status: 'active',
    budget: 15000,
    spent: 8500,
    startDate: '2026-01-15',
    endDate: '2026-03-31',
    reach: 25000,
    conversions: 450,
    roi: 3.2,
    description: 'Multi-channel product launch campaign',
    createdAt: '2026-01-10T00:00:00Z',
  },
  {
    id: 'camp-2',
    name: 'Brand Awareness Social',
    type: 'social',
    status: 'active',
    budget: 8000,
    spent: 5200,
    startDate: '2026-02-01',
    endDate: '2026-04-30',
    reach: 150000,
    conversions: 1200,
    roi: 4.5,
    description: 'Social media brand awareness push',
    createdAt: '2026-01-28T00:00:00Z',
  },
  {
    id: 'camp-3',
    name: 'Developer Conference',
    type: 'event',
    status: 'draft',
    budget: 25000,
    spent: 0,
    startDate: '2026-05-15',
    endDate: '2026-05-17',
    reach: 0,
    conversions: 0,
    roi: 0,
    description: 'Annual developer conference sponsorship',
    createdAt: '2026-02-20T00:00:00Z',
  },
]);

// ============================================================================
// Support Ticket Store
// ============================================================================

export interface Ticket {
  id: string;
  subject: string;
  description: string;
  status: 'open' | 'in-progress' | 'waiting' | 'resolved' | 'closed';
  priority: 'low' | 'medium' | 'high' | 'critical';
  category: string;
  assignee?: string;
  contactName: string;
  contactEmail: string;
  createdAt: string;
  updatedAt: string;
  resolvedAt?: string;
}

export const useTicketStore = createLocalCrudStore<Ticket>('singularity-tickets', [
  {
    id: 'ticket-1',
    subject: 'Unable to access dashboard',
    description: 'User reports 403 error when accessing the main dashboard after login.',
    status: 'open',
    priority: 'high',
    category: 'Access',
    assignee: 'Engineering',
    contactName: 'John Smith',
    contactEmail: 'john@example.com',
    createdAt: '2026-03-04T10:30:00Z',
    updatedAt: '2026-03-04T10:30:00Z',
  },
  {
    id: 'ticket-2',
    subject: 'Invoice PDF generation failing',
    description: 'PDF export returns blank document for invoices created after March 1st.',
    status: 'in-progress',
    priority: 'medium',
    category: 'Finance',
    assignee: 'Backend Team',
    contactName: 'Sarah Chen',
    contactEmail: 'sarah@example.com',
    createdAt: '2026-03-03T15:00:00Z',
    updatedAt: '2026-03-04T09:00:00Z',
  },
  {
    id: 'ticket-3',
    subject: 'Feature request: Dark mode',
    description: 'Multiple users requesting dark mode support for the platform.',
    status: 'resolved',
    priority: 'low',
    category: 'Feature Request',
    contactName: 'Alex Johnson',
    contactEmail: 'alex@example.com',
    createdAt: '2026-02-28T12:00:00Z',
    updatedAt: '2026-03-05T02:00:00Z',
    resolvedAt: '2026-03-05T02:00:00Z',
  },
]);

// ============================================================================
// Pipeline Store (CI/CD)
// ============================================================================

export interface Pipeline {
  id: string;
  name: string;
  repository: string;
  branch: string;
  status: 'success' | 'failed' | 'running' | 'pending' | 'cancelled';
  trigger: 'push' | 'pr' | 'schedule' | 'manual';
  duration?: number; // seconds
  stages: { name: string; status: 'success' | 'failed' | 'running' | 'pending' | 'skipped'; duration?: number }[];
  commit?: string;
  author?: string;
  createdAt: string;
}

export const usePipelineStore = createLocalCrudStore<Pipeline>('singularity-pipelines', [
  {
    id: 'pipe-1',
    name: 'singularity-deploy',
    repository: 'artifact-virtual/singularity',
    branch: 'main',
    status: 'success',
    trigger: 'push',
    duration: 145,
    stages: [
      { name: 'Build', status: 'success', duration: 45 },
      { name: 'Test', status: 'success', duration: 62 },
      { name: 'Deploy', status: 'success', duration: 38 },
    ],
    commit: 'a3f8c91',
    author: 'Ali Shakil',
    createdAt: '2026-03-05T03:30:00Z',
  },
  {
    id: 'pipe-2',
    name: 'erp-frontend',
    repository: 'artifact-virtual/business-erp',
    branch: 'main',
    status: 'success',
    trigger: 'push',
    duration: 98,
    stages: [
      { name: 'Install', status: 'success', duration: 22 },
      { name: 'Lint', status: 'success', duration: 8 },
      { name: 'Build', status: 'success', duration: 45 },
      { name: 'Deploy', status: 'success', duration: 23 },
    ],
    commit: 'f7d2e44',
    author: 'Singularity',
    createdAt: '2026-03-05T04:15:00Z',
  },
  {
    id: 'pipe-3',
    name: 'comb-cloud-ci',
    repository: 'artifact-virtual/comb-cloud',
    branch: 'develop',
    status: 'failed',
    trigger: 'pr',
    duration: 67,
    stages: [
      { name: 'Build', status: 'success', duration: 30 },
      { name: 'Test', status: 'failed', duration: 37 },
      { name: 'Deploy', status: 'skipped' },
    ],
    commit: 'b1c4a88',
    author: 'AVA',
    createdAt: '2026-03-04T22:45:00Z',
  },
]);

// ============================================================================
// Deployment Store
// ============================================================================

export interface Deployment {
  id: string;
  name: string;
  environment: 'production' | 'staging' | 'development';
  status: 'active' | 'deploying' | 'failed' | 'rolled-back';
  version: string;
  url?: string;
  service: string;
  deployedBy: string;
  deployedAt: string;
  healthCheck?: 'healthy' | 'degraded' | 'down';
}

export const useDeploymentStore = createLocalCrudStore<Deployment>('singularity-deployments', [
  {
    id: 'dep-1',
    name: 'Singularity ERP',
    environment: 'production',
    status: 'active',
    version: '1.0.0',
    url: 'https://erp.artifactvirtual.com',
    service: 'artifact-erp',
    deployedBy: 'Singularity',
    deployedAt: '2026-03-05T04:00:00Z',
    healthCheck: 'healthy',
  },
  {
    id: 'dep-2',
    name: 'COMB Cloud',
    environment: 'production',
    status: 'active',
    version: '2.4.1',
    url: 'https://comb.artifactvirtual.com',
    service: 'comb-cloud',
    deployedBy: 'AVA',
    deployedAt: '2026-03-03T18:00:00Z',
    healthCheck: 'healthy',
  },
  {
    id: 'dep-3',
    name: 'Mach6 Gateway',
    environment: 'production',
    status: 'active',
    version: '1.2.0',
    service: 'mach6-gateway',
    deployedBy: 'Ali Shakil',
    deployedAt: '2026-03-02T14:30:00Z',
    healthCheck: 'healthy',
  },
  {
    id: 'dep-4',
    name: 'Qorvex Frontend',
    environment: 'production',
    status: 'active',
    version: '3.1.0',
    url: 'https://gladius.artifactvirtual.com',
    service: 'gladius',
    deployedBy: 'Vercel',
    deployedAt: '2026-03-01T10:00:00Z',
    healthCheck: 'healthy',
  },
]);

// ============================================================================
// Ledger Account Store
// ============================================================================

export interface LedgerAccount {
  id: string;
  code: string;
  name: string;
  type: 'asset' | 'liability' | 'equity' | 'revenue' | 'expense';
  balance: number;
  currency: string;
  description?: string;
  parentId?: string;
  isActive: boolean;
  createdAt: string;
}

export const useLedgerStore = createLocalCrudStore<LedgerAccount>('singularity-ledger', [
  { id: 'acct-1', code: '1000', name: 'Cash & Equivalents', type: 'asset', balance: 125000, currency: 'USD', isActive: true, createdAt: '2026-01-01T00:00:00Z' },
  { id: 'acct-2', code: '1200', name: 'Accounts Receivable', type: 'asset', balance: 45000, currency: 'USD', isActive: true, createdAt: '2026-01-01T00:00:00Z' },
  { id: 'acct-3', code: '2000', name: 'Accounts Payable', type: 'liability', balance: 18500, currency: 'USD', isActive: true, createdAt: '2026-01-01T00:00:00Z' },
  { id: 'acct-4', code: '3000', name: 'Owner Equity', type: 'equity', balance: 200000, currency: 'USD', isActive: true, createdAt: '2026-01-01T00:00:00Z' },
  { id: 'acct-5', code: '4000', name: 'Service Revenue', type: 'revenue', balance: 89000, currency: 'USD', isActive: true, createdAt: '2026-01-01T00:00:00Z' },
  { id: 'acct-6', code: '5000', name: 'Operating Expenses', type: 'expense', balance: 32000, currency: 'USD', isActive: true, createdAt: '2026-01-01T00:00:00Z' },
  { id: 'acct-7', code: '5100', name: 'Payroll', type: 'expense', balance: 55000, currency: 'USD', isActive: true, createdAt: '2026-01-01T00:00:00Z' },
  { id: 'acct-8', code: '5200', name: 'Infrastructure', type: 'expense', balance: 8500, currency: 'USD', isActive: true, createdAt: '2026-01-01T00:00:00Z' },
]);

// ============================================================================
// Bill (Payables) Store
// ============================================================================

export interface Bill {
  id: string;
  vendorName: string;
  vendorEmail?: string;
  description: string;
  amount: number;
  currency: string;
  status: 'pending' | 'approved' | 'paid' | 'overdue' | 'cancelled';
  issueDate: string;
  dueDate: string;
  paidDate?: string;
  category: string;
  createdAt: string;
}

export const useBillStore = createLocalCrudStore<Bill>('singularity-bills', [
  { id: 'bill-1', vendorName: 'AWS', description: 'Cloud hosting - March 2026', amount: 2400, currency: 'USD', status: 'pending', issueDate: '2026-03-01', dueDate: '2026-03-31', category: 'Infrastructure', createdAt: '2026-03-01T00:00:00Z' },
  { id: 'bill-2', vendorName: 'Cloudflare', description: 'CDN & Security', amount: 200, currency: 'USD', status: 'paid', issueDate: '2026-02-01', dueDate: '2026-02-28', paidDate: '2026-02-15', category: 'Infrastructure', createdAt: '2026-02-01T00:00:00Z' },
  { id: 'bill-3', vendorName: 'Vercel', description: 'Edge hosting', amount: 150, currency: 'USD', status: 'paid', issueDate: '2026-02-01', dueDate: '2026-02-28', paidDate: '2026-02-20', category: 'Infrastructure', createdAt: '2026-02-01T00:00:00Z' },
]);

// ============================================================================
// Job Posting (Recruitment) Store
// ============================================================================

export interface JobPosting {
  id: string;
  title: string;
  department: string;
  location: string;
  type: 'full-time' | 'part-time' | 'contract' | 'intern';
  status: 'draft' | 'open' | 'interviewing' | 'filled' | 'closed';
  description: string;
  requirements: string[];
  salaryRange?: string;
  applicants: number;
  postedDate?: string;
  createdAt: string;
}

export const useJobPostingStore = createLocalCrudStore<JobPosting>('singularity-jobs', [
  {
    id: 'job-1',
    title: 'Senior Full-Stack Engineer',
    department: 'Engineering',
    location: 'Remote',
    type: 'full-time',
    status: 'open',
    description: 'Build and maintain core platform infrastructure',
    requirements: ['5+ years experience', 'TypeScript/React', 'Node.js', 'PostgreSQL'],
    salaryRange: '$120k-$160k',
    applicants: 23,
    postedDate: '2026-02-15',
    createdAt: '2026-02-15T00:00:00Z',
  },
  {
    id: 'job-2',
    title: 'AI/ML Engineer',
    department: 'AI',
    location: 'Remote',
    type: 'full-time',
    status: 'interviewing',
    description: 'Design and implement autonomous agent systems',
    requirements: ['3+ years ML experience', 'Python', 'LLM fine-tuning', 'RAG systems'],
    salaryRange: '$140k-$180k',
    applicants: 45,
    postedDate: '2026-02-01',
    createdAt: '2026-02-01T00:00:00Z',
  },
]);

// ============================================================================
// Workflow Store
// ============================================================================

export interface WorkflowItem {
  id: string;
  name: string;
  description: string;
  status: 'active' | 'draft' | 'paused' | 'archived';
  trigger: string;
  steps: number;
  lastRun?: string;
  runCount: number;
  successRate: number;
  schedule?: string;
  createdAt: string;
}

export const useWorkflowStore = createLocalCrudStore<WorkflowItem>('singularity-workflows', [
  {
    id: 'wf-1',
    name: 'New Lead Onboarding',
    description: 'Automatically send welcome emails and assign to sales rep when new lead is created',
    status: 'active',
    trigger: 'Contact Created',
    steps: 4,
    lastRun: '2026-03-05T03:45:00Z',
    runCount: 156,
    successRate: 98.7,
    schedule: 'On trigger',
    createdAt: '2026-01-15T00:00:00Z',
  },
  {
    id: 'wf-2',
    name: 'Invoice Overdue Reminder',
    description: 'Send automated reminders for invoices past due date',
    status: 'active',
    trigger: 'Daily at 9:00 AM',
    steps: 3,
    lastRun: '2026-03-05T09:00:00Z',
    runCount: 45,
    successRate: 100,
    schedule: '0 9 * * *',
    createdAt: '2026-02-01T00:00:00Z',
  },
  {
    id: 'wf-3',
    name: 'Monthly Report Generation',
    description: 'Generate and distribute monthly financial and operational reports',
    status: 'active',
    trigger: '1st of every month',
    steps: 6,
    lastRun: '2026-03-01T00:00:00Z',
    runCount: 3,
    successRate: 100,
    schedule: '0 0 1 * *',
    createdAt: '2026-01-01T00:00:00Z',
  },
]);

// ============================================================================
// Dashboard (Analytics) Store
// ============================================================================

export interface AnalyticsDashboard {
  id: string;
  name: string;
  description: string;
  type: 'custom' | 'preset';
  widgets: number;
  lastViewed?: string;
  isDefault: boolean;
  createdAt: string;
}

export const useDashboardStore = createLocalCrudStore<AnalyticsDashboard>('singularity-dashboards', [
  { id: 'dash-1', name: 'Executive Overview', description: 'High-level KPIs and business metrics', type: 'preset', widgets: 8, lastViewed: '2026-03-05T04:00:00Z', isDefault: true, createdAt: '2026-01-01T00:00:00Z' },
  { id: 'dash-2', name: 'Sales Pipeline', description: 'Deal flow and conversion metrics', type: 'preset', widgets: 6, lastViewed: '2026-03-04T18:00:00Z', isDefault: false, createdAt: '2026-01-01T00:00:00Z' },
  { id: 'dash-3', name: 'Engineering Velocity', description: 'Sprint metrics, deployment frequency, incident response', type: 'custom', widgets: 5, lastViewed: '2026-03-03T12:00:00Z', isDefault: false, createdAt: '2026-02-15T00:00:00Z' },
]);

// ============================================================================
// Analytics Report Store
// ============================================================================

export interface AnalyticsReport {
  id: string;
  name: string;
  description: string;
  type: 'financial' | 'operational' | 'sales' | 'custom';
  schedule?: string;
  lastGenerated?: string;
  format: 'pdf' | 'csv' | 'xlsx';
  status: 'ready' | 'generating' | 'scheduled' | 'error';
  createdAt: string;
}

export const useReportStore = createLocalCrudStore<AnalyticsReport>('singularity-reports', [
  { id: 'rpt-1', name: 'Monthly Revenue Report', description: 'Detailed revenue breakdown by source and period', type: 'financial', schedule: 'Monthly', lastGenerated: '2026-03-01T00:00:00Z', format: 'pdf', status: 'ready', createdAt: '2026-01-01T00:00:00Z' },
  { id: 'rpt-2', name: 'Pipeline Health', description: 'Deal pipeline analysis and forecasting', type: 'sales', schedule: 'Weekly', lastGenerated: '2026-03-03T00:00:00Z', format: 'pdf', status: 'ready', createdAt: '2026-01-15T00:00:00Z' },
  { id: 'rpt-3', name: 'Operational Efficiency', description: 'Resource utilization and team performance', type: 'operational', lastGenerated: '2026-02-28T00:00:00Z', format: 'xlsx', status: 'ready', createdAt: '2026-02-01T00:00:00Z' },
]);

// ============================================================================
// Stakeholder Store
// ============================================================================

export interface Stakeholder {
  id: string;
  name: string;
  type: 'investor' | 'board' | 'partner' | 'advisor';
  organization?: string;
  email?: string;
  phone?: string;
  role?: string;
  investmentAmount?: number;
  equityPercent?: number;
  status: 'active' | 'inactive';
  notes?: string;
  joinDate: string;
  createdAt: string;
}

export const useStakeholderStore = createLocalCrudStore<Stakeholder>('singularity-stakeholders', [
  { id: 'sh-1', name: 'Ali Shakil', type: 'board', organization: 'Artifact Virtual', role: 'Founder & CEO', status: 'active', equityPercent: 100, joinDate: '2025-01-01', createdAt: '2025-01-01T00:00:00Z' },
]);

// ============================================================================
// Integration Store
// ============================================================================

export interface Integration {
  id: string;
  name: string;
  description: string;
  category: 'communication' | 'development' | 'analytics' | 'finance' | 'storage' | 'ai';
  status: 'connected' | 'disconnected' | 'error' | 'configuring';
  icon: string;
  lastSync?: string;
  config?: Record<string, string>;
  createdAt: string;
}

export const useIntegrationStore = createLocalCrudStore<Integration>('singularity-integrations', [
  { id: 'int-1', name: 'Discord', description: 'Team communication and bot commands', category: 'communication', status: 'connected', icon: 'MessageSquare', lastSync: '2026-03-05T04:30:00Z', createdAt: '2025-06-01T00:00:00Z' },
  { id: 'int-2', name: 'GitHub', description: 'Source code management and CI/CD', category: 'development', status: 'connected', icon: 'Github', lastSync: '2026-03-05T04:00:00Z', createdAt: '2025-06-01T00:00:00Z' },
  { id: 'int-3', name: 'PostgreSQL', description: 'Primary database', category: 'storage', status: 'connected', icon: 'Database', lastSync: '2026-03-05T04:30:00Z', createdAt: '2025-06-01T00:00:00Z' },
  { id: 'int-4', name: 'Cloudflare', description: 'CDN, DNS, and edge security', category: 'analytics', status: 'connected', icon: 'Cloud', lastSync: '2026-03-05T04:00:00Z', createdAt: '2025-08-01T00:00:00Z' },
  { id: 'int-5', name: 'Ollama', description: 'Local LLM inference engine', category: 'ai', status: 'connected', icon: 'Brain', lastSync: '2026-03-05T04:30:00Z', createdAt: '2025-12-01T00:00:00Z' },
  { id: 'int-6', name: 'Stripe', description: 'Payment processing', category: 'finance', status: 'disconnected', icon: 'CreditCard', createdAt: '2026-01-01T00:00:00Z' },
]);

// ============================================================================
// Infrastructure Server Store
// ============================================================================

export interface Server {
  id: string;
  name: string;
  hostname: string;
  ip?: string;
  type: 'physical' | 'vps' | 'container' | 'serverless';
  status: 'online' | 'offline' | 'maintenance' | 'degraded';
  os?: string;
  cpu?: string;
  ram?: string;
  disk?: string;
  cpuUsage?: number;
  ramUsage?: number;
  diskUsage?: number;
  uptime?: string;
  services: string[];
  location: string;
  createdAt: string;
}

export const useServerStore = createLocalCrudStore<Server>('singularity-servers', [
  {
    id: 'srv-1',
    name: 'qorvex',
    hostname: 'qorvex.local',
    ip: '192.168.1.100',
    type: 'physical',
    status: 'online',
    os: 'Ubuntu 24.04 LTS',
    cpu: 'AMD Ryzen 9',
    ram: '32GB',
    disk: '338GB NVMe',
    cpuUsage: 24,
    ramUsage: 52,
    diskUsage: 47,
    uptime: '45 days',
    services: ['singularity', 'comb-cloud', 'mach6-gateway', 'hektor', 'ollama', 'postgresql', 'nginx'],
    location: 'On-premise',
    createdAt: '2025-01-01T00:00:00Z',
  },
]);
