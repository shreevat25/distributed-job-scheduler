import React, { useEffect, useState } from 'react';
import api from '../api/client';
import { format, formatDistanceToNow } from 'date-fns';

const Workers = () => {
  const [workers, setWorkers] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchWorkers = async () => {
      try {
        const res = await api.get('/workers');
        setWorkers(res.data);
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    };
    
    fetchWorkers();
    const interval = setInterval(fetchWorkers, 5000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div>
      <div style={{ marginBottom: 32 }}>
        <h1>Workers</h1>
        <p className="text-muted">Manage and monitor distributed worker nodes.</p>
      </div>

      <div className="surface" style={{ borderRadius: 12, overflow: 'hidden' }}>
        <div className="table-container">
          {loading ? (
            <div className="loading-container"><div className="loader"></div></div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Worker Name</th>
                  <th>Hostname</th>
                  <th>Status</th>
                  <th>Concurrency</th>
                  <th>Started At</th>
                  <th>Last Seen</th>
                </tr>
              </thead>
              <tbody>
                {workers.map((w: any) => (
                  <tr key={w.id}>
                    <td style={{ fontWeight: 500 }}>{w.name}</td>
                    <td>{w.hostname}</td>
                    <td>
                      <span className={`badge badge-${w.status === 'online' ? 'success' : w.status === 'draining' ? 'warning' : 'danger'}`}>
                        {w.status}
                      </span>
                    </td>
                    <td>{w.concurrency}</td>
                    <td>{format(new Date(w.started_at), 'MMM d, HH:mm:ss')}</td>
                    <td>{formatDistanceToNow(new Date(w.last_seen_at), { addSuffix: true })}</td>
                  </tr>
                ))}
                {workers.length === 0 && (
                  <tr>
                    <td colSpan={6} style={{ textAlign: 'center', padding: 48, color: 'var(--text-muted)' }}>
                      No workers active.
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

export default Workers;
