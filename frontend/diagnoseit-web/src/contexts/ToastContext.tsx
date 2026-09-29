import React, { createContext, useContext, useState, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { IconClose, IconCheck, IconInfo } from '../components/Icons';

type ToastType = 'success' | 'error' | 'info';

interface Toast {
  id: number;
  message: string;
  type: ToastType;
}

interface ToastContextType {
  toast: (message: string, type?: ToastType) => void;
  confirm: (message: string) => Promise<boolean>;
}

const ToastContext = createContext<ToastContextType | null>(null);

export const useToast = (): ToastContextType => {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used within ToastProvider');
  return ctx;
};

let nextId = 0;

export const ToastProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [confirmState, setConfirmState] = useState<{
    message: string;
    resolve: (value: boolean) => void;
  } | null>(null);

  const toast = useCallback((message: string, type: ToastType = 'info') => {
    const id = nextId++;
    setToasts(prev => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    }, 4000);
  }, []);

  const confirmFn = useCallback((message: string): Promise<boolean> => {
    return new Promise(resolve => {
      setConfirmState({ message, resolve });
    });
  }, []);

  const handleConfirm = (result: boolean) => {
    confirmState?.resolve(result);
    setConfirmState(null);
  };

  const dismissToast = (id: number) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  };

  return (
    <ToastContext.Provider value={{ toast, confirm: confirmFn }}>
      {children}
      {createPortal(
        <>
          {/* Toast container */}
          <div className="toast-container" role="status" aria-live="polite">
            {toasts.map(t => (
              <div
                key={t.id}
                className={`toast toast-${t.type}`}
                onClick={() => dismissToast(t.id)}
              >
                <span className="toast-icon">
                  {t.type === 'success' ? <IconCheck size={14} /> : t.type === 'error' ? <IconClose size={14} /> : <IconInfo size={14} />}
                </span>
                <span className="toast-message">{t.message}</span>
              </div>
            ))}
          </div>

          {/* Confirm dialog */}
          {confirmState && (
            <div className="modal-overlay" style={{ zIndex: 2000 }}>
              <div className="modal" style={{ maxWidth: 400, animation: 'scaleIn 0.2s ease' }}>
                <div className="modal-header">
                  <h2 className="modal-title">Confirm</h2>
                </div>
                <div className="modal-body">
                  <p style={{ fontSize: 'var(--font-sm)', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                    {confirmState.message}
                  </p>
                  <div className="modal-actions">
                    <button className="btn btn-secondary" onClick={() => handleConfirm(false)}>
                      Cancel
                    </button>
                    <button className="btn btn-danger" onClick={() => handleConfirm(true)}>
                      Confirm
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}
        </>,
        document.body
      )}
    </ToastContext.Provider>
  );
};
