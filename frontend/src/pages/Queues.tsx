import React, { useEffect, useState } from 'react';
import api from '../api/client';
import { format } from 'date-fns';

const Queues = () => {
  const [queues, setQueues] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [projects, setProjects] = useState([]);
  const [formData, setFormData] = useState({ name: '', project_id: '', concurrency_limit: 10 });

  const fetchQueues = async (selectedProjectId?: string) => {
    try {
      const pRes = await api.get('/projects');
      setProjects(pRes.data);
      
      const targetProject = selectedProjectId || (pRes.data.length > 0 ? pRes.data[0].id : null);
      if (targetProject) {
        if (!formData.project_id) {
          setFormData(f => ({ ...f, project_id: targetProject }));
        }
        const qRes = await api.get(`/projects/${targetProject}/queues`);
        setQueues(qRes.data);
      } else {
        setQueues([]);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchQueues();
  }, []);

  const handleToggle = async (id: string, isPaused: boolean) => {
    try {
      if (isPaused) {
        await api.post(`/queues/${id}/resume`);
      } else {
        await api.post(`/queues/${id}/pause`);
      }
      fetchQueues(formData.project_id);
    } catch (e) {
      console.error(e);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.post(`/projects/${formData.project_id}/queues`, formData);
      setShowModal(false);
      fetchQueues(formData.project_id);
    } catch (e) {
      alert('Error creating queue');
    }
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 32 }}>
        <div>
          <h1>Queues</h1>
          <p className="text-muted">Manage job queues and concurrency limits.</p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowModal(true)}>
          Create Queue
        </button>
      </div>

      <div className="surface" style={{ borderRadius: 12, overflow: 'hidden' }}>
        <div className="table-container">
          {loading ? (
            <div className="loading-container"><div className="loader"></div></div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Queue Name</th>
                  <th>ID</th>
                  <th>Concurrency Limit</th>
                  <th>Status</th>
                  <th>Created At</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {queues.map((q: any) => (
                  <tr key={q.id}>
                    <td style={{ fontWeight: 500 }}>{q.name}</td>
                    <td style={{ fontFamily: 'monospace' }}>{q.id.substring(0, 8)}...</td>
                    <td>{q.concurrency_limit}</td>
                    <td>
                      <span className={`badge badge-${q.is_paused ? 'warning' : 'success'}`}>
                        {q.is_paused ? 'Paused' : 'Active'}
                      </span>
                    </td>
                    <td>{format(new Date(q.created_at), 'MMM d, yyyy')}</td>
                    <td>
                      <button className="btn btn-outline" onClick={() => handleToggle(q.id, q.is_paused)}>
                        {q.is_paused ? 'Resume' : 'Pause'}
                      </button>
                    </td>
                  </tr>
                ))}
                {queues.length === 0 && (
                  <tr>
                    <td colSpan={6} style={{ textAlign: 'center', padding: 48, color: 'var(--text-muted)' }}>
                      No queues found. Create one to get started.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {showModal && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, backdropFilter: 'blur(4px)' }}>
          <div className="surface" style={{ width: 400, padding: 32, borderRadius: 12 }}>
            <h2>New Queue</h2>
            <form onSubmit={handleSubmit} style={{ marginTop: 24 }}>
              <div className="form-group">
                <label>Queue Name</label>
                <input value={formData.name} onChange={e => setFormData({...formData, name: e.target.value})} required />
              </div>
              <div className="form-group">
                <label>Project</label>
                <select value={formData.project_id} onChange={e => setFormData({...formData, project_id: e.target.value})} required>
                  {projects.map((p: any) => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
              </div>
              <div className="form-group">
                <label>Concurrency Limit</label>
                <input type="number" min={1} max={100} value={formData.concurrency_limit} onChange={e => setFormData({...formData, concurrency_limit: parseInt(e.target.value)})} required />
              </div>
              
              <div style={{ display: 'flex', gap: 12, marginTop: 24, justifyContent: 'flex-end' }}>
                <button type="button" className="btn btn-outline" onClick={() => setShowModal(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary">Create</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default Queues;
