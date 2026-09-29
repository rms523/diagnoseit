import React, { useRef } from 'react';
import { parseDateTimeInput } from '../utils/dates';

interface DateTimeTextInputProps {
  id: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}

/**
 * A date with an optional time, typed or pasted as text ("14/05/2026 09:30", "14 May 2026"), plus a
 * Calendar button that opens the native date and time picker. Valid text is normalized to
 * "YYYY-MM-DD HH:mm" on blur and paste; parse it with dateTimeTextToIso when saving.
 */
const DateTimeTextInput: React.FC<DateTimeTextInputProps> = ({ id, value, onChange, placeholder }) => {
  const pickerRef = useRef<HTMLInputElement>(null);

  const normalize = () => {
    const parsed = parseDateTimeInput(value);
    if (parsed) onChange(parsed);
  };

  const handlePaste = (e: React.ClipboardEvent<HTMLInputElement>) => {
    const parsed = parseDateTimeInput(e.clipboardData.getData('text'));
    if (parsed) {
      e.preventDefault();
      onChange(parsed);
    }
  };

  const openPicker = () => {
    const picker = pickerRef.current;
    if (!picker) return;
    const parsed = parseDateTimeInput(value);
    picker.value = parsed ? `${parsed.slice(0, 10)}T${parsed.slice(11) || '00:00'}` : '';
    try {
      picker.showPicker();
    } catch {
      // Browsers without showPicker still open the picker from focus/click on the input.
      picker.focus();
      picker.click();
    }
  };

  return (
    <div className="row" style={{ gap: 'var(--space-2)', position: 'relative' }}>
      <input
        id={id}
        className="form-input"
        style={{ flex: 1, minWidth: 0 }}
        placeholder={placeholder ?? 'e.g. 14/05/2026 09:30'}
        autoComplete="off"
        value={value}
        onChange={e => onChange(e.target.value)}
        onPaste={handlePaste}
        onBlur={normalize}
      />
      <button type="button" className="btn btn-secondary btn-sm" onClick={openPicker} aria-label="Pick date and time from calendar">
        Calendar
      </button>
      {/* Native picker kept rendered (not display:none) so showPicker() can open it. */}
      <input
        ref={pickerRef}
        type="datetime-local"
        tabIndex={-1}
        aria-hidden="true"
        style={{ position: 'absolute', right: 0, bottom: 0, width: 1, height: 1, opacity: 0, pointerEvents: 'none' }}
        onChange={e => {
          if (e.target.value) onChange(e.target.value.replace('T', ' '));
        }}
      />
    </div>
  );
};

export default DateTimeTextInput;
