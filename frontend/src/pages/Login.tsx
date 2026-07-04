import React, { useState } from 'react';
import api from '../api/client';
import { Server } from 'lucide-react';

const Login = ({ onLogin }: { onLogin: (token: string) => void }) => {
  const [isRegister, setIsRegister] = useState(false);
  const [formData, setFormData] = useState({ email: '', password: '' });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    
    try {
      if (isRegister) {
        await api.post('/auth/register', formData);
        setIsRegister(false);
        setFormData({ email: '', password: '' });
        alert('Registered successfully. Please login.');
      } else {
        const res = await api.post('/auth/login', {
          email: formData.email,
          password: formData.password
        });
        onLogin(res.data.access_token);
      }
    } catch (e: any) {
      setError(e.response?.data?.detail || 'An error occurred');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: 'flex', minHeight: '100vh', alignItems: 'center', justifyContent: 'center' }}>
      <div className="surface" style={{ width: 400, padding: 40, borderRadius: 16 }}>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', marginBottom: 32 }}>
          <div style={{ width: 48, height: 48, borderRadius: 12, background: 'var(--primary)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'white', marginBottom: 16 }}>
            <Server size={28} />
          </div>
          <h1 style={{ fontSize: '1.5rem', textAlign: 'center' }}>
            {isRegister ? 'Create Account' : 'Welcome Back'}
          </h1>
          <p className="text-muted" style={{ marginTop: 8 }}>
            Distributed Job Scheduler Platform
          </p>
        </div>

        {error && (
          <div style={{ padding: 12, background: 'rgba(239, 68, 68, 0.1)', color: 'var(--danger)', borderRadius: 8, marginBottom: 24, fontSize: '0.875rem' }}>
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>Email</label>
            <input 
              type="email" 
              value={formData.email} 
              onChange={e => setFormData({...formData, email: e.target.value})} 
              required 
            />
          </div>
          <div className="form-group">
            <label>Password</label>
            <input 
              type="password" 
              value={formData.password} 
              onChange={e => setFormData({...formData, password: e.target.value})} 
              required 
            />
          </div>
          
          <button 
            type="submit" 
            className="btn btn-primary" 
            style={{ width: '100%', marginTop: 24, padding: 12 }}
            disabled={loading}
          >
            {loading ? 'Processing...' : (isRegister ? 'Register' : 'Login')}
          </button>
        </form>

        <div style={{ marginTop: 24, textAlign: 'center', fontSize: '0.875rem' }}>
          <span className="text-muted">
            {isRegister ? 'Already have an account?' : "Don't have an account?"}
          </span>
          <button 
            type="button" 
            style={{ background: 'none', border: 'none', color: 'var(--primary)', cursor: 'pointer', marginLeft: 8, fontWeight: 500 }}
            onClick={() => setIsRegister(!isRegister)}
          >
            {isRegister ? 'Login' : 'Register'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default Login;
