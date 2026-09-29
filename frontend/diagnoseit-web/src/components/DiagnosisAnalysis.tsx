import React from 'react';
import type { DiagnosisAnalysis as Analysis, DiagnosisCandidate } from '../services/api';

/**
 * The reasoning behind a diagnosis: the ranked differential, what argues for and against each candidate,
 * where the model thinks it is most likely to be wrong, and what it noticed along the way.
 *
 * The point of showing all of it is that a single confident-sounding condition name is the least useful
 * thing a model can produce about health data. What makes the next conversation with a clinician a better
 * one is the evidence, the alternatives, and the tests that would tell them apart.
 */

interface DiagnosisAnalysisProps {
  analysis: Analysis;
}

const LIKELIHOOD_BADGE: Record<DiagnosisCandidate['likelihood'], string> = {
  'most likely': 'badge-danger',
  possible: 'badge-warning',
  'less likely': 'badge-muted',
};

const Points: React.FC<{ label: string; items?: string[]; color?: string }> = ({ label, items, color }) => {
  if (!items?.length) return null;
  return (
    <div style={{ marginTop: 'var(--space-2)' }}>
      <div style={{ fontSize: 'var(--font-xs)', fontWeight: 600, color: color ?? 'var(--text-secondary)' }}>
        {label}
      </div>
      <ul style={{ margin: '2px 0 0', paddingLeft: 'var(--space-5)' }}>
        {items.map((item, index) => (
          <li key={index} style={{ fontSize: 'var(--font-xs)', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
};

const Section: React.FC<{ title: string; hint?: string; children: React.ReactNode }> = ({
  title, hint, children,
}) => (
  <div style={{ marginTop: 'var(--space-5)' }}>
    <h4 style={{ fontSize: 'var(--font-sm)', fontWeight: 600 }}>{title}</h4>
    {hint && <p className="form-hint" style={{ marginTop: 2 }}>{hint}</p>}
    <div style={{ marginTop: 'var(--space-2)' }}>{children}</div>
  </div>
);

const Bullets: React.FC<{ items: string[] }> = ({ items }) => (
  <ul style={{ margin: 0, paddingLeft: 'var(--space-5)' }}>
    {items.map((item, index) => (
      <li key={index} style={{ fontSize: 'var(--font-sm)', color: 'var(--text-secondary)', lineHeight: 1.7 }}>
        {item}
      </li>
    ))}
  </ul>
);

const DiagnosisAnalysis: React.FC<DiagnosisAnalysisProps> = ({ analysis }) => {
  const differential = analysis.differential ?? [];
  const falsePositives = analysis.false_positives ?? [];
  const patterns = analysis.patterns ?? [];
  const cautions = analysis.cautions ?? [];
  const redFlags = analysis.red_flags ?? [];

  const hasAnything =
    differential.length || falsePositives.length || patterns.length || cautions.length || redFlags.length;
  if (!hasAnything) return null;

  return (
    <div>
      {redFlags.length > 0 && (
        <div className="alert alert-error" style={{ marginTop: 'var(--space-4)', display: 'block' }}>
          <strong>Worth prompt medical attention</strong>
          <Bullets items={redFlags} />
        </div>
      )}

      {differential.length > 0 && (
        <Section
          title={`What could explain this (${differential.length})`}
          hint="Ranked by what the evidence supports, with what argues against each."
        >
          <div className="stack" style={{ gap: 'var(--space-2)' }}>
            {differential.map((candidate, index) => (
              <div key={index} className="medication-row">
                <div className="row-between" style={{ gap: 'var(--space-3)', flexWrap: 'wrap' }}>
                  <div style={{ fontWeight: 600, fontSize: 'var(--font-sm)' }}>
                    {index + 1}. {candidate.condition}
                  </div>
                  <div className="row" style={{ gap: 'var(--space-2)' }}>
                    <span className={`badge ${LIKELIHOOD_BADGE[candidate.likelihood] ?? 'badge-muted'}`}>
                      {candidate.likelihood}
                    </span>
                    <span className="badge badge-muted">{candidate.confidence}/5</span>
                  </div>
                </div>
                {candidate.reasoning && (
                  <p style={{
                    fontSize: 'var(--font-sm)', color: 'var(--text-secondary)', lineHeight: 1.7,
                    marginTop: 'var(--space-2)',
                  }}>
                    {candidate.reasoning}
                  </p>
                )}
                <Points label="Points to it" items={candidate.supporting} color="var(--sage)" />
                <Points label="Argues against it" items={candidate.against} color="var(--coral)" />
                <Points label="Would confirm it" items={candidate.confirm_with} />
                <Points label="Would rule it out" items={candidate.rule_out_with} />
              </div>
            ))}
          </div>
        </Section>
      )}

      {falsePositives.length > 0 && (
        <Section
          title="Where this is most likely wrong"
          hint="The model's own read on which of its candidates is the likeliest false alarm."
        >
          <div className="stack" style={{ gap: 'var(--space-2)' }}>
            {falsePositives.map((item, index) => (
              <div key={index} className="medication-row">
                <div style={{ fontWeight: 600, fontSize: 'var(--font-sm)' }}>{item.condition}</div>
                {item.why_it_might_be_wrong && (
                  <p style={{ fontSize: 'var(--font-xs)', color: 'var(--text-secondary)', lineHeight: 1.6, marginTop: 4 }}>
                    {item.why_it_might_be_wrong}
                  </p>
                )}
                {item.how_to_tell && (
                  <p style={{ fontSize: 'var(--font-xs)', color: 'var(--text-muted)', lineHeight: 1.6, marginTop: 4 }}>
                    How to tell: {item.how_to_tell}
                  </p>
                )}
              </div>
            ))}
          </div>
        </Section>
      )}

      {patterns.length > 0 && (
        <Section title="Patterns noticed" hint="Things in the data a quick look would miss.">
          <Bullets items={patterns} />
        </Section>
      )}

      {cautions.length > 0 && (
        <Section title="Cautions" hint="What to watch out for, and how this reading could be misused.">
          <Bullets items={cautions} />
        </Section>
      )}
    </div>
  );
};

export default DiagnosisAnalysis;
