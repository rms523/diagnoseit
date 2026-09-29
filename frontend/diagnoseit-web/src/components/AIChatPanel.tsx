import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { apiService } from '../services/api';
import type { ReportChatMessage } from '../services/api';
import { useToast } from '../contexts/ToastContext';
import { apiErrorMessage } from '../utils/apiErrors';
import { IconClose } from './Icons';

/**
 * Asking the AI about one stored document — a lab report or a prescription — in a pane beside it.
 *
 * The model is given that document and the recent turns, and answers from it (`utils/ai_chat.py`). The
 * conversation is stored on the document, so it is still here on the next visit. Names, phone numbers,
 * and emails are replaced before anything leaves the server.
 *
 * The card fills the height of its column so the question box stays put while the transcript scrolls,
 * the way the PDF pane beside it fills the same space.
 */

type ChatSubject = 'report' | 'prescription';

interface AIChatPanelProps {
  subject: ChatSubject;
  id: number;
  /** Whether the document has rows read from it, so the prompts offered fit what is on screen. */
  hasRows: boolean;
  /** Closes the pane; the page owns whether it is open. */
  onClose?: () => void;
}

const SUGGESTIONS: Record<ChatSubject, string[]> = {
  report: [
    'What does this report say in plain language?',
    'Which results are outside their reference range, and what does that mean?',
    'What should I ask my doctor about this report?',
  ],
  prescription: [
    'What is each of these medicines for?',
    'How and when should I take them?',
    'What side effects or interactions should I watch for?',
  ],
};

/** Prompts that only make sense once something was read from the document. */
const NEEDS_ROWS: Record<ChatSubject, string> = { report: 'reference range', prescription: 'each of these' };

const LABEL: Record<ChatSubject, string> = { report: 'report', prescription: 'prescription' };

const AIChatPanel: React.FC<AIChatPanelProps> = ({ subject, id, hasRows, onClose }) => {
  const { toast, confirm } = useToast();
  const [messages, setMessages] = useState<ReportChatMessage[]>([]);
  const [configured, setConfigured] = useState(true);
  const [model, setModel] = useState('');
  const [question, setQuestion] = useState('');
  const [asking, setAsking] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const transcriptRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    try {
      const state = subject === 'report'
        ? await apiService.getReportChat(id)
        : await apiService.getPrescriptionChat(id);
      setMessages(state.messages);
      setConfigured(state.configured);
      setModel(state.model);
    } catch {
      /* the pane still offers to ask; the ask itself reports any error */
    } finally {
      setLoading(false);
    }
  }, [subject, id]);

  useEffect(() => {
    load();
  }, [load]);

  // Keep the newest turn in view as the conversation grows.
  useEffect(() => {
    const box = transcriptRef.current;
    if (box) box.scrollTop = box.scrollHeight;
  }, [messages, asking]);

  const ask = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || asking) return;
    setAsking(true);
    setError('');
    try {
      const state = subject === 'report'
        ? await apiService.askReportChat(id, trimmed)
        : await apiService.askPrescriptionChat(id, trimmed);
      setMessages(state.messages);
      setQuestion('');
    } catch (err) {
      setError(apiErrorMessage(err, 'The model did not answer'));
    } finally {
      setAsking(false);
    }
  };

  const clear = async () => {
    if (!(await confirm('Clear this conversation? The questions and answers are deleted.'))) return;
    try {
      const cleared = subject === 'report'
        ? await apiService.clearReportChat(id)
        : await apiService.clearPrescriptionChat(id);
      setMessages(cleared.messages);
      toast('Conversation cleared', 'success');
    } catch (err) {
      toast(apiErrorMessage(err, 'Could not clear the conversation'), 'error');
    }
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    ask(question);
  };

  // Enter sends, Shift+Enter starts a new line, as a chat box is expected to behave.
  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      ask(question);
    }
  };

  if (loading) return <div className="skeleton report-chat-card" />;

  return (
    <div className="card report-chat-card">
      <div className="row-between" style={{ gap: 'var(--space-3)' }}>
        <div style={{ minWidth: 0 }}>
          <h3 style={{ fontSize: 'var(--font-lg)' }}>Ask about this {LABEL[subject]}</h3>
          <p className="form-hint" style={{ marginTop: 'var(--space-1)' }}>
            Answered from this {LABEL[subject]} only{model ? ` by ${model}` : ''}. Your name, phone numbers,
            and emails are replaced before it is sent.
          </p>
        </div>
        <div className="row" style={{ gap: 'var(--space-1)', flexShrink: 0 }}>
          {messages.length > 0 && (
            <button type="button" className="btn btn-ghost btn-sm" onClick={clear}>Clear</button>
          )}
          {onClose && (
            <button type="button" className="modal-close" onClick={onClose} aria-label="Close the AI chat">
              <IconClose size={16} />
            </button>
          )}
        </div>
      </div>

      {!configured && (
        <div className="alert alert-info" style={{ marginTop: 'var(--space-4)' }}>
          Set up the AI diagnosis model in <Link to="/settings/ai">AI settings</Link> to ask about a{' '}
          {LABEL[subject]}.
        </div>
      )}

      {/* The part that grows: the conversation, or the prompts offered before it starts. */}
      <div className="report-chat-body">
        {messages.length > 0 ? (
          <div className="report-chat-transcript" ref={transcriptRef}>
            {messages.map((message, index) => (
              <div key={index} className={`report-chat-message report-chat-message-${message.role}`}>
                <span className="report-chat-who">{message.role === 'user' ? 'You' : 'AI'}</span>
                <div className="report-chat-text">{message.content}</div>
              </div>
            ))}
            {asking && (
              <div className="report-chat-message report-chat-message-assistant">
                <span className="report-chat-who">AI</span>
                <div className="report-chat-text form-hint">Reading the report…</div>
              </div>
            )}
          </div>
        ) : (
          configured && (
            <div className="report-chat-prompts">
              {SUGGESTIONS[subject]
                .filter(text => hasRows || !text.includes(NEEDS_ROWS[subject]))
                .map(text => (
                <button
                  key={text}
                  type="button"
                  className="btn btn-secondary btn-sm"
                  disabled={asking}
                  onClick={() => ask(text)}
                >
                  {text}
                </button>
              ))}
            </div>
          )
        )}
      </div>

      {error && <div className="alert alert-error" style={{ marginTop: 'var(--space-3)' }}>{error}</div>}

      <form onSubmit={submit} style={{ marginTop: 'var(--space-3)' }}>
        <textarea
          className="form-textarea report-chat-input"
          value={question}
          onChange={e => setQuestion(e.target.value)}
          onKeyDown={onKeyDown}
          disabled={!configured || asking}
          placeholder={subject === 'report'
            ? 'Ask what a result means, what is out of range, or what to raise with your doctor…'
            : 'Ask what a medicine is for, how to take it, or what to raise with your doctor…'}
          aria-label={`Ask about this ${LABEL[subject]}`}
        />
        <div className="row-between" style={{ gap: 'var(--space-3)', marginTop: 'var(--space-2)' }}>
          <span className="form-hint">
            An explanation of what is written here, not a diagnosis or medical advice. Only your prescriber
            can change a prescription.
          </span>
          <button type="submit" className="btn btn-primary btn-sm" disabled={!configured || asking || !question.trim()}>
            {asking ? 'Asking…' : 'Ask'}
          </button>
        </div>
      </form>
    </div>
  );
};

export default AIChatPanel;
