import React, { useEffect, useState } from 'react';
import api from '../api/client';
import { format } from 'date-fns';

const Jobs = () => {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('');

  useEffect(() => {
    const fetchJobs = async () => {
      try {
        const url = statusFilter ? `/jobs?status=${statusFilter}&limit=50` : `/jobs?limit=50`;
        const res = await api.get(url);
        setJobs(res.data.items ?? []);
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    };
    
    fetchJobs();
    const interval = setInterval(fetchJobs, 5000);
    return () => clearInterval(interval);
  }, [statusFilter]);

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 32 }}>
        <div>
          <h1>Jobs</h1>
          <p className="text-muted">Monitor and inspect job executions.</p>
        </div>
        
        <div style={{ display: 'flex', gap: 12 }}>
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="">All Statuses</option>
            <option value="queued">Queued</option>
            <option value="claimed">Claimed</option>
            <option value="running">Running</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
            <option value="cancelled">Cancelled</option>
          </select>
        </div>
      </div>

      <div className="surface" style={{ borderRadius: 12, overflow: 'hidden' }}>
        <div className="table-container">
          {loading && jobs.length === 0 ? (
            <div className="loading-container"><div className="loader"></div></div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Job ID</th>
                  <th>Type</th>
                  <th>Status</th>
                  <th>Queue</th>
                  <th>Attempts</th>
                  <th>Available At</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job: any) => (
                  <tr key={job.id}>
                    <td style={{ fontFamily: 'monospace' }}>{job.id.substring(0, 8)}...</td>
                    <td>{job.type}</td>
                    <td>
                      <span className={`badge badge-${job.status === 'completed' ? 'success' : job.status === 'failed' ? 'danger' : job.status === 'running' ? 'info' : 'default'}`}>
                        {job.status}
                      </span>
                    </td>
                    <td style={{ fontFamily: 'monospace' }}>{job.queue_id.substring(0, 8)}...</td>
                    <td>{job.attempt_count} / {job.max_attempts}</td>
                    <td>{format(new Date(job.available_at), 'MMM d, HH:mm:ss')}</td>
                  </tr>
                ))}
                {jobs.length === 0 && (
                  <tr>
                    <td colSpan={6} style={{ textAlign: 'center', padding: 48, color: 'var(--text-muted)' }}>
                      No jobs found matching criteria.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
};

export default Jobs;
