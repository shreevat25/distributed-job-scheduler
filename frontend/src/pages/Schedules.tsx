import React, { useEffect, useState } from 'react';
import api from '../api/client';
import { format } from 'date-fns';
import { Play, Pause, Trash2 } from 'lucide-react';

const Schedules = () => {
  const [schedules, setSchedules] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [queues, setQueues] = useState([]);
  
  const [formData, setFormData] = useState({
    name: '',
    queue_id: '',
    job_type: 'echo',
    schedule_type: 'cron',
    cron_expression: '* * * * *',
    payload: '{}',
  });

  const fetchSchedules = async () => {
    try {
      const [schedRes, pRes] = await Promise.all([
        api.get('/schedules'),
        api.get('/projects')
      ]);
      setSchedules(schedRes.data);
      
      if (pRes.data.length > 0) {
        const targetProject = pRes.data[0].id;
        const qRes = await api.get(`/projects/${targetProject}/queues`);
        setQueues(qRes.data);
        if (qRes.data.length > 0 && !formData.queue_id) {
          setFormData(f => ({ ...f, queue_id: qRes.data[0].id }));
        }
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
    fetchSchedules();
  }, []);

  const handleToggle = async (id: string, currentActive: boolean) => {
    try {
      if (currentActive) {
        await api.post(`/schedules/${id}/pause`);
      } else {
        await api.post(`/schedules/${id}/resume`);
      }
      fetchSchedules();
    } catch (e) {
      console.error(e);
    }
  };

  const handleDelete = async (id: string) => {
    if (confirm('Delete this schedule?')) {
      try {
        await api.delete(`/schedules/${id}`);
        fetchSchedules();
      } catch (e) {
        console.error(e);
      }
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.post('/schedules', {
        ...formData,
        payload: JSON.parse(formData.payload)
      });
      setShowModal(false);
      fetchSchedules();
    } catch (e) {
      alert('Error creating schedule. Ensure JSON is valid and cron is correct.');
      console.error(e);
    }
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 32 }}>
        <div>
          <h1>Schedules</h1>
          <p className="text-muted">Manage recurring and one-time scheduled jobs.</p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowModal(true)}>
          Create Schedule
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
                  <th>Name</th>
                  <th>Type</th>
                  <th>Expression</th>
                  <th>Next Run</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {schedules.map((s: any) => (
                  <tr key={s.id}>
                    <td style={{ fontWeight: 500 }}>{s.name}</td>
                    <td>{s.schedule_type}</td>
                    <td style={{ fontFamily: 'monospace' }}>{s.cron_expression || 'N/A'}</td>
                    <td>{format(new Date(s.next_run_at), 'MMM d, HH:mm:ss')}</td>
                    <td>
                      <span className={`badge badge-${s.is_active ? 'success' : 'default'}`}>
                        {s.is_active ? 'Active' : 'Paused'}
                      </span>
                    </td>
                    <td>
                      <div style={{ display: 'flex', gap: 8 }}>
                        <button className="btn btn-outline" style={{ padding: 6 }} onClick={() => handleToggle(s.id, s.is_active)}>
                          {s.is_active ? <Pause size={16} /> : <Play size={16} />}
                        </button>
                        <button className="btn btn-danger" style={{ padding: 6 }} onClick={() => handleDelete(s.id)}>
                          <Trash2 size={16} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {schedules.length === 0 && (
                  <tr>
                    <td colSpan={6} style={{ textAlign: 'center', padding: 48, color: 'var(--text-muted)' }}>
                      No schedules defined yet.
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
            <h2>New Schedule</h2>
            <form onSubmit={handleSubmit} style={{ marginTop: 24 }}>
              <div className="form-group">
                <label>Name</label>
                <input value={formData.name} onChange={e => setFormData({...formData, name: e.target.value})} required />
              </div>
              <div className="form-group">
                <label>Queue</label>
                <select value={formData.queue_id} onChange={e => setFormData({...formData, queue_id: e.target.value})} required>
                  {queues.map((q: any) => <option key={q.id} value={q.id}>{q.name}</option>)}
                </select>
              </div>
              <div className="form-group">
                <label>Job Type</label>
                <input value={formData.job_type} onChange={e => setFormData({...formData, job_type: e.target.value})} required />
              </div>
              <div className="form-group">
                <label>Cron Expression</label>
                <input value={formData.cron_expression} onChange={e => setFormData({...formData, cron_expression: e.target.value})} required />
              </div>
              <div className="form-group">
                <label>Payload (JSON)</label>
                <textarea rows={3} value={formData.payload} onChange={e => setFormData({...formData, payload: e.target.value})} required />
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

export default Schedules;
