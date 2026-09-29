import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { IconLogo } from './Icons';
import { useRegistrationOpen } from '../utils/registration';

const AuthBrandPanel: React.FC = () => (
  <div className="auth-brand">
    <div className="auth-brand-content">
      <IconLogo size={36} />
      <h1 className="auth-brand-title" style={{ marginTop: 'var(--space-6)' }}>
        Your health records, readable at a glance.
      </h1>
      <p className="auth-brand-text">
        DiagnoseIt parses lab reports, tracks symptoms, and surfaces what matters —
        so you walk into appointments knowing your numbers.
      </p>
    </div>
    <div className="auth-brand-demo">
      <div className="ref-range" style={{ maxWidth: 280 }}>
        <p className="eyebrow" style={{ color: 'rgba(247,245,240,0.5)', marginBottom: 'var(--space-3)' }}>
          Reference range
        </p>
        <div className="ref-range-track">
          <div className="ref-range-normal" style={{ left: '20%', width: '55%', background: 'rgba(74,124,89,0.35)' }} />
          <div className="ref-range-marker high" style={{ left: '78%' }} />
        </div>
        <div className="ref-range-labels" style={{ color: 'rgba(247,245,240,0.4)' }}>
          <span>Low</span>
          <span>Normal</span>
          <span>High</span>
        </div>
      </div>
    </div>
  </div>
);

const Login: React.FC = () => {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [formData, setFormData] = useState({ username: '', password: '' });
  const registrationOpen = useRegistrationOpen();
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      await login(formData.username, formData.password);
      navigate('/');
    } catch {
      setError('Invalid username or password');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <AuthBrandPanel />

      <div className="auth-panel">
        <div className="auth-card animate-scale-in">
          <div className="auth-header">
            <h1 className="auth-title">Sign in</h1>
            <p className="auth-subtitle">Access your health dashboard</p>
          </div>

          {error && (
            <div className="alert alert-error animate-shake" style={{ marginBottom: 'var(--space-5)' }}>
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="auth-form">
            <div className="form-group">
              <label className="form-label" htmlFor="login-username">Username</label>
              <input
                id="login-username"
                className="form-input"
                name="username"
                type="text"
                placeholder="Your username"
                value={formData.username}
                onChange={handleChange}
                required
                autoFocus
              />
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="login-password">Password</label>
              <input
                id="login-password"
                className="form-input"
                name="password"
                type="password"
                placeholder="Your password"
                value={formData.password}
                onChange={handleChange}
                required
              />
            </div>
            <button className="btn btn-primary btn-lg auth-submit" type="submit" disabled={loading}>
              {loading ? <><span className="spinner" /> Signing in…</> : 'Sign in'}
            </button>
          </form>

          <p className="auth-footer">
            {registrationOpen === false
              ? "Need an account? Ask this server's administrator."
              : <>No account yet? <Link to="/register">Create one</Link></>}
          </p>
        </div>
      </div>
    </div>
  );
};

export default Login;
