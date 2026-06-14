/**
 * Infrastructure Module
 * Server monitoring, service status, and system health
 * Pulls real data from backend health endpoint + localStorage for configuration
 */

import { useState, useEffect, useCallback } from 'react';
import { Routes, Route, Link } from 'react-router-dom';
import {
  Server,
  Activity,
  CheckCircle,
  AlertCircle,
  XCircle,
  RefreshCw,
  Clock,
  Cpu,
  HardDrive,
  Wifi,
  Globe,
  Shield,
  Plus,
  Edit,
  Trash2,
  X,
  Save,
  ExternalLink,
} from 'lucide-react';
import { cn } from '@shared/utils';

// Types
interface ServiceCheck {
  name: string;
  url: string;
  expectedStatus?: number;
  status: 'online' | 'offline' | 'checking' | 'unknown';
  responseTime?: number;
  lastChecked?: Date;
  error?: string;
}

interface MonitoredService {
  id: string;
  name: string;
  url: string;
  expectedStatus: number;
  type: 'internal' | 'external';
  description: string;
}

// Persistence
function loadServices(): MonitoredService[] {
  try {
    const stored = localStorage.getItem('singularity-infra-services');
    if (stored) return JSON.parse(stored);
  } catch {}
  return [
    { id: '1', name: 'Singularity API', url: '/api/health', expectedStatus: 200, type: 'internal', description: 'Backend API server' },
    { id: '2', name: 'COMB Cloud', url: 'https://comb-cloud.artifactvirtual.com/health', expectedStatus: 200, type: 'external', description: 'Cloud memory service' },
    { id: '3', name: 'Qorvex', url: 'https://gladius.artifactvirtual.com', expectedStatus: 200, type: 'external', description: 'Frontend application' },
    { id: '4', name: 'Mach6 Gateway', url: 'https://mach6.artifactvirtual.com', expectedStatus: 200, type: 'external', description: 'API gateway' },
  ];
}

function saveServices(services: MonitoredService[]) {
  localStorage.setItem('singularity-infra-services', JSON.stringify(services));
}

function generateId() {
  return `svc-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
}

const inputClass = "w-full h-9 px-3 rounded-md border border-input bg-background text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring";

// Infrastructure Overview
function InfraOverview() {
  const [services, setServices] = useState<MonitoredService[]>(loadServices);
  const [checks, setChecks] = useState<Map<string, ServiceCheck>>(new Map());
  const [isChecking, setIsChecking] = useState(false);
  const [lastFullCheck, setLastFullCheck] = useState<Date | null>(null);

  const checkService = useCallback(async (service: MonitoredService): Promise<ServiceCheck> => {
    const check: ServiceCheck = {
      name: service.name,
      url: service.url,
      expectedStatus: service.expectedStatus,
      status: 'checking',
    };

    try {
      const start = performance.now();
      const response = await fetch(service.url, {
        method: 'GET',
        signal: AbortSignal.timeout(10000),
      });
      const elapsed = Math.round(performance.now() - start);

      check.responseTime = elapsed;
      check.lastChecked = new Date();
      check.status = response.status === service.expectedStatus ? 'online' : 'offline';
      if (check.status === 'offline') {
        check.error = `Expected ${service.expectedStatus}, got ${response.status}`;
      }
    } catch (err) {
      check.status = 'offline';
      check.lastChecked = new Date();
      check.error = err instanceof Error ? err.message : 'Connection failed';
    }

    return check;
  }, []);

  const runAllChecks = useCallback(async () => {
    setIsChecking(true);
    const results = new Map<string, ServiceCheck>();
    
    // Set all to checking first
    services.forEach(s => {
      results.set(s.id, { name: s.name, url: s.url, status: 'checking' });
    });
    setChecks(new Map(results));

    // Run checks in parallel
    await Promise.all(
      services.map(async (service) => {
        const result = await checkService(service);
        results.set(service.id, result);
        setChecks(new Map(results));
      })
    );

    setLastFullCheck(new Date());
    setIsChecking(false);
  }, [services, checkService]);

  useEffect(() => {
    runAllChecks();
    const interval = setInterval(runAllChecks, 60000); // Auto-refresh every 60s
    return () => clearInterval(interval);
  }, [runAllChecks]);

  const onlineCount = Array.from(checks.values()).filter(c => c.status === 'online').length;
  const offlineCount = Array.from(checks.values()).filter(c => c.status === 'offline').length;
  const avgResponseTime = Array.from(checks.values())
    .filter(c => c.responseTime)
    .reduce((sum, c, _, arr) => sum + (c.responseTime || 0) / arr.length, 0);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-primary/10">
            <Server className="h-6 w-6 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-foreground">Infrastructure</h1>
            <p className="text-muted-foreground">System health and service monitoring</p>
          </div>
        </div>
        <button
          onClick={runAllChecks}
          disabled={isChecking}
          className="h-9 px-4 rounded-md border border-input bg-background text-foreground text-sm font-medium hover:bg-accent flex items-center gap-2 disabled:opacity-50"
        >
          <RefreshCw className={cn('h-4 w-4', isChecking && 'animate-spin')} />
          {isChecking ? 'Checking...' : 'Refresh'}
        </button>
      </div>

      {/* Summary cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <div className="rounded-lg border border-border bg-card p-6">
          <div className="flex items-center gap-2 mb-2">
            <CheckCircle className="h-5 w-5 text-green-600" />
            <span className="text-sm font-medium text-muted-foreground">Online</span>
          </div>
          <p className="text-2xl font-bold text-foreground">{onlineCount}</p>
          <p className="text-xs text-muted-foreground">services healthy</p>
        </div>
        <div className="rounded-lg border border-border bg-card p-6">
          <div className="flex items-center gap-2 mb-2">
            <XCircle className="h-5 w-5 text-red-600" />
            <span className="text-sm font-medium text-muted-foreground">Offline</span>
          </div>
          <p className="text-2xl font-bold text-foreground">{offlineCount}</p>
          <p className="text-xs text-muted-foreground">services down</p>
        </div>
        <div className="rounded-lg border border-border bg-card p-6">
          <div className="flex items-center gap-2 mb-2">
            <Activity className="h-5 w-5 text-blue-600" />
            <span className="text-sm font-medium text-muted-foreground">Avg Response</span>
          </div>
          <p className="text-2xl font-bold text-foreground">{Math.round(avgResponseTime)}ms</p>
          <p className="text-xs text-muted-foreground">across all services</p>
        </div>
        <div className="rounded-lg border border-border bg-card p-6">
          <div className="flex items-center gap-2 mb-2">
            <Clock className="h-5 w-5 text-purple-600" />
            <span className="text-sm font-medium text-muted-foreground">Last Check</span>
          </div>
          <p className="text-2xl font-bold text-foreground">
            {lastFullCheck ? `${Math.round((Date.now() - lastFullCheck.getTime()) / 1000)}s` : '—'}
          </p>
          <p className="text-xs text-muted-foreground">ago (auto-refresh 60s)</p>
        </div>
      </div>

      {/* Service status table */}
      <div className="rounded-lg border border-border bg-card overflow-hidden">
        <div className="px-6 py-4 border-b border-border flex items-center justify-between">
          <h2 className="font-semibold text-foreground">Service Status</h2>
          <Link to="/infrastructure/services" className="text-sm text-primary hover:underline flex items-center gap-1">
            Manage Services <ExternalLink className="h-3 w-3" />
          </Link>
        </div>
        <table className="w-full">
          <thead className="bg-muted/50">
            <tr>
              <th className="text-left p-4 text-sm font-medium text-muted-foreground">Service</th>
              <th className="text-left p-4 text-sm font-medium text-muted-foreground">Status</th>
              <th className="text-left p-4 text-sm font-medium text-muted-foreground">Response Time</th>
              <th className="text-left p-4 text-sm font-medium text-muted-foreground">Type</th>
              <th className="text-left p-4 text-sm font-medium text-muted-foreground">Last Checked</th>
            </tr>
          </thead>
          <tbody>
            {services.map((service) => {
              const check = checks.get(service.id);
              return (
                <tr key={service.id} className="border-t border-border hover:bg-muted/30">
                  <td className="p-4">
                    <div>
                      <p className="font-medium text-foreground">{service.name}</p>
                      <p className="text-xs text-muted-foreground">{service.description}</p>
                    </div>
                  </td>
                  <td className="p-4">
                    <div className="flex items-center gap-2">
                      {check?.status === 'online' && <CheckCircle className="h-4 w-4 text-green-600" />}
                      {check?.status === 'offline' && <XCircle className="h-4 w-4 text-red-600" />}
                      {check?.status === 'checking' && <RefreshCw className="h-4 w-4 text-blue-600 animate-spin" />}
                      {!check && <AlertCircle className="h-4 w-4 text-muted-foreground" />}
                      <span className={cn(
                        'text-xs px-2 py-1 rounded-full',
                        check?.status === 'online' && 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
                        check?.status === 'offline' && 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
                        check?.status === 'checking' && 'bg-blue-100 text-blue-800',
                        !check && 'bg-muted text-muted-foreground',
                      )}>
                        {check?.status || 'pending'}
                      </span>
                    </div>
                    {check?.error && <p className="text-xs text-destructive mt-1">{check.error}</p>}
                  </td>
                  <td className="p-4 font-mono text-sm text-foreground">
                    {check?.responseTime ? `${check.responseTime}ms` : '—'}
                  </td>
                  <td className="p-4">
                    <span className={cn(
                      'text-xs px-2 py-1 rounded-full',
                      service.type === 'internal' ? 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200' : 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200'
                    )}>
                      {service.type}
                    </span>
                  </td>
                  <td className="p-4 text-sm text-muted-foreground">
                    {check?.lastChecked ? check.lastChecked.toLocaleTimeString() : '—'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Overall status banner */}
      {!isChecking && checks.size > 0 && (
        <div className={cn(
          'rounded-lg border p-4 flex items-center gap-3',
          offlineCount === 0 ? 'bg-green-50 border-green-200 dark:bg-green-950 dark:border-green-800' : 'bg-red-50 border-red-200 dark:bg-red-950 dark:border-red-800'
        )}>
          {offlineCount === 0 ? (
            <>
              <CheckCircle className="h-5 w-5 text-green-600" />
              <span className="font-medium text-green-800 dark:text-green-200">All systems operational</span>
            </>
          ) : (
            <>
              <AlertCircle className="h-5 w-5 text-red-600" />
              <span className="font-medium text-red-800 dark:text-red-200">{offlineCount} service{offlineCount > 1 ? 's' : ''} experiencing issues</span>
            </>
          )}
        </div>
      )}
    </div>
  );
}

// Services Management Page
function ServicesPage() {
  const [services, setServices] = useState<MonitoredService[]>(loadServices);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<MonitoredService | null>(null);
  const [form, setForm] = useState({ name: '', url: '', expectedStatus: '200', type: 'internal' as 'internal' | 'external', description: '' });

  const handleSave = () => {
    const entry: MonitoredService = {
      id: editing?.id || generateId(),
      name: form.name,
      url: form.url,
      expectedStatus: parseInt(form.expectedStatus) || 200,
      type: form.type,
      description: form.description,
    };
    const updated = editing ? services.map(s => s.id === editing.id ? entry : s) : [...services, entry];
    setServices(updated);
    saveServices(updated);
    setShowForm(false);
    setEditing(null);
    setForm({ name: '', url: '', expectedStatus: '200', type: 'internal', description: '' });
  };

  const handleDelete = (id: string) => {
    const updated = services.filter(s => s.id !== id);
    setServices(updated);
    saveServices(updated);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-primary/10"><Globe className="h-6 w-6 text-primary" /></div>
          <div>
            <h1 className="text-2xl font-bold text-foreground">Managed Services</h1>
            <p className="text-muted-foreground">Configure endpoints to monitor</p>
          </div>
        </div>
        <button onClick={() => { setEditing(null); setForm({ name: '', url: '', expectedStatus: '200', type: 'internal', description: '' }); setShowForm(true); }} className="h-10 px-4 rounded-md bg-primary text-primary-foreground font-medium hover:bg-primary/90 flex items-center gap-2">
          <Plus className="h-4 w-4" />Add Service
        </button>
      </div>

      <div className="rounded-lg border border-border bg-card overflow-hidden">
        <table className="w-full">
          <thead className="bg-muted/50">
            <tr>
              <th className="text-left p-4 text-sm font-medium text-muted-foreground">Service</th>
              <th className="text-left p-4 text-sm font-medium text-muted-foreground">URL</th>
              <th className="text-left p-4 text-sm font-medium text-muted-foreground">Expected Status</th>
              <th className="text-left p-4 text-sm font-medium text-muted-foreground">Type</th>
              <th className="text-left p-4 text-sm font-medium text-muted-foreground">Actions</th>
            </tr>
          </thead>
          <tbody>
            {services.map((service) => (
              <tr key={service.id} className="border-t border-border hover:bg-muted/30">
                <td className="p-4">
                  <p className="font-medium text-foreground">{service.name}</p>
                  <p className="text-xs text-muted-foreground">{service.description}</p>
                </td>
                <td className="p-4 font-mono text-sm text-muted-foreground">{service.url}</td>
                <td className="p-4 text-foreground">{service.expectedStatus}</td>
                <td className="p-4">
                  <span className={cn('text-xs px-2 py-1 rounded-full', service.type === 'internal' ? 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200' : 'bg-purple-100 text-purple-800')}>
                    {service.type}
                  </span>
                </td>
                <td className="p-4">
                  <div className="flex gap-1">
                    <button onClick={() => { setForm({ name: service.name, url: service.url, expectedStatus: String(service.expectedStatus), type: service.type, description: service.description }); setEditing(service); setShowForm(true); }} className="p-1.5 rounded hover:bg-accent"><Edit className="h-4 w-4 text-muted-foreground" /></button>
                    <button onClick={() => handleDelete(service.id)} className="p-1.5 rounded hover:bg-accent"><Trash2 className="h-4 w-4 text-destructive" /></button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-card border border-border rounded-lg shadow-xl w-full max-w-lg mx-4">
            <div className="flex items-center justify-between p-4 border-b border-border">
              <h3 className="font-semibold text-foreground">{editing ? 'Edit Service' : 'Add Service'}</h3>
              <button onClick={() => setShowForm(false)} className="p-1 rounded hover:bg-accent"><X className="h-4 w-4" /></button>
            </div>
            <div className="p-4 space-y-4">
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-foreground">Name</label>
                <input className={inputClass} value={form.name} onChange={e => setForm(f => ({...f, name: e.target.value}))} placeholder="e.g., Production API" />
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-foreground">URL</label>
                <input className={inputClass} value={form.url} onChange={e => setForm(f => ({...f, url: e.target.value}))} placeholder="https://api.example.com/health" />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-sm font-medium text-foreground">Expected Status</label>
                  <input className={inputClass} type="number" value={form.expectedStatus} onChange={e => setForm(f => ({...f, expectedStatus: e.target.value}))} />
                </div>
                <div className="space-y-1.5">
                  <label className="text-sm font-medium text-foreground">Type</label>
                  <select className={inputClass} value={form.type} onChange={e => setForm(f => ({...f, type: e.target.value as 'internal' | 'external'}))}>
                    <option value="internal">Internal</option>
                    <option value="external">External</option>
                  </select>
                </div>
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-foreground">Description</label>
                <input className={inputClass} value={form.description} onChange={e => setForm(f => ({...f, description: e.target.value}))} placeholder="Brief description" />
              </div>
            </div>
            <div className="flex justify-end gap-2 p-4 border-t border-border">
              <button onClick={() => setShowForm(false)} className="h-9 px-4 rounded-md border border-input bg-background text-foreground text-sm hover:bg-accent">Cancel</button>
              <button onClick={handleSave} className="h-9 px-4 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 flex items-center gap-2">
                <Save className="h-4 w-4" />Save
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// Monitoring Page
function MonitoringPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="p-2 rounded-lg bg-primary/10"><Activity className="h-6 w-6 text-primary" /></div>
        <div>
          <h1 className="text-2xl font-bold text-foreground">Monitoring</h1>
          <p className="text-muted-foreground">Real-time system monitoring</p>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-lg border border-border bg-card p-6">
          <div className="flex items-center gap-2 mb-4">
            <Cpu className="h-5 w-5 text-blue-600" />
            <h3 className="font-semibold text-foreground">System Resources</h3>
          </div>
          <div className="space-y-4">
            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-muted-foreground">CPU Usage</span>
                <span className="font-medium text-foreground">—</span>
              </div>
              <div className="h-2 rounded-full bg-muted" />
            </div>
            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-muted-foreground">Memory Usage</span>
                <span className="font-medium text-foreground">—</span>
              </div>
              <div className="h-2 rounded-full bg-muted" />
            </div>
            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-muted-foreground">Disk Usage</span>
                <span className="font-medium text-foreground">—</span>
              </div>
              <div className="h-2 rounded-full bg-muted" />
            </div>
          </div>
          <p className="text-xs text-muted-foreground mt-4 flex items-center gap-1">
            <Shield className="h-3 w-3" />
            System metrics require a monitoring agent endpoint
          </p>
        </div>

        <div className="rounded-lg border border-border bg-card p-6">
          <div className="flex items-center gap-2 mb-4">
            <Wifi className="h-5 w-5 text-green-600" />
            <h3 className="font-semibold text-foreground">Network</h3>
          </div>
          <div className="space-y-3 text-sm">
            <div className="flex justify-between py-2 border-b border-border">
              <span className="text-muted-foreground">Uptime Checks</span>
              <span className="font-medium text-foreground">Every 60s</span>
            </div>
            <div className="flex justify-between py-2 border-b border-border">
              <span className="text-muted-foreground">Monitored Endpoints</span>
              <span className="font-medium text-foreground">{loadServices().length}</span>
            </div>
            <div className="flex justify-between py-2">
              <span className="text-muted-foreground">Alert Channel</span>
              <span className="font-medium text-foreground">In-app notifications</span>
            </div>
          </div>
          <p className="text-xs text-muted-foreground mt-4">
            Add endpoints in <Link to="/infrastructure/services" className="text-primary hover:underline">Services</Link> to monitor them
          </p>
        </div>
      </div>
    </div>
  );
}

// Servers Page
function ServersPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="p-2 rounded-lg bg-primary/10"><HardDrive className="h-6 w-6 text-primary" /></div>
        <div>
          <h1 className="text-2xl font-bold text-foreground">Servers</h1>
          <p className="text-muted-foreground">Server inventory and management</p>
        </div>
      </div>

      <div className="rounded-lg border border-border bg-card p-6">
        <div className="flex items-center gap-3 p-4 rounded-lg bg-muted/50">
          <Server className="h-8 w-8 text-primary" />
          <div>
            <h3 className="font-semibold text-foreground">Production Server</h3>
            <p className="text-sm text-muted-foreground">Hosts Singularity ERP, COMB Cloud, Mach6 Gateway, Qorvex</p>
          </div>
          <CheckCircle className="h-5 w-5 text-green-600 ml-auto" />
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4 text-sm">
          <div className="p-3 rounded-lg border border-border">
            <p className="text-muted-foreground">OS</p>
            <p className="font-medium text-foreground">Ubuntu Server</p>
          </div>
          <div className="p-3 rounded-lg border border-border">
            <p className="text-muted-foreground">Runtime</p>
            <p className="font-medium text-foreground">Node.js + Python</p>
          </div>
          <div className="p-3 rounded-lg border border-border">
            <p className="text-muted-foreground">Database</p>
            <p className="font-medium text-foreground">PostgreSQL</p>
          </div>
          <div className="p-3 rounded-lg border border-border">
            <p className="text-muted-foreground">Proxy</p>
            <p className="font-medium text-foreground">Nginx + Cloudflare</p>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function Infrastructure() {
  return (
    <Routes>
      <Route index element={<InfraOverview />} />
      <Route path="servers/*" element={<ServersPage />} />
      <Route path="services/*" element={<ServicesPage />} />
      <Route path="monitoring/*" element={<MonitoringPage />} />
    </Routes>
  );
}
