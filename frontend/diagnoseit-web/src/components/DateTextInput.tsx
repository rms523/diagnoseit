import React, { useRef } from 'react';
import { parseDateInput } from '../utils/dates';

interface DateTextInputProps {
  id: string;
  value: string;
  onChange: (value: string) => void;
  /** Shown under the field when the text is not a date the form could read. */
  error?: string;
  placeholder?: string;
  label?: string;
}

/**
 * A date typed or pasted as text ("2026-05-14", "14/05/2026", "14 May 2026"), with a Calendar button
 * for the native picker.
 *
 * A bare `<input type="date">` cannot be typed into freely — the browser enforces its own segmented
 * format — and pasting a date from a report rarely works at all. The text is normalized on blur, so what
 * is submitted is always "YYYY-MM-DD"; parse it with parseDateInput when saving.
 */
const DateTextInput: React.FC<DateTextInputProps> = ({ id, value, onChange, error, placeholder, label }) => {
  const pickerRef = useRef<HTMLInputElement>(null);

  const normalize = () => {
    const parsed = parseDateInput(value);
    if (parsed) onChange(parsed);
  };

  const handlePaste = (e: React.ClipboardEvent<HTMLInputElement>) => {
    const parsed = parseDateInput(e.clipboardData.getData('text'));
    if (parsed) {
      e.preventDefault();
      onChange(parsed);
    }
  };

  const openPicker = () => {
    const picker = pickerRef.current;
    if (!picker) return;
    picker.value = parseDateInput(value) ?? '';
    try {
      picker.showPicker();
    } catch {
      // Browsers without showPicker still open the picker from focus and click.
      picker.focus();
      picker.click();
    }
  };

  return (
    <div className="form-group">
      {label && <label className="form-label" htmlFor={id}>{label}</label>}
      <div className="row" style={{ gap: 'var(--space-2)', position: 'relative' }}>
        <input
          id={id}
          className={`form-input${error ? ' error' : ''}`}
          style={{ flex: 1 }}
          value={value}
          onChange={e => onChange(e.target.value)}
          onBlur={normalize}
          onPaste={handlePaste}
          placeholder={placeholder ?? '2026-05-14, 14/05/2026, or 14 May 2026'}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${id}-error` : undefined}
        />
        <button type="button" className="btn btn-secondary btn-sm" onClick={openPicker} aria-label="Pick from calendar">
          Calendar
        </button>
        {/* Kept rendered (not display:none) so showPicker() has something to open. */}
        <input
          ref={pickerRef}
          type="date"
          tabIndex={-1}
          aria-hidden="true"
          style={{ position: 'absolute', right: 0, bottom: 0, width: 1, height: 1, opacity: 0, pointerEvents: 'none' }}
          onChange={e => {
            if (e.target.value) onChange(e.target.value);
          }}
        />
      </div>
      {error && <div id={`${id}-error`} className="form-error">{error}</div>}
    </div>
  );
};

export default DateTextInput;
