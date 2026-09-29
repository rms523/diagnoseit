import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { IconLogo } from './Icons';
import { apiErrorMessage } from '../utils/apiErrors';
import { useRegistrationOpen } from '../utils/registration';

const AuthBrandPanel: React.FC = () => (
  <div className="auth-brand">
    <div className="auth-brand-content">
      <IconLogo size={36} />
      <h1 className="auth-brand-title" style={{ marginTop: 'var(--space-6)' }}>
        Start building your health timeline.
      </h1>
      <p className="auth-brand-text">
        Upload lab PDFs, log symptoms as they happen, and let DiagnoseIt
        connect the dots between your data points over time.
      </p>
    </div>
    <div className="auth-brand-demo">
      <div className="ref-range" style={{ maxWidth: 280 }}>
        <p className="eyebrow" style={{ color: 'rgba(247,245,240,0.5)', marginBottom: 'var(--space-3)' }}>
          Reference range
        </p>
        <div className="ref-range-track">
          <div className="ref-range-normal" style={{ left: '20%', width: '55%', background: 'rgba(74,124,89,0.35)' }} />
          <div className="ref-range-marker normal" style={{ left: '48%' }} />
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

const Register: React.FC = () => {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [formData, setFormData] = useState({
    username: '',
    email: '',
    first_name: '',
    last_name: '',
    password: '',
    password_confirm: '',
  });
  const [error, setError] = useState('');
  const registrationOpen = useRegistrationOpen();
  const [loading, setLoading] = useState(false);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (formData.password !== formData.password_confirm) {
      setError('Passwords do not match');
      return;
    }
    if (formData.password.length < 8) {
      setError('Password must be at least 8 characters');
      return;
    }
    setLoading(true);
    setError('');
    try {
      await register(formData);
      navigate('/');
    } catch (err) {
      setError(apiErrorMessage(err, 'Registration failed. Username or email may already be in use.'));
    } finally {
      setLoading(false);
    }
  };

  const passwordStrength = (() => {
    const p = formData.password;
    if (!p) return { level: 0, label: '', color: '' };
    let score = 0;
    if (p.length >= 8) score++;
    if (p.length >= 12) score++;
    if (/[A-Z]/.test(p) && /[a-z]/.test(p)) score++;
    if (/\d/.test(p)) score++;
    if (/[^A-Za-z0-9]/.test(p)) score++;
    if (score <= 1) return { level: 1, label: 'Weak', color: 'var(--coral)' };
    if (score <= 3) return { level: 2, label: 'Fair', color: 'var(--amber)' };
    return { level: 3, label: 'Strong', color: 'var(--sage)' };
  })();

  return (
    <div className="auth-page">
      <AuthBrandPanel />

      <div className="auth-panel">
        <div className="auth-card animate-scale-in" style={{ maxWidth: 440 }}>
          <div className="auth-header">
            <h1 className="auth-title">Create account</h1>
            <p className="auth-subtitle">Set up your health profile</p>
          </div>

          {error && (
            <div className="alert alert-error animate-shake" style={{ marginBottom: 'var(--space-4)' }}>
              {error}
            </div>
          )}

          {registrationOpen === false ? (
            <div className="alert alert-info">
              Sign-up is closed on this server. Ask its administrator to create an account for you.
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="auth-form">
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-4)' }}>
                <div className="form-group">
                  <label className="form-label" htmlFor="reg-fname">First name</label>
                  <input id="reg-fname" className="form-input" name="first_name" placeholder="John"
                    value={formData.first_name} onChange={handleChange} />
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="reg-lname">Last name</label>
                  <input id="reg-lname" className="form-input" name="last_name" placeholder="Doe"
                    value={formData.last_name} onChange={handleChange} />
                </div>
              </div>

              <div className="form-group">
                <label className="form-label" htmlFor="reg-username">Username</label>
                <input id="reg-username" className="form-input" name="username" placeholder="johndoe"
                  value={formData.username} onChange={handleChange} required />
              </div>

              <div className="form-group">
                <label className="form-label" htmlFor="reg-email">Email</label>
                <input id="reg-email" className="form-input" name="email" type="email" placeholder="john@example.com"
                  value={formData.email} onChange={handleChange} required />
              </div>

              <div className="form-group">
                <label className="form-label" htmlFor="reg-password">Password</label>
                <input id="reg-password" className="form-input" name="password" type="password"
                  placeholder="At least 8 characters" value={formData.password} onChange={handleChange} required />
                {formData.password && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', marginTop: '4px' }}>
                    <div style={{ flex: 1, height: 3, borderRadius: 2, background: 'var(--paper-muted)' }}>
                      <div style={{
                        width: `${(passwordStrength.level / 3) * 100}%`,
                        height: '100%',
                        borderRadius: 2,
                        background: passwordStrength.color,
                        transition: 'all 0.3s ease',
                      }} />
                    </div>
                    <span className="font-mono" style={{ fontSize: '0.6875rem', color: passwordStrength.color }}>
                      {passwordStrength.label}
                    </span>
                  </div>
                )}
              </div>

              <div className="form-group">
                <label className="form-label" htmlFor="reg-confirm">Confirm password</label>
                <input id="reg-confirm" className="form-input" name="password_confirm" type="password"
                  placeholder="Repeat password" value={formData.password_confirm} onChange={handleChange} required />
              </div>

              <button className="btn btn-primary btn-lg auth-submit" type="submit" disabled={loading}>
                {loading ? <><span className="spinner" /> Creating account…</> : 'Create account'}
              </button>
            </form>
          )}

          <p className="auth-footer">
            Already have an account? <Link to="/login">Sign in</Link>
          </p>
        </div>
      </div>
    </div>
  );
};

export default Register;
