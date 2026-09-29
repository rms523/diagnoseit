import React, { useState } from 'react';
import { apiService } from '../services/api';
import type { Medication, MedicationFields } from '../services/api';
import { useToast } from '../contexts/ToastContext';
import { apiErrorMessage } from '../utils/apiErrors';

/**
 * The medicines on a prescription, with the means to correct them.
 *
 * What the OCR model reads off a photograph is a good start and not a record: a handwritten name, a
 * strength in a script the model half-recognises, a dose split across two lines. Every field is editable,
 * a missed medicine can be added, and a row the model invented can be removed.
 */

interface MedicationListProps {
  prescriptionId: number;
  medications: Medication[];
  /** Called after a change, so the page reloads the prescription it belongs to. */
  onChanged: () => void;
}

const EMPTY: MedicationFields = {
  medication_name: '', dosage: '', frequency: '', duration: '', instructions: '',
};

function fieldsOf(medication: Medication): MedicationFields {
  return {
    medication_name: medication.medication_name,
    dosage: medication.dosage ?? '',
    frequency: medication.frequency ?? '',
    duration: medication.duration ?? '',
    instructions: medication.instructions ?? '',
  };
}

const MedicationList: React.FC<MedicationListProps> = ({ prescriptionId, medications, onChanged }) => {
  const { toast, confirm } = useToast();
  const [editingId, setEditingId] = useState<number | null>(null);
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState<MedicationFields>(EMPTY);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const startEdit = (medication: Medication) => {
    setAdding(false);
    setEditingId(medication.id);
    setForm(fieldsOf(medication));
    setError('');
  };

  const startAdd = () => {
    setEditingId(null);
    setAdding(true);
    setForm(EMPTY);
    setError('');
  };

  const cancel = () => {
    setEditingId(null);
    setAdding(false);
    setError('');
  };

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.medication_name.trim()) {
      setError('Give the medicine a name.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      if (adding) {
        await apiService.createMedication(prescriptionId, form);
        toast(`Added ${form.medication_name.trim()}`, 'success');
      } else if (editingId !== null) {
        await apiService.updateMedication(prescriptionId, editingId, form);
        toast('Medicine saved', 'success');
      }
      cancel();
      onChanged();
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not save this medicine'));
    } finally {
      setSaving(false);
    }
  };

  const remove = async (medication: Medication) => {
    if (!(await confirm(`Remove “${medication.medication_name}” from this prescription?`))) return;
    try {
      await apiService.deleteMedication(prescriptionId, medication.id);
      toast('Medicine removed', 'success');
      onChanged();
    } catch (err) {
      toast(apiErrorMessage(err, 'Could not remove this medicine'), 'error');
    }
  };

  const fields = (
    <>
      <div className="form-group">
        <label className="form-label" htmlFor={`med-name-${prescriptionId}`}>Medicine</label>
        <input
          id={`med-name-${prescriptionId}`}
          className="form-input"
          value={form.medication_name}
          onChange={e => setForm({ ...form, medication_name: e.target.value })}
          placeholder="Amoxicillin"
          autoFocus
        />
      </div>
      <div className="medication-field-row">
        <div className="form-group">
          <label className="form-label" htmlFor={`med-dose-${prescriptionId}`}>Dose</label>
          <input
            id={`med-dose-${prescriptionId}`}
            className="form-input"
            value={form.dosage}
            onChange={e => setForm({ ...form, dosage: e.target.value })}
            placeholder="500 mg"
          />
        </div>
        <div className="form-group">
          <label className="form-label" htmlFor={`med-freq-${prescriptionId}`}>Frequency</label>
          <input
            id={`med-freq-${prescriptionId}`}
            className="form-input"
            value={form.frequency}
            onChange={e => setForm({ ...form, frequency: e.target.value })}
            placeholder="twice daily, or 1-0-1"
          />
        </div>
        <div className="form-group">
          <label className="form-label" htmlFor={`med-dur-${prescriptionId}`}>Duration</label>
          <input
            id={`med-dur-${prescriptionId}`}
            className="form-input"
            value={form.duration}
            onChange={e => setForm({ ...form, duration: e.target.value })}
            placeholder="5 days"
          />
        </div>
      </div>
      <div className="form-group">
        <label className="form-label" htmlFor={`med-instr-${prescriptionId}`}>Instructions</label>
        <input
          id={`med-instr-${prescriptionId}`}
          className="form-input"
          value={form.instructions}
          onChange={e => setForm({ ...form, instructions: e.target.value })}
          placeholder="after food"
        />
      </div>
      {error && <div className="form-error">{error}</div>}
      <div className="row" style={{ gap: 'var(--space-2)', justifyContent: 'flex-end' }}>
        <button type="button" className="btn btn-ghost btn-sm" onClick={cancel} disabled={saving}>Cancel</button>
        <button type="submit" className="btn btn-primary btn-sm" disabled={saving}>
          {saving ? 'Saving…' : adding ? 'Add medicine' : 'Save'}
        </button>
      </div>
    </>
  );

  return (
    <div style={{ marginTop: 'var(--space-4)' }}>
      <div className="row-between" style={{ marginBottom: 'var(--space-3)', gap: 'var(--space-3)' }}>
        <div style={{ fontSize: 'var(--font-sm)', fontWeight: 600, color: 'var(--teal)' }}>
          Medicines ({medications.length})
        </div>
        {!adding && editingId === null && (
          <button type="button" className="btn btn-secondary btn-sm" onClick={startAdd}>Add medicine</button>
        )}
      </div>

      <div className="stack" style={{ gap: 'var(--space-2)' }}>
        {medications.map(medication => (
          <div key={medication.id} className="medication-row">
            {editingId === medication.id ? (
              <form onSubmit={save} className="stack" style={{ gap: 'var(--space-3)' }}>{fields}</form>
            ) : (
              <div className="row-between" style={{ gap: 'var(--space-3)', alignItems: 'flex-start' }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontWeight: 500, fontSize: 'var(--font-sm)' }}>{medication.medication_name}</div>
                  <div
                    style={{
                      fontSize: 'var(--font-xs)', color: 'var(--text-muted)', marginTop: 'var(--space-1)',
                      display: 'flex', gap: 'var(--space-4)', flexWrap: 'wrap',
                    }}
                  >
                    {medication.dosage && <span>Dose: {medication.dosage}</span>}
                    {medication.frequency && <span>Freq: {medication.frequency}</span>}
                    {medication.duration && <span>Duration: {medication.duration}</span>}
                  </div>
                  {medication.instructions && (
                    <p style={{ fontSize: 'var(--font-xs)', color: 'var(--text-secondary)', marginTop: 'var(--space-1)' }}>
                      {medication.instructions}
                    </p>
                  )}
                </div>
                <div className="row" style={{ gap: 'var(--space-1)', flexShrink: 0 }}>
                  <button type="button" className="btn btn-ghost btn-sm" onClick={() => startEdit(medication)}>
                    Edit
                  </button>
                  <button type="button" className="btn btn-ghost btn-sm" onClick={() => remove(medication)}>
                    Remove
                  </button>
                </div>
              </div>
            )}
          </div>
        ))}

        {adding && (
          <div className="medication-row">
            <form onSubmit={save} className="stack" style={{ gap: 'var(--space-3)' }}>{fields}</form>
          </div>
        )}
      </div>
    </div>
  );
};

export default MedicationList;
