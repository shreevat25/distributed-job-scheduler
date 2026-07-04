import React, { useEffect, useState } from 'react';
import api from '../api/client';
import { format } from 'date-fns';
import { RotateCw, Trash2 } from 'lucide-react';

const DLQ = () => {
  const [dlqEntries, setDlqEntries] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchDLQ = async () => {
    try {
      const res = await api.get('/dlq');
      setDlqEntries(res.data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDLQ();
  }, []);

  const handleRetry = async (id: string) => {
    try {
      await api.post(`/dlq/${id}/retry`);
      fetchDLQ();
    } catch (e) {
      console.error(e);
      alert('Failed to retry job');
    }
  };

  return (
    <div>
      <div style={{ marginBottom: 32 }}>
        <h1>Dead Letter Queue</h1>
        <p className="text-muted">Review and retry permanently failed jobs.</p>
      </div>

      <div className="surface" style={{ borderRadius: 12, overflow: 'hidden' }}>
        <div className="table-container">
          {loading ? (
            <div className="loading-container"><div className="loader"></div></div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Job ID</th>
                  <th>Dead-lettered At</th>
                  <th>Reason</th>
                  <th>Attempts</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {dlqEntries.map((entry: any) => (
                  <tr key={entry.id}>
                    <td style={{ fontFamily: 'monospace' }}>{entry.job_id.toString().substring(0, 8)}...</td>
                    <td>{format(new Date(entry.dead_lettered_at), 'MMM d, HH:mm:ss')}</td>
                    <td><span className="badge badge-danger">{entry.reason}</span></td>
                    <td>{entry.attempts}</td>
                    <td>
                      <button className="btn btn-primary" style={{ padding: '6px 12px' }} onClick={() => handleRetry(entry.id)}>
                        <RotateCw size={16} /> Retry
                      </button>
                    </td>
                  </tr>
                ))}
                {dlqEntries.length === 0 && (
                  <tr>
                    <td colSpan={5} style={{ textAlign: 'center', padding: 48, color: 'var(--text-muted)' }}>
                      No dead-lettered jobs. Awesome!
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

export default DLQ;
