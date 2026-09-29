import React, { useState } from 'react';
import { apiService } from '../services/api';
import type {
  MedicationFields,
  PrescriptionAppliedChange,
  PrescriptionReview as Review,
  PrescriptionSuggestion,
} from '../services/api';
import { useToast } from '../contexts/ToastContext';
import { apiErrorMessage } from '../utils/apiErrors';

/**
 * What the AI review found wrong with a prescription's medicines, and what the user does about it.
 *
 * Every change is the user's to accept. Unlike a lab report, where correcting a unit is safe enough to
 * apply on its own, each of these is a change to a medicine, so nothing here happens without a click —
 * and each accepted change can be undone.
 */

interface PrescriptionReviewProps {
  prescriptionId: number;
  review: Review;
  /** Called after anything changes, so the card reloads its medicines and its review. */
  onChanged: () => void;
}

const FIELD_LABELS: Record<keyof MedicationFields, string> = {
  medication_name: 'Name',
  dosage: 'Dose',
  frequency: 'Frequency',
  duration: 'Duration',
  instructions: 'Instructions',
};

function describe(medication?: MedicationFields): string {
  if (!medication) return '';
  return [medication.medication_name, medication.dosage, medication.frequency, medication.duration]
    .filter(Boolean)
    .join(' · ');
}

const PrescriptionReview: React.FC<PrescriptionReviewProps> = ({ prescriptionId, review, onChanged }) => {
  const { toast, confirm } = useToast();
  const [busy, setBusy] = useState<'all' | number | null>(null);

  const run = async (work: () => Promise<unknown>, failure: string, after?: () => void) => {
    try {
      await work();
      after?.();
      onChanged();
    } catch (err) {
      toast(apiErrorMessage(err, failure), 'error');
    } finally {
      setBusy(null);
    }
  };

  const suggestions = review.suggestions ?? [];
  const applied = review.applied ?? [];

  if (review.status === 'pending') {
    return (
      <div className="card row" style={{ gap: 'var(--space-3)', marginTop: 'var(--space-4)' }}>
        <span className="spinner" />
        <span style={{ color: 'var(--text-secondary)', flex: 1 }}>
          {review.started_at ? 'Checking the medicines against the prescription.' : 'AI review queued.'}
        </span>
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          disabled={busy !== null}
          onClick={() => {
            setBusy('all');
            run(() => apiService.stopPrescriptionReview(prescriptionId), 'Could not stop the review');
          }}
        >
          Stop
        </button>
      </div>
    );
  }

  if (review.status === 'failed') {
    return (
      <div className="card" style={{ marginTop: 'var(--space-4)' }}>
        <div className="row-between" style={{ gap: 'var(--space-3)', flexWrap: 'wrap' }}>
          <span style={{ color: 'var(--coral)' }}>AI review failed: {review.error}</span>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => run(() => apiService.closePrescriptionReview(prescriptionId), 'Could not close')}
          >
            Dismiss
          </button>
        </div>
      </div>
    );
  }

  const accept = (ids: number[]) => {
    setBusy(ids.length > 1 ? 'all' : ids[0]);
    run(
      () => apiService.acceptPrescriptionSuggestions(prescriptionId, ids),
      'Could not apply this change',
      () => toast(ids.length > 1 ? `${ids.length} changes applied` : 'Change applied', 'success'),
    );
  };

  return (
    <div className="card" style={{ marginTop: 'var(--space-4)' }}>
      <div className="row-between" style={{ gap: 'var(--space-3)', flexWrap: 'wrap' }}>
        <div>
          <h4 style={{ fontSize: 'var(--font-base)', fontWeight: 600 }}>AI review</h4>
          <p className="form-hint" style={{ marginTop: 'var(--space-1)' }}>
            {suggestions.length === 0
              ? 'The medicines match the prescription.'
              : `${suggestions.length} thing${suggestions.length === 1 ? '' : 's'} to look at.`}
            {review.model ? ` Checked by ${review.model}` : ''}
            {review.input_mode === 'text_image' ? ', against the original image.' : '.'}
          </p>
        </div>
        <div className="row" style={{ gap: 'var(--space-2)' }}>
          {suggestions.length > 1 && (
            <button
              type="button"
              className="btn btn-primary btn-sm"
              disabled={busy !== null}
              onClick={() => accept(suggestions.map(item => item.id))}
            >
              {busy === 'all' ? 'Applying…' : 'Accept all'}
            </button>
          )}
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            disabled={busy !== null}
            onClick={async () => {
              if (applied.length && !(await confirm('Close this review? What you accepted stays applied.'))) return;
              run(() => apiService.closePrescriptionReview(prescriptionId), 'Could not close the review');
            }}
          >
            Close
          </button>
        </div>
      </div>

      {suggestions.length > 0 && (
        <div className="stack" style={{ gap: 'var(--space-2)', marginTop: 'var(--space-4)' }}>
          {suggestions.map(item => (
            <div key={item.id} className="medication-row">
              <div className="row-between" style={{ gap: 'var(--space-3)', alignItems: 'flex-start' }}>
                <div style={{ minWidth: 0 }}>
                  <span
                    className={`badge ${
                      item.action === 'add' ? 'badge-success' : item.action === 'remove' ? 'badge-danger' : 'badge-warning'
                    }`}
                  >
                    {item.action === 'add' ? 'Missing' : item.action === 'remove' ? 'Not a medicine' : 'Correction'}
                  </span>
                  <div style={{ marginTop: 'var(--space-2)', fontSize: 'var(--font-sm)' }}>
                    <SuggestionBody suggestion={item} />
                  </div>
                  {item.reason && (
                    <p className="form-hint" style={{ marginTop: 'var(--space-1)' }}>{item.reason}</p>
                  )}
                </div>
                <div className="row" style={{ gap: 'var(--space-1)', flexShrink: 0 }}>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    disabled={busy !== null}
                    onClick={() => accept([item.id])}
                  >
                    {busy === item.id ? 'Applying…' : 'Accept'}
                  </button>
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    disabled={busy !== null}
                    onClick={() =>
                      run(
                        () => apiService.dismissPrescriptionSuggestion(prescriptionId, item.id),
                        'Could not dismiss this suggestion',
                      )
                    }
                  >
                    Dismiss
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {applied.length > 0 && (
        <div style={{ marginTop: 'var(--space-4)' }}>
          <h5 style={{ fontSize: 'var(--font-sm)', fontWeight: 600, marginBottom: 'var(--space-2)' }}>
            Applied
          </h5>
          <div className="stack" style={{ gap: 'var(--space-2)' }}>
            {applied.map(change => (
              <div key={change.id} className="row-between" style={{ gap: 'var(--space-3)', flexWrap: 'wrap' }}>
                <span style={{ fontSize: 'var(--font-xs)', color: 'var(--text-muted)' }}>
                  <AppliedBody change={change} />
                </span>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  disabled={busy !== null}
                  onClick={() =>
                    run(
                      () => apiService.undoPrescriptionChange(prescriptionId, change.id),
                      'Could not undo this change',
                      () => toast('Change undone', 'success'),
                    )
                  }
                >
                  Undo
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

const SuggestionBody: React.FC<{ suggestion: PrescriptionSuggestion }> = ({ suggestion }) => {
  if (suggestion.action === 'add') {
    return <>Add <strong>{describe(suggestion.medication)}</strong></>;
  }
  if (suggestion.action === 'remove') {
    return <>Remove this row — the model reads it as something other than a prescribed medicine.</>;
  }
  const changes = Object.entries(suggestion.changes ?? {}) as [keyof MedicationFields, string][];
  return (
    <>
      {changes.map(([field, value]) => (
        <div key={field}>
          {FIELD_LABELS[field]} → <strong>{value || '(blank)'}</strong>
        </div>
      ))}
    </>
  );
};

const AppliedBody: React.FC<{ change: PrescriptionAppliedChange }> = ({ change }) => {
  if (change.action === 'add') return <>Added {describe(change.after)}</>;
  if (change.action === 'remove') return <>Removed {describe(change.before)}</>;
  return <>Changed {describe(change.before)} to {describe(change.after)}</>;
};

export default PrescriptionReview;
