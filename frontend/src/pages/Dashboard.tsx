import React, { useEffect, useState } from 'react';
import axios from 'axios';
import api from '../api/client';
import { Activity, Clock, AlertTriangle, CheckCircle, Server } from 'lucide-react';

const Dashboard = () => {
  const [stats, setStats] = useState({
    queues: 0,
    jobs: { running: 0, total_recent: 0 },
    workers: { online: 0, total: 0 },
    dlq: 0
  });
  const [health, setHealth] = useState({ api: 'Unknown' });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const pRes = await api.get('/projects');
        let queuesCount = 0;
        if (pRes.data.length > 0) {
          const targetProject = pRes.data[0].id;
          const qRes = await api.get(`/projects/${targetProject}/queues`);
          queuesCount = qRes.data.length;
        }

        const [jobsRes, workersRes, dlqRes, healthRes] = await Promise.all([
          api.get('/jobs?limit=50'),
          api.get('/workers'),
          api.get('/dlq'),
          axios.get('/health').catch(() => ({ data: { status: 'Error' } }))
        ]);
        
        const workers = workersRes.data;
        // jobs is a PaginatedResponse: { items: [...], total, page, limit }
        const jobItems: any[] = jobsRes.data.items ?? [];
        
        setStats({
          queues: queuesCount,
          jobs: { 
            running: jobItems.filter((j: any) => j.status === 'running').length,
            total_recent: jobItems.length
          },
          workers: {
            online: workers.filter((w: any) => w.status === 'online').length,
            total: workers.length
          },
          dlq: Array.isArray(dlqRes.data) ? dlqRes.data.length : 0
        });

        setHealth({ api: healthRes.data.status === 'ok' ? 'Operational' : 'Unavailable' });
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    };
    
    fetchStats();
    const interval = setInterval(fetchStats, 5000);
    return () => clearInterval(interval);
  }, []);

  if (loading) return <div className="loading-container"><div className="loader"></div></div>;

  return (
    <div>
      <div style={{ marginBottom: 32 }}>
        <h1>Dashboard</h1>
        <p className="text-muted">Overview of your distributed job scheduling platform.</p>
      </div>

      <div className="stats-grid" style={{ marginBottom: 32 }}>
        <div className="surface stat-card">
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span className="stat-title">Active Queues</span>
            <Server size={20} color="var(--primary)" />
          </div>
          <span className="stat-value">{stats.queues}</span>
        </div>
        
        <div className="surface stat-card">
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span className="stat-title">Workers Online</span>
            <Activity size={20} color="var(--success)" />
          </div>
          <span className="stat-value">{stats.workers.online} / {stats.workers.total}</span>
        </div>
        
        <div className="surface stat-card">
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span className="stat-title">Recent Jobs Running</span>
            <Clock size={20} color="var(--info)" />
          </div>
          <span className="stat-value">{stats.jobs.running}</span>
        </div>
        
        <div className="surface stat-card">
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span className="stat-title">DLQ Entries</span>
            <AlertTriangle size={20} color="var(--danger)" />
          </div>
          <span className="stat-value">{stats.dlq}</span>
        </div>
      </div>
      
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
        <div className="surface" style={{ padding: 24, borderRadius: 12 }}>
          <h3>System Health</h3>
          <div style={{ marginTop: 16, display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <div style={{ padding: 8, background: health.api === 'Operational' ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)', borderRadius: '50%' }}>
                {health.api === 'Operational' ? <CheckCircle size={20} color="var(--success)" /> : <AlertTriangle size={20} color="var(--danger)" />}
              </div>
              <div>
                <div style={{ fontWeight: 500 }}>API Gateway</div>
                <div className="text-sm text-muted">{health.api}</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
