import React from 'react';

interface IconProps {
  size?: number;
  className?: string;
}

const stroke = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.75, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const };

export const IconDashboard: React.FC<IconProps> = ({ size = 20, className }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" className={className} aria-hidden>
    <rect x="3" y="3" width="8" height="8" rx="1.5" {...stroke} />
    <rect x="13" y="3" width="8" height="5" rx="1.5" {...stroke} />
    <rect x="13" y="10" width="8" height="11" rx="1.5" {...stroke} />
    <rect x="3" y="13" width="8" height="8" rx="1.5" {...stroke} />
  </svg>
);

export const IconReports: React.FC<IconProps> = ({ size = 20, className }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" className={className} aria-hidden>
    <path d="M8 3h8l4 4v14H8V3z" {...stroke} />
    <path d="M16 3v4h4M10 12h6M10 16h4" {...stroke} />
  </svg>
);

export const IconSymptoms: React.FC<IconProps> = ({ size = 20, className }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" className={className} aria-hidden>
    <circle cx="12" cy="12" r="9" {...stroke} />
    <path d="M12 8v8M8 12h8" {...stroke} />
  </svg>
);

export const IconPrescriptions: React.FC<IconProps> = ({ size = 20, className }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" className={className} aria-hidden>
    <rect x="4" y="6" width="16" height="14" rx="2" {...stroke} />
    <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M12 11v6M9 14h6" {...stroke} />
  </svg>
);

export const IconDiagnosis: React.FC<IconProps> = ({ size = 20, className }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" className={className} aria-hidden>
    <path d="M4 18V6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v12" {...stroke} />
    <path d="M8 14l3-3 2 2 5-6" {...stroke} />
  </svg>
);

export const IconTrends: React.FC<IconProps> = ({ size = 20, className }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" className={className} aria-hidden>
    <path d="M4 20V4M4 20h16" {...stroke} />
    <path d="M7 16l4-5 3 3 5-8" {...stroke} />
  </svg>
);

export const IconConverter: React.FC<IconProps> = ({ size = 20, className }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" className={className} aria-hidden>
    <path d="M7 8h10M7 16h10" {...stroke} />
    <path d="M17 5l3 3-3 3M7 19l-3-3 3-3" {...stroke} />
  </svg>
);

export const IconProfile: React.FC<IconProps> = ({ size = 20, className }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" className={className} aria-hidden>
    <circle cx="12" cy="8" r="4" {...stroke} />
    <path d="M4 21c1.5-4 6-6 8-6s6.5 2 8 6" {...stroke} />
  </svg>
);

export const IconClose: React.FC<IconProps> = ({ size = 20, className }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" className={className} aria-hidden>
    <path d="M6 6l12 12M18 6L6 18" {...stroke} />
  </svg>
);

export const IconCheck: React.FC<IconProps> = ({ size = 20, className }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" className={className} aria-hidden>
    <path d="M5 12l5 5L19 7" {...stroke} />
  </svg>
);

export const IconInfo: React.FC<IconProps> = ({ size = 20, className }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" className={className} aria-hidden>
    <circle cx="12" cy="12" r="9" {...stroke} />
    <path d="M12 10v6M12 7h.01" {...stroke} />
  </svg>
);

export const IconTrash: React.FC<IconProps> = ({ size = 20, className }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" className={className} aria-hidden>
    <path d="M4 7h16M9 7V5h6v2M10 11v6M14 11v6M6 7l1 12h10l1-12" {...stroke} />
  </svg>
);

export const IconEdit: React.FC<IconProps> = ({ size = 20, className }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" className={className} aria-hidden>
    <path d="M4 20h4l10-10-4-4L4 16v4z" {...stroke} />
    <path d="M13 7l4 4" {...stroke} />
  </svg>
);

export const IconLogout: React.FC<IconProps> = ({ size = 20, className }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" className={className} aria-hidden>
    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" {...stroke} />
    <path d="M16 17l5-5-5-5M21 12H9" {...stroke} />
  </svg>
);

export const IconRefresh: React.FC<IconProps> = ({ size = 20, className }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" className={className} aria-hidden>
    <path d="M4 12a8 8 0 0 1 13.5-5.7L20 8" {...stroke} />
    <path d="M20 12a8 8 0 0 1-13.5 5.7L4 16" {...stroke} />
  </svg>
);

export const IconSwap: React.FC<IconProps> = ({ size = 20, className }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" className={className} aria-hidden>
    <path d="M7 8h10M7 16h10" {...stroke} />
    <path d="M17 5l3 3-3 3M7 19l-3-3 3-3" {...stroke} />
  </svg>
);

export const IconLogo: React.FC<IconProps> = ({ size = 28, className }) => (
  <svg width={size} height={size} viewBox="0 0 32 32" className={className} aria-hidden>
    <rect x="2" y="2" width="28" height="28" rx="6" fill="var(--teal)" />
    <path d="M8 22V10h4.5c2.8 0 4.5 1.4 4.5 3.6 0 1.5-.8 2.6-2.1 3.1L18 22h-3.2l-2.8-4.5H11V22H8z" fill="var(--paper)" />
    <rect x="20" y="14" width="4" height="8" rx="1" fill="var(--paper)" opacity="0.85" />
  </svg>
);

export const IconSettings: React.FC<IconProps> = ({ size = 20, className }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" className={className} aria-hidden>
    <circle cx="12" cy="12" r="3" {...stroke} />
    <path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9L7 7M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1" {...stroke} />
  </svg>
);

export const IconCatalog: React.FC<IconProps> = ({ size = 20, className }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" className={className} aria-hidden>
    <path d="M4 5.5A1.5 1.5 0 0 1 5.5 4H10v16H5.5A1.5 1.5 0 0 1 4 18.5v-13z" {...stroke} />
    <path d="M10 4h8.5A1.5 1.5 0 0 1 20 5.5v13a1.5 1.5 0 0 1-1.5 1.5H10" {...stroke} />
    <path d="M13 9h4M13 13h4" {...stroke} />
  </svg>
);

export const NAV_ICONS: Record<string, React.FC<IconProps>> = {
  dashboard: IconDashboard,
  reports: IconReports,
  symptoms: IconSymptoms,
  prescriptions: IconPrescriptions,
  diagnosis: IconDiagnosis,
  trends: IconTrends,
  converter: IconConverter,
  catalog: IconCatalog,
  profile: IconProfile,
  settings: IconSettings,
};

export const IconSearch: React.FC<IconProps> = ({ size = 20, className }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" className={className} aria-hidden>
    <circle cx="11" cy="11" r="6.5" {...stroke} />
    <path d="M16 16l4.5 4.5" {...stroke} />
  </svg>
);

export const IconCopy: React.FC<IconProps> = ({ size = 20, className }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" className={className} aria-hidden>
    <rect x="8" y="8" width="11" height="11" rx="2" {...stroke} />
    <path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" {...stroke} />
  </svg>
);
