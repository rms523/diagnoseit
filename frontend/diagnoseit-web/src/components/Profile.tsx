import React, { useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { IconCheck, IconEdit, IconLogout } from './Icons';

const Profile: React.FC = () => {
  const { user, updateUser, logout } = useAuth();
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({
    first_name: user?.first_name || '',
    last_name: user?.last_name || '',
    email: user?.email || '',
    phone_number: user?.phone_number || '',
    emergency_contact: user?.emergency_contact || '',
    emergency_phone: user?.emergency_phone || '',
  });
  const [saving, setSaving] = useState(false);
  const [success, setSuccess] = useState('');
  const [error, setError] = useState('');

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    setSuccess('');
    try {
      await updateUser(form);
      setEditing(false);
      setSuccess('Profile updated successfully');
      setTimeout(() => setSuccess(''), 3000);
    } catch {
      setError('Failed to update profile');
    } finally {
      setSaving(false);
    }
  };

  if (!user) return null;

  return (
    <div className="animate-fade-in" style={{ maxWidth: 640 }}>
      <div className="page-header">
        <div>
          <h1 className="page-title">Profile</h1>
          <p className="page-subtitle">Manage your account information</p>
        </div>
      </div>

      {success && <div className="alert alert-success" style={{ marginBottom: 'var(--space-4)' }}>{success}</div>}
      {error && <div className="alert alert-error" style={{ marginBottom: 'var(--space-4)' }}>{error}</div>}

      {/* Profile Card */}
      <div className="card" style={{ marginBottom: 'var(--space-6)' }}>
        <div className="row" style={{ gap: 'var(--space-5)', marginBottom: 'var(--space-6)' }}>
          <div style={{
            width: 72, height: 72, borderRadius: 'var(--radius-md)',
            background: 'var(--teal)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 'var(--font-2xl)', fontWeight: 700, color: '#fff',
            flexShrink: 0,
          }}>
            {(user.first_name?.[0] || user.username[0]).toUpperCase()}
          </div>
          <div>
            <h2 style={{ fontSize: 'var(--font-xl)', fontWeight: 600 }}>
              {user.first_name ? `${user.first_name} ${user.last_name || ''}`.trim() : user.username}
            </h2>
            <p style={{ fontSize: 'var(--font-sm)', color: 'var(--text-muted)' }}>@{user.username}</p>
            <p style={{ fontSize: 'var(--font-xs)', color: 'var(--text-muted)', marginTop: 'var(--space-1)' }}>
              {user.email}
            </p>
          </div>
        </div>

        {!editing ? (
          <>
            <div className="grid-2" style={{ gap: 'var(--space-5)' }}>
              <InfoRow label="First Name" value={user.first_name || '—'} />
              <InfoRow label="Last Name" value={user.last_name || '—'} />
              <InfoRow label="Email" value={user.email} />
              <InfoRow label="Phone" value={user.phone_number || '—'} />
              <InfoRow label="Gender" value={user.gender === 'M' ? 'Male' : user.gender === 'F' ? 'Female' : user.gender === 'O' ? 'Other' : '—'} />
              <InfoRow label="Date of Birth" value={user.date_of_birth || '—'} />
              <InfoRow label="Emergency Contact" value={user.emergency_contact || '—'} />
              <InfoRow label="Emergency Phone" value={user.emergency_phone || '—'} />
            </div>
            <div style={{ marginTop: 'var(--space-6)' }}>
              <button className="btn btn-primary" onClick={() => setEditing(true)}>
                <IconEdit size={14} /> Edit profile
              </button>
            </div>
          </>
        ) : (
          <form onSubmit={handleSave} className="stack" style={{ gap: 'var(--space-4)' }}>
            <div className="grid-2" style={{ gap: 'var(--space-4)' }}>
              <div className="form-group">
                <label className="form-label">First Name</label>
                <input className="form-input" value={form.first_name}
                  onChange={e => setForm({ ...form, first_name: e.target.value })} />
              </div>
              <div className="form-group">
                <label className="form-label">Last Name</label>
                <input className="form-input" value={form.last_name}
                  onChange={e => setForm({ ...form, last_name: e.target.value })} />
              </div>
            </div>
            <div className="form-group">
              <label className="form-label">Email</label>
              <input className="form-input" type="email" value={form.email}
                onChange={e => setForm({ ...form, email: e.target.value })} />
            </div>
            <div className="form-group">
              <label className="form-label">Phone Number</label>
              <input className="form-input" value={form.phone_number}
                onChange={e => setForm({ ...form, phone_number: e.target.value })} />
            </div>
            <div className="grid-2" style={{ gap: 'var(--space-4)' }}>
              <div className="form-group">
                <label className="form-label">Emergency Contact</label>
                <input className="form-input" value={form.emergency_contact}
                  onChange={e => setForm({ ...form, emergency_contact: e.target.value })} />
              </div>
              <div className="form-group">
                <label className="form-label">Emergency Phone</label>
                <input className="form-input" value={form.emergency_phone}
                  onChange={e => setForm({ ...form, emergency_phone: e.target.value })} />
              </div>
            </div>
            <div className="row" style={{ gap: 'var(--space-3)', marginTop: 'var(--space-2)' }}>
              <button type="submit" className="btn btn-primary" disabled={saving}>
                {saving ? <><span className="spinner" /> Saving…</> : <><IconCheck size={14} /> Save changes</>}
              </button>
              <button type="button" className="btn btn-secondary" onClick={() => setEditing(false)}>Cancel</button>
            </div>
          </form>
        )}
      </div>

      {/* Danger Zone */}
      <div className="card" style={{ border: '1px solid rgba(239, 68, 68, 0.2)' }}>
        <h3 style={{ fontSize: 'var(--font-base)', marginBottom: 'var(--space-3)', color: 'var(--accent-danger)' }}>Session</h3>
        <p style={{ fontSize: 'var(--font-sm)', color: 'var(--text-muted)', marginBottom: 'var(--space-4)' }}>
          Log out of your account on this device.
        </p>
        <button className="btn btn-danger" onClick={() => { logout(); }}>
          <IconLogout size={14} /> Logout
        </button>
      </div>
    </div>
  );
};

const InfoRow: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div>
    <div style={{ fontSize: 'var(--font-xs)', color: 'var(--text-muted)', marginBottom: 'var(--space-1)' }}>{label}</div>
    <div style={{ fontSize: 'var(--font-sm)', color: 'var(--text-primary)' }}>{value}</div>
  </div>
);

export default Profile;
