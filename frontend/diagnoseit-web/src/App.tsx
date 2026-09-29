import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { ToastProvider } from './contexts/ToastContext';
import Layout from './components/Layout';
import Login from './components/Login';
import Register from './components/Register';
import Dashboard from './components/Dashboard';
import MedicalReports from './components/MedicalReports';
import ReportDetail from './components/ReportDetail';
import Symptoms from './components/Symptoms';
import Prescriptions from './components/Prescriptions';
import Diagnosis from './components/Diagnosis';
import HealthTrends from './components/HealthTrends';
import LabCatalog from './components/LabCatalog';
import UnitConverter from './components/UnitConverter';
import Profile from './components/Profile';
import AISettings from './components/AISettings';

function AppRoutes() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="loading-page">
        <div className="spinner spinner-lg" />
        <p style={{ color: 'var(--text-muted)', fontSize: 'var(--font-sm)' }}>Loading…</p>
      </div>
    );
  }

  if (!user) {
    return (
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/medical-reports" element={<MedicalReports />} />
        <Route path="/medical-reports/:id" element={<ReportDetail />} />
        <Route path="/symptoms" element={<Symptoms />} />
        <Route path="/prescriptions" element={<Prescriptions />} />
        <Route path="/diagnosis" element={<Diagnosis />} />
        <Route path="/health-trends" element={<HealthTrends />} />
        <Route path="/lab-catalog" element={<LabCatalog />} />
        <Route path="/unit-converter" element={<UnitConverter />} />
        <Route path="/profile" element={<Profile />} />
        <Route path="/settings/ai" element={<AISettings />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <AuthProvider>
          <AppRoutes />
        </AuthProvider>
      </ToastProvider>
    </BrowserRouter>
  );
}

export default App;
