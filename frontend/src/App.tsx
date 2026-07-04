import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Link, useLocation } from 'react-router-dom';
import { LayoutDashboard, List, Server, AlertTriangle, Calendar, Settings, LogOut } from 'lucide-react';
import Dashboard from './pages/Dashboard';
import Jobs from './pages/Jobs';
import Queues from './pages/Queues';
import Workers from './pages/Workers';
import DLQ from './pages/DLQ';
import Schedules from './pages/Schedules';
import Login from './pages/Login';
import api from './api/client';

const App = () => {
  const [token, setToken] = useState(localStorage.getItem('token'));
  
  if (!token) {
    return <Login onLogin={(t) => {
      localStorage.setItem('token', t);
      setToken(t);
    }} />;
  }

  return (
    <Router>
      <div className="app-container">
        <Sidebar onLogout={() => {
          localStorage.removeItem('token');
          setToken(null);
        }} />
        <main className="main-content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/jobs" element={<Jobs />} />
            <Route path="/queues" element={<Queues />} />
            <Route path="/workers" element={<Workers />} />
            <Route path="/dlq" element={<DLQ />} />
            <Route path="/schedules" element={<Schedules />} />
          </Routes>
        </main>
      </div>
    </Router>
  );
};

const Sidebar = ({ onLogout }: { onLogout: () => void }) => {
  const location = useLocation();
  const navItems = [
    { path: '/', icon: <LayoutDashboard size={20} />, label: 'Dashboard' },
    { path: '/jobs', icon: <List size={20} />, label: 'Jobs' },
    { path: '/queues', icon: <Server size={20} />, label: 'Queues' },
    { path: '/workers', icon: <Settings size={20} />, label: 'Workers' },
    { path: '/dlq', icon: <AlertTriangle size={20} />, label: 'DLQ' },
    { path: '/schedules', icon: <Calendar size={20} />, label: 'Schedules' },
  ];

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <div style={{ width: 32, height: 32, borderRadius: 8, background: 'var(--primary)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'white' }}>
          <Server size={20} />
        </div>
        DJS Platform
      </div>
      
      <nav style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 8 }}>
        {navItems.map((item) => (
          <Link 
            key={item.path} 
            to={item.path} 
            className={`nav-item ${location.pathname === item.path ? 'active' : ''}`}
          >
            {item.icon}
            {item.label}
          </Link>
        ))}
      </nav>
      
      <button className="nav-item" style={{ background: 'transparent', border: 'none', cursor: 'pointer', textAlign: 'left' }} onClick={onLogout}>
        <LogOut size={20} />
        Logout
      </button>
    </aside>
  );
};

export default App;
