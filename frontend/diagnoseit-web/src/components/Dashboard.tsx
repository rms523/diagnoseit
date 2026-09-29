import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { apiService } from '../services/api';
import type { MedicalReport, Symptom, Diagnosis, Prescription } from '../services/api';
import { IconReports, IconSymptoms, IconDiagnosis, IconPrescriptions } from './Icons';

const RefRangeHero: React.FC<{ high: number; low: number; normal: number; total: number }> = ({
  high, low, normal, total,
}) => {
  const abnormal = high + low;
  const abnormalPct = total > 0 ? (abnormal / total) * 100 : 0;
  const markerClass = high > low ? 'high' : low > high ? 'low' : abnormal > 0 ? 'high' : 'normal';
  const markerPos = Math.min(Math.max(abnormalPct, 8), 92);

  return (
    <div className="ref-range" style={{ maxWidth: 360 }}>
      <div className="ref-range-track">
        <div className="ref-range-normal" style={{ left: '15%', width: '70%' }} />
        <div className={`ref-range-marker ${markerClass}`} style={{ left: `${markerPos}%` }} />
      </div>
      <div className="ref-range-labels">
        <span>Low {low}</span>
        <span>Normal {normal}</span>
        <span>High {high}</span>
      </div>
    </div>
  );
};

const Dashboard: React.FC = () => {
  const { user } = useAuth();
  const [reports, setReports] = useState<MedicalReport[]>([]);
  const [symptoms, setSymptoms] = useState<Symptom[]>([]);
  const [diagnoses, setDiagnoses] = useState<Diagnosis[]>([]);
  const [prescriptions, setPrescriptions] = useState<Prescription[]>([]);
  const [loading, setLoading] = useState(true);
  const [healthSummary, setHealthSummary] = useState({ high: 0, low: 0, normal: 0, total: 0 });

  useEffect(() => {
    const fetchAll = async () => {
      try {
        const [rRes, sRes, dRes, pRes] = await Promise.allSettled([
          apiService.getMedicalReports(),
          apiService.getActiveSymptoms(),
          apiService.getDiagnoses(),
          apiService.getPrescriptions(),
        ]);
        if (rRes.status === 'fulfilled') {
          const allReports = rRes.value;
          setReports(allReports);
          let high = 0, low = 0, normal = 0, total = 0;
          allReports.forEach(r => {
            r.test_results?.forEach(tr => {
              total++;
              if (tr.status === 'HIGH') high++;
              else if (tr.status === 'LOW') low++;
              else if (tr.status === 'NORMAL') normal++;
            });
          });
          setHealthSummary({ high, low, normal, total });
        }
        if (sRes.status === 'fulfilled') setSymptoms(sRes.value ?? []);
        if (dRes.status === 'fulfilled') setDiagnoses(dRes.value);
        if (pRes.status === 'fulfilled') setPrescriptions(pRes.value);
      } catch { /* ignore */ } finally {
        setLoading(false);
      }
    };
    fetchAll();
  }, []);

  const severityLabel = (s: number) => ['', 'Mild', 'Moderate', 'Severe', 'Very Severe'][s] || '';
  const severityClass = (s: number) => ['', 'badge-success', 'badge-warning', 'badge-danger', 'badge-danger'][s] || 'badge-muted';

  if (loading) {
    return (
      <div className="stack stagger-children">
        <div className="skeleton" style={{ height: 120, width: '100%' }} />
        <div className="grid-4">{[1, 2, 3, 4].map(i => <div key={i} className="skeleton" style={{ height: 96 }} />)}</div>
        <div className="grid-2">{[1, 2].map(i => <div key={i} className="skeleton" style={{ height: 200 }} />)}</div>
      </div>
    );
  }

  const name = user?.first_name || user?.username;
  const abnormalCount = healthSummary.high + healthSummary.low;

  const stats = [
    { Icon: IconReports, label: 'Medical Reports', value: reports.length, accent: 'var(--teal)', link: '/medical-reports' },
    { Icon: IconSymptoms, label: 'Active Symptoms', value: symptoms.length, accent: 'var(--amber)', link: '/symptoms' },
    { Icon: IconDiagnosis, label: 'Diagnoses', value: diagnoses.length, accent: 'var(--slate)', link: '/diagnosis' },
    { Icon: IconPrescriptions, label: 'Prescriptions', value: prescriptions.length, accent: 'var(--sage)', link: '/prescriptions' },
  ];

  return (
    <div className="stack animate-fade-in">
      {/* Hero — health signal first */}
      <section className="dashboard-hero report-section">
        <div className="dashboard-hero-grid">
          <div>
            <p className="eyebrow">Patient overview</p>
            <h1 style={{ fontSize: 'var(--font-3xl)', marginTop: 'var(--space-2)', marginBottom: 'var(--space-3)' }}>
              {name}
            </h1>
            {healthSummary.total > 0 ? (
              <>
                <p style={{ color: 'var(--text-secondary)', fontSize: 'var(--font-base)', maxWidth: 420, lineHeight: 1.6 }}>
                  {abnormalCount === 0
                    ? 'All parsed lab values are within reference range.'
                    : `${abnormalCount} of ${healthSummary.total} lab values fall outside reference range.`}
                </p>
                <Link to="/health-trends" className="btn btn-secondary btn-sm" style={{ marginTop: 'var(--space-5)' }}>
                  View trends
                </Link>
              </>
            ) : (
              <p style={{ color: 'var(--text-muted)', fontSize: 'var(--font-sm)' }}>
                Upload a lab report to see your reference range summary.
              </p>
            )}
          </div>
          {healthSummary.total > 0 && (
            <div className="dashboard-hero-viz">
              <p className="eyebrow" style={{ marginBottom: 'var(--space-3)' }}>Lab results distribution</p>
              <RefRangeHero {...healthSummary} />
              <div className="row" style={{ gap: 'var(--space-6)', marginTop: 'var(--space-5)' }}>
                <div>
                  <div className="stat-value" style={{ color: 'var(--sage)', fontSize: 'var(--font-2xl)' }}>{healthSummary.normal}</div>
                  <div className="stat-label">Normal</div>
                </div>
                <div>
                  <div className="stat-value" style={{ color: 'var(--coral)', fontSize: 'var(--font-2xl)' }}>{healthSummary.high}</div>
                  <div className="stat-label">High</div>
                </div>
                <div>
                  <div className="stat-value" style={{ color: 'var(--amber)', fontSize: 'var(--font-2xl)' }}>{healthSummary.low}</div>
                  <div className="stat-label">Low</div>
                </div>
              </div>
            </div>
          )}
        </div>
      </section>

      {/* Stats */}
      <div className="grid-4 stagger-children">
        {stats.map(({ Icon, label, value, accent, link }) => (
          <Link key={label} to={link} style={{ textDecoration: 'none' }}>
            <div className="card stat-card-link">
              <span style={{ color: accent, display: 'flex' }}><Icon size={20} /></span>
              <div className="stat-value" style={{ color: accent, marginTop: 'var(--space-3)' }}>{value}</div>
              <div className="stat-label">{label}</div>
            </div>
          </Link>
        ))}
      </div>

      {/* Quick Actions */}
      <div className="card-gradient">
        <p className="eyebrow" style={{ marginBottom: 'var(--space-3)' }}>Quick actions</p>
        <div className="row" style={{ flexWrap: 'wrap', gap: 'var(--space-3)' }}>
          <Link to="/medical-reports" className="btn btn-secondary">Upload report</Link>
          <Link to="/symptoms" className="btn btn-secondary">Log symptom</Link>
          <Link to="/diagnosis" className="btn btn-secondary">Generate diagnosis</Link>
          <Link to="/prescriptions" className="btn btn-secondary">Add prescription</Link>
        </div>
      </div>

      {/* Recent Data */}
      <div className="grid-2">
        <div className="card">
          <div className="row-between" style={{ marginBottom: 'var(--space-4)' }}>
            <h3 style={{ fontSize: 'var(--font-lg)' }}>Recent reports</h3>
            <Link to="/medical-reports" className="btn btn-ghost btn-sm">View all</Link>
          </div>
          {reports.length === 0 ? (
            <p style={{ color: 'var(--text-muted)', fontSize: 'var(--font-sm)' }}>No reports yet. Upload your first lab report.</p>
          ) : (
            <div className="stack" style={{ gap: 'var(--space-2)' }}>
              {reports.slice(0, 4).map(r => (
                <Link key={r.id} to={`/medical-reports/${r.id}`} className="list-row" style={{ textDecoration: 'none' }}>
                  <div>
                    <div style={{ fontSize: 'var(--font-sm)', fontWeight: 500 }}>{r.title}</div>
                    <div className="font-mono" style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}>
                      {r.lab_name && `${r.lab_name} · `}{new Date(`${r.report_date}T00:00:00`).toLocaleDateString()}
                    </div>
                  </div>
                  <span className={`badge ${r.is_parsed ? 'badge-success' : 'badge-warning'}`}>
                    {r.status === 'PROCESSING' || r.status === 'PENDING' ? 'Parsing' : r.is_parsed ? 'Parsed' : 'Pending'}
                  </span>
                </Link>
              ))}
            </div>
          )}
        </div>

        <div className="card">
          <div className="row-between" style={{ marginBottom: 'var(--space-4)' }}>
            <h3 style={{ fontSize: 'var(--font-lg)' }}>Active symptoms</h3>
            <Link to="/symptoms" className="btn btn-ghost btn-sm">View all</Link>
          </div>
          {symptoms.length === 0 ? (
            <p style={{ color: 'var(--text-muted)', fontSize: 'var(--font-sm)' }}>No active symptoms logged.</p>
          ) : (
            <div className="stack" style={{ gap: 'var(--space-2)' }}>
              {symptoms.slice(0, 4).map(s => (
                <div key={s.id} className="list-row">
                  <div>
                    <div style={{ fontSize: 'var(--font-sm)', fontWeight: 500 }}>{s.description.slice(0, 40)}{s.description.length > 40 ? '…' : ''}</div>
                    <div className="font-mono" style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}>
                      {s.body_part && `${s.body_part} · `}{new Date(s.onset_date).toLocaleDateString()}
                    </div>
                  </div>
                  <span className={`badge ${severityClass(s.severity)}`}>{severityLabel(s.severity)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="grid-2">
        <div className="card">
          <div className="row-between" style={{ marginBottom: 'var(--space-4)' }}>
            <h3 style={{ fontSize: 'var(--font-lg)' }}>Recent prescriptions</h3>
            <Link to="/prescriptions" className="btn btn-ghost btn-sm">View all</Link>
          </div>
          {prescriptions.length === 0 ? (
            <p style={{ color: 'var(--text-muted)', fontSize: 'var(--font-sm)' }}>No prescriptions yet.</p>
          ) : (
            <div className="stack" style={{ gap: 'var(--space-2)' }}>
              {prescriptions.slice(0, 3).map(rx => (
                <div key={rx.id} className="list-row">
                  <div>
                    <div style={{ fontSize: 'var(--font-sm)', fontWeight: 500 }}>
                      {rx.doctor_name ? `Dr. ${rx.doctor_name}` : 'Prescription'}
                    </div>
                    <div className="font-mono" style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}>
                      {rx.hospital_clinic && `${rx.hospital_clinic} · `}
                      {new Date(`${rx.prescription_date}T00:00:00`).toLocaleDateString()}
                    </div>
                  </div>
                  <span className={`badge ${rx.medications && rx.medications.length > 0 ? 'badge-success' : 'badge-muted'}`}>
                    {rx.medications?.length || 0} meds
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="card">
          <div className="row-between" style={{ marginBottom: 'var(--space-4)' }}>
            <h3 style={{ fontSize: 'var(--font-lg)' }}>Recent diagnoses</h3>
            <Link to="/diagnosis" className="btn btn-ghost btn-sm">View all</Link>
          </div>
          {diagnoses.length === 0 ? (
            <p style={{ color: 'var(--text-muted)', fontSize: 'var(--font-sm)' }}>No diagnoses yet.</p>
          ) : (
            <div className="stack" style={{ gap: 'var(--space-2)' }}>
              {diagnoses.slice(0, 3).map(d => (
                <div key={d.id} className="list-row" style={{ flexDirection: 'column', alignItems: 'stretch' }}>
                  <div className="row-between">
                    <div style={{ fontSize: 'var(--font-sm)', fontWeight: 500 }}>{d.condition_name}</div>
                    <span className="badge badge-purple">Confidence {d.confidence_score}/5</span>
                  </div>
                  {d.recommendations && (
                    <p style={{ fontSize: 'var(--font-xs)', color: 'var(--text-muted)', marginTop: 'var(--space-2)' }}>
                      {d.recommendations.slice(0, 100)}{d.recommendations.length > 100 ? '…' : ''}
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <style>{`
        .dashboard-hero { padding: var(--space-8); }
        .dashboard-hero-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: var(--space-10);
          align-items: center;
        }
        .dashboard-hero-viz {
          padding: var(--space-6);
          background: var(--paper-muted);
          border-radius: var(--radius-lg);
          border: 1px solid var(--border-color);
        }
        .stat-card-link { cursor: pointer; }
        .stat-card-link:hover { border-color: var(--border-color-hover); }
        .list-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: var(--space-3);
          padding: var(--space-3) var(--space-4);
          border-radius: var(--radius-md);
          background: var(--paper-muted);
          border: 1px solid transparent;
          transition: border-color var(--transition-fast);
        }
        .list-row:hover { border-color: var(--border-color); }
        @media (max-width: 768px) {
          .dashboard-hero-grid { grid-template-columns: 1fr; gap: var(--space-6); }
        }
      `}</style>
    </div>
  );
};

export default Dashboard;
