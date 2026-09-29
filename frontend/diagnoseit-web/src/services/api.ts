/**
 * API service for DiagnoseIt application
 */

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api';

/* ---------- Type definitions ---------- */

export interface User {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  date_of_birth?: string;
  gender?: 'M' | 'F' | 'O';
  phone_number?: string;
  emergency_contact?: string;
  emergency_phone?: string;
  /** The user's own summary, sent with health timeline diagnoses. */
  health_summary?: string;
  is_staff?: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface MedicalReport {
  id: number;
  title: string;
  report_type: string;
  lab_name?: string;
  report_date: string;
  file?: string;
  parsed_data: Record<string, unknown>;
  is_parsed: boolean;
  status?: 'PENDING' | 'PROCESSING' | 'COMPLETED' | 'FAILED';
  parse_error?: string;
  ai_review?: StoredReportReview | null;
  /** List responses only: the review's progress, so reports need not be opened one by one. */
  ai_review_summary?: AIReviewSummary;
  test_results: TestResult[];
  /** Detail responses only: the reports before and after this one in the report list. */
  neighbors?: ReportNeighbors | null;
  notes?: string;
  created_at: string;
  updated_at: string;
}

/** One turn of the conversation about a report. */
export interface ReportChatMessage {
  role: 'user' | 'assistant';
  content: string;
  at?: string;
}

export interface ReportChatState {
  messages: ReportChatMessage[];
  /** Whether the AI diagnosis model is set up; without it a question cannot be asked. */
  configured: boolean;
  model: string;
}

export interface ReportBrief {
  id: number;
  title: string;
}

export interface ReportNeighbors {
  previous: ReportBrief | null;
  next: ReportBrief | null;
  position: number;
  total: number;
}

export interface TestResultSearchHit {
  id: number;
  test_name: string;
  value: string;
  unit: string;
  reference_range: string;
  status: string;
  test_type_name: string | null;
  report: { id: number; title: string; report_date: string; lab_name: string };
}

export interface ReportStatusResponse {
  id: number;
  status: 'PENDING' | 'PROCESSING' | 'COMPLETED' | 'FAILED';
  is_parsed: boolean;
  parse_error: string;
  ai_review_status?: '' | 'pending' | 'completed' | 'failed';
}

export interface BulkUploadResult {
  total: number;
  created: number;
  errors: number;
  reports: Array<{
    id: number;
    title: string;
    report_date: string;
    status: string;
    is_parsed: boolean;
  }>;
  error_details: Array<{ file: string; error: string }>;
}

export interface LabTestTypeUnit {
  id: number;
  test_type_name: string;
  unit: {
    id: number;
    name: string;
    display_name: string;
    symbol: string;
  };
  normal_min?: string | null;
  normal_max?: string | null;
}

export interface LabTestType {
  id: number;
  name: string;
  display_name: string;
  description?: string;
  category: string;
  default_unit?: string;
  normal_min?: string | null;
  normal_max?: string | null;
  aliases?: string[];
  is_active?: boolean;
  /** 'user' for an entry added in the app; 'catalog' for a built-in one. */
  source?: 'catalog' | 'user';
  /** Set once someone edits the entry here, which stops populate_lab_tests overwriting it on deploy. */
  edited_by_user?: boolean;
  /** Stored results linked to this test; removing it unlinks them, it never deletes them. */
  result_count?: number;
}

/** The fields of a catalog entry someone can set; the key (name) cannot change once results use it. */
export interface LabTestTypeInput {
  name?: string;
  display_name: string;
  description?: string;
  category?: string;
  aliases?: string[];
  default_unit?: string;
  normal_min?: string | null;
  normal_max?: string | null;
  is_active?: boolean;
}

export interface LabTestUnit {
  id: number;
  name: string;
  display_name: string;
  symbol: string;
  category: string;
}

export interface UnitConversionResult {
  original_value: string;
  original_unit: string;
  converted_value: string;
  converted_unit: string;
  conversion_factor: string;
  formula: string;
}

export interface LabTestValidationResult {
  status: string;
  message: string;
  value: string;
  unit: string;
  normal_range?: string | null;
  critical_range?: string | null;
}

export interface TestResultUpdateResponse {
  id: number;
  value: string;
  unit: string;
  status: string;
}

export interface TestResult {
  id: number;
  test_type_name?: string | null;
  test_name: string;
  value: string;
  unit: string;
  reference_range: string;
  status: 'NORMAL' | 'HIGH' | 'LOW' | 'ABNORMAL';
  notes: string;
  created_at: string;
}

export type TestResultFields = Pick<TestResult, 'test_name' | 'value' | 'unit' | 'reference_range'>;

export interface NewTestResult extends TestResultFields {
  status?: string;
  notes?: string;
}

export type ReviewSuggestion = { id: number; row_seen?: boolean } & (
  | {
      action: 'update';
      result_id: number;
      changes: Partial<TestResultFields> & { status?: string };
      catalog_name?: string | null;
      reason: string;
    }
  | { action: 'remove'; result_id: number; reason: string }
  | {
      action: 'add';
      result: TestResultFields & { status: string };
      catalog_name: string | null;
      reason: string;
    }
);

/** A stretch of a long report whose review request failed; its pages were not checked. */
export interface ReviewFailedPart {
  part: number;
  first_page: number;
  last_page: number;
  error: string;
}

/** A suggestion that changed the results, with what it replaced so it can be undone. */
export type AppliedReviewChange = { id: number; reason: string; automatic: boolean; applied_at: string } & (
  | {
      action: 'update';
      result_id: number;
      changes: Partial<TestResultFields> & { status?: string };
      before: Partial<TestResultFields> & { status?: string };
    }
  | { action: 'remove'; result: TestResultFields & { status: string } }
  | { action: 'add'; result_id: number; result: TestResultFields & { status: string } }
);

export interface ReportReview {
  status: 'completed';
  summary: string;
  suggestions: ReviewSuggestion[];
  applied?: AppliedReviewChange[];
  model: string;
  /** What the model was shown: PDF text, page images, OCR text of the pages, or page images with OCR text. */
  input_mode: 'text' | 'images' | 'ocr' | 'images_ocr';
  parts: number;
  failed_parts: ReviewFailedPart[];
  reviewed_at: string;
}

export interface AIReviewSummary {
  status: '' | 'pending' | 'completed' | 'failed';
  /** A pending review is running rather than waiting behind other reports. */
  started: boolean;
  open_suggestions: number;
}

export interface BulkReviewResult {
  queued: number[];
  skipped: { id: number; reason: string }[];
}

export interface ReviewActionResponse {
  review: StoredReportReview | null;
  test_results: TestResult[];
  applied?: number[];
}

export type StoredReportReview =
  | ReportReview
  | { status: 'pending'; queued_at: string; started_at?: string }
  | { status: 'failed'; error: string; reviewed_at: string | null };

export type AIRole = 'diagnosis' | 'ocr' | 'report_review';

export interface AIServiceSettings {
  role: AIRole;
  label: string;
  source: 'database' | 'environment' | 'diagnosis';
  enabled: boolean;
  provider: 'openai' | 'ollama';
  base_url: string;
  model: string;
  timeout_seconds: number;
  max_tokens: number;
  /** null: the service's default_temperature is used. */
  temperature: number | null;
  default_temperature: number;
  /** Report OCR only: pages sent to the server at once. */
  parallel_requests: number;
  ocr_mode: 'auto' | 'paddle_ocr' | 'json_vlm';
  review_input: 'auto' | 'text' | 'images';
  auto_review: boolean;
  auto_apply: boolean;
  api_key_set: boolean;
  is_configured: boolean;
  updated_at: string | null;
  updated_by: string | null;
}

export type AIServiceSettingsUpdate = Partial<
  Pick<
    AIServiceSettings,
    | 'enabled'
    | 'provider'
    | 'base_url'
    | 'model'
    | 'timeout_seconds'
    | 'max_tokens'
    | 'temperature'
    | 'parallel_requests'
    | 'ocr_mode'
    | 'review_input'
    | 'auto_review'
    | 'auto_apply'
  >
> & { api_key?: string; clear_api_key?: boolean };

export interface AIConnectionCheck {
  ok: boolean;
  models: string[];
  latency_ms?: number;
  warning?: string;
  error?: string;
}

export interface AIStatus {
  report_review: { available: boolean; model: string; auto_review: boolean };
  diagnosis: { available: boolean };
  ocr?: { available: boolean };
}

export interface Prescription {
  id: number;
  doctor_name?: string;
  hospital_clinic?: string;
  prescription_date: string;
  file?: string;
  parsed_data: Record<string, unknown>;
  is_parsed: boolean;
  /** Reading runs in the background, like a report's: an upload comes back PENDING. */
  status?: 'PENDING' | 'PROCESSING' | 'COMPLETED' | 'FAILED';
  parse_error?: string;
  ai_review?: PrescriptionReview | null;
  medications: Medication[];
  notes: string;
  created_at: string;
  updated_at: string;
}

/** One thing the AI review thinks is wrong with a prescription's medicines. */
export interface PrescriptionSuggestion {
  id: number;
  action: 'update' | 'add' | 'remove';
  /** update and remove: the medicine it is about. */
  medication_id?: number;
  /** add: the medicine to create. */
  medication?: MedicationFields;
  /** update: only the fields that should change. */
  changes?: Partial<MedicationFields>;
  reason: string;
}

/** An accepted suggestion, with what it replaced, so it can be undone. */
export interface PrescriptionAppliedChange {
  id: number;
  suggestion_id: number;
  action: 'update' | 'add' | 'remove';
  medication_id?: number;
  before?: MedicationFields;
  after?: MedicationFields;
  at: string;
}

export interface PrescriptionReview {
  status: 'pending' | 'completed' | 'failed';
  error?: string;
  verdict?: 'correct' | 'changes';
  model?: string;
  /** 'text_image' when the original image was checked too, which catches what OCR itself got wrong. */
  input_mode?: 'text' | 'text_image';
  started_at?: string;
  suggestions?: PrescriptionSuggestion[];
  applied?: PrescriptionAppliedChange[];
}

/** Every review action answers with the review and the medicines as they now stand. */
export interface PrescriptionReviewResponse {
  id: number;
  ai_review: PrescriptionReview | null;
  medications: Medication[];
  accepted?: number[];
}

export interface PrescriptionStatusResponse {
  id: number;
  status: 'PENDING' | 'PROCESSING' | 'COMPLETED' | 'FAILED';
  is_parsed: boolean;
  parse_error: string;
  medication_count: number;
  ai_review_status?: '' | 'pending' | 'completed' | 'failed';
}

/** What a prescription upload accepts: a clinic PDF, or a photograph of the paper. */
export const PRESCRIPTION_FILE_ACCEPT =
  '.pdf,.jpg,.jpeg,.png,.webp,.bmp,.tif,.tiff,.heic,.heif,application/pdf,image/*';

export interface Medication {
  id: number;
  medication_name: string;
  dosage: string;
  frequency: string;
  duration: string;
  instructions: string;
  created_at: string;
}

/** The fields of a medicine someone can correct; OCR gets a handwritten name wrong often enough to matter. */
export type MedicationFields = Pick<
  Medication, 'medication_name' | 'dosage' | 'frequency' | 'duration' | 'instructions'
>;

export interface Symptom {
  id: number;
  description: string;
  severity: 1 | 2 | 3 | 4;
  duration: 'ACUTE' | 'SUBACUTE' | 'CHRONIC';
  body_part?: string;
  onset_date: string;
  end_date?: string;
  is_ongoing: boolean;
  notes: string;
  logs?: SymptomLog[];
  created_at: string;
  updated_at: string;
}

export interface SymptomLog {
  id: number;
  severity: number;
  notes: string;
  logged_at: string;
}

/** One explanation the model considered, with what it rests on and what would settle it. */
export interface DiagnosisCandidate {
  condition: string;
  likelihood: 'most likely' | 'possible' | 'less likely';
  confidence: 1 | 2 | 3 | 4 | 5;
  reasoning: string;
  supporting: string[];
  against: string[];
  confirm_with: string[];
  rule_out_with: string[];
}

/** A candidate the model thinks is most likely to be its own false alarm. */
export interface DiagnosisFalsePositive {
  condition: string;
  why_it_might_be_wrong: string;
  how_to_tell: string;
}

/** The reasoning behind a diagnosis; `condition_name` above is the differential's leading entry. */
export interface DiagnosisAnalysis {
  summary?: string;
  differential?: DiagnosisCandidate[];
  false_positives?: DiagnosisFalsePositive[];
  patterns?: string[];
  cautions?: string[];
  red_flags?: string[];
}

export interface Diagnosis {
  id: number;
  condition_name: string;
  description: string;
  confidence_score: 1 | 2 | 3 | 4 | 5;
  symptoms_considered: number[];
  test_results_considered: number[];
  recommendations: string;
  follow_up_required: boolean;
  follow_up_notes: string;
  /** The differential and the reasoning behind it; empty for diagnoses made before this existed. */
  analysis?: DiagnosisAnalysis;
  /** Set for health timeline diagnoses: what the diagnosis was based on. */
  context?: DiagnosisContext;
  created_at: string;
  updated_at: string;
}

export type DiagnosisPeriod = '3m' | '6m' | '1y' | '2y' | 'all';

export interface DiagnosisTimelineCounts {
  reports?: number;
  results?: number;
  symptoms?: number;
  symptom_updates?: number;
  prescriptions?: number;
  medications?: number;
  assessments?: number;
}

export interface DiagnosisContext {
  mode?: 'timeline';
  period?: DiagnosisPeriod;
  since?: string | null;
  until?: string;
  counts?: DiagnosisTimelineCounts;
  omitted_dates?: number;
  summary_included?: boolean;
}

export interface DiagnosisTimelinePreview {
  prompt: string;
  since: string | null;
  until: string;
  counts: DiagnosisTimelineCounts;
  omitted_dates: number;
}

/** One result in a trend; value, unit, and reference_range are in the trend's unit when unit_status is 'converted'. */
export interface HealthTrendPoint {
  date: string;
  report_id: number;
  report_title: string;
  result_id: number;
  printed_name: string;
  value: string;
  unit: string;
  status: string;
  reference_range: string;
  original_value: string;
  original_unit: string;
  original_reference_range: string;
  /** 'unconverted': printed in another unit with no known conversion, so it is not plotted. */
  unit_status: 'same' | 'converted' | 'unconverted';
}

export interface HealthTrendData {
  /** How the trend was asked for ("type:hemoglobin", "name:<printed name>"); unique per test. */
  key: string;
  parameter: string;
  /** The catalog test, or null for a printed name the catalog does not know. */
  test_type: string | null;
  unit: string;
  unconverted_count: number;
  trends: HealthTrendPoint[];
}

/** One test to chart: a catalog test, a printed name the catalog does not know, or a typed search. */
export interface TrendSelection {
  kind: 'test_type' | 'name' | 'parameter';
  value: string;
}

/** A printed test name this user linked to a catalog test. */
export interface TestNameLink {
  id: number;
  name: string;
  test_type: string;
  test_type_display_name: string;
  created_at: string;
}

export interface TestNameLinkSuggestion {
  name: string;
  test_type: string | null;
  test_type_display_name: string | null;
  reason: string;
}

/** A test with results: one per catalog test, or per printed name that matches no catalog test. */
export interface HealthTrendParameter {
  key: string;
  name: string;
  test_type: string | null;
  result_count: number;
  /** Results with a number; a name with none ("Negative", "Absent") cannot be linked to a catalog test. */
  numeric_count: number;
  printed_names: string[];
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

/* ---------- API Service class ---------- */

class ApiService {
  private token: string | null = null;

  constructor() {
    this.token = localStorage.getItem('authToken');
  }

  getToken(): string | null {
    return this.token;
  }

  setToken(token: string) {
    this.token = token;
    localStorage.setItem('authToken', token);
  }

  clearToken() {
    this.token = null;
    localStorage.removeItem('authToken');
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${API_BASE_URL}${endpoint}`;
    const headers: Record<string, string> = {};

    // Only set Content-Type for non-FormData requests
    if (!(options.body instanceof FormData)) {
      headers['Content-Type'] = 'application/json';
    }

    if (this.token) {
      headers['Authorization'] = `Token ${this.token}`;
    }

    const response = await fetch(url, {
      ...options,
      headers: {
        ...headers,
        ...(options.headers as Record<string, string> || {}),
      },
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(
        `API Error: ${response.status} ${response.statusText} - ${errorText}`
      );
    }

    // Handle 204 No Content
    if (response.status === 204) {
      return undefined as unknown as T;
    }

    return response.json();
  }

  private async listAll<T>(endpoint: string): Promise<T[]> {
    const all: T[] = [];
    let page = 1;
    const separator = endpoint.includes('?') ? '&' : '?';

    while (true) {
      const response = await this.request<PaginatedResponse<T>>(
        `${endpoint}${separator}page=${page}`
      );
      all.push(...(response.results ?? []));
      if (!response.next) break;
      page += 1;
    }

    return all;
  }

  /* ---- Auth ---- */

  async login(username: string, password: string): Promise<{ user: User; token: string }> {
    const response = await this.request<{ user: User; token: string }>('/auth/login/', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    });
    this.setToken(response.token);
    return response;
  }

  /** Whether this server accepts new accounts (always for the first one). */
  async getRegistrationStatus(): Promise<{ open: boolean }> {
    return this.request<{ open: boolean }>('/auth/registration/');
  }

  async register(userData: {
    username: string;
    email: string;
    password: string;
    password_confirm: string;
    first_name?: string;
    last_name?: string;
  }): Promise<{ user: User; token: string }> {
    const response = await this.request<{ user: User; token: string }>('/auth/register/', {
      method: 'POST',
      body: JSON.stringify(userData),
    });
    this.setToken(response.token);
    return response;
  }

  async logout(): Promise<void> {
    try {
      await this.request('/auth/logout/', { method: 'POST' });
    } finally {
      this.clearToken();
    }
  }

  async getProfile(): Promise<User> {
    return this.request<User>('/auth/profile/');
  }

  async updateProfile(userData: Partial<User>): Promise<User> {
    return this.request<User>('/auth/profile/', {
      method: 'PATCH',
      body: JSON.stringify(userData),
    });
  }

  /* ---- Medical Reports ---- */

  async getMedicalReports(): Promise<MedicalReport[]> {
    return this.listAll<MedicalReport>('/medical-reports/reports/');
  }

  async getMedicalReport(id: number): Promise<MedicalReport> {
    return this.request<MedicalReport>(`/medical-reports/reports/${id}/`);
  }

  /** The original report PDF, fetched with the auth token so it never depends on an expiring link. */
  async getMedicalReportFile(id: number): Promise<Blob> {
    const response = await fetch(`${API_BASE_URL}/medical-reports/reports/${id}/download/`, {
      headers: this.token ? { Authorization: `Token ${this.token}` } : {},
    });
    if (!response.ok) {
      throw new Error(`API Error: ${response.status} ${response.statusText} - `);
    }
    return response.blob();
  }

  async uploadMedicalReport(
    file: File,
    title: string,
    report_type: string = 'LAB',
    lab_name?: string,
    report_date?: string,
    notes?: string,
    aiReview?: boolean
  ): Promise<MedicalReport> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('title', title);
    formData.append('report_type', report_type);
    if (lab_name) formData.append('lab_name', lab_name);
    if (report_date) formData.append('report_date', report_date);
    if (notes) formData.append('notes', notes);
    if (aiReview !== undefined) formData.append('ai_review', String(aiReview));

    return this.request<MedicalReport>('/medical-reports/reports/', {
      method: 'POST',
      body: formData,
    });
  }

  /** aiReview reviews each parsed file with AI; leave it undefined to follow AI settings. */
  async bulkUploadMedicalReports(files: File[], aiReview?: boolean): Promise<BulkUploadResult> {
    const formData = new FormData();
    files.forEach(file => formData.append('files', file));
    if (aiReview !== undefined) formData.append('ai_review', String(aiReview));
    return this.request<BulkUploadResult>('/medical-reports/reports/bulk-upload/', {
      method: 'POST',
      body: formData,
    });
  }

  async deleteMedicalReport(id: number): Promise<void> {
    return this.request(`/medical-reports/reports/${id}/`, { method: 'DELETE' });
  }

  async getReportStatus(id: number): Promise<ReportStatusResponse> {
    return this.request<ReportStatusResponse>(`/medical-reports/reports/${id}/status/`);
  }

  /** Queues an AI review in the background; poll the report status until it finishes. */
  /** options.ocr reads the pages with the Report OCR model; options.images sends page images, whatever the settings say. */
  async reviewReportWithAI(id: number, options: { ocr?: boolean; images?: boolean } = {}): Promise<StoredReportReview> {
    return this.request<StoredReportReview>(`/medical-reports/reports/${id}/ai-review/`, {
      method: 'POST',
      body: JSON.stringify(options),
    });
  }

  /** Stops a queued or running AI review; nothing from it is stored or applied. */
  async stopReportReview(id: number): Promise<void> {
    return this.request(`/medical-reports/reports/${id}/ai-review/stop/`, { method: 'POST' });
  }

  /** Queues AI reviews for several parsed reports; they are reviewed one at a time, in this order. */
  async reviewReportsWithAI(ids: number[]): Promise<BulkReviewResult> {
    return this.request<BulkReviewResult>('/medical-reports/reports/bulk-ai-review/', {
      method: 'POST',
      body: JSON.stringify({ ids }),
    });
  }

  async clearReportReview(id: number): Promise<void> {
    return this.request(`/medical-reports/reports/${id}/ai-review/`, { method: 'DELETE' });
  }

  async dismissReviewSuggestion(reportId: number, suggestionId: number): Promise<void> {
    return this.request(`/medical-reports/reports/${reportId}/ai-review/suggestions/${suggestionId}/`, {
      method: 'DELETE',
    });
  }

  async acceptReviewSuggestions(reportId: number, ids: number[]): Promise<ReviewActionResponse> {
    return this.request<ReviewActionResponse>(`/medical-reports/reports/${reportId}/ai-review/accept/`, {
      method: 'POST',
      body: JSON.stringify({ ids }),
    });
  }

  async undoReviewChange(reportId: number, appliedId: number): Promise<ReviewActionResponse> {
    return this.request<ReviewActionResponse>(
      `/medical-reports/reports/${reportId}/ai-review/applied/${appliedId}/undo/`,
      { method: 'POST' }
    );
  }

  async getTestResults(reportId: number): Promise<TestResult[]> {
    return this.request<TestResult[]>(`/medical-reports/reports/${reportId}/test-results/`);
  }

  async createTestResult(reportId: number, data: NewTestResult): Promise<TestResult> {
    return this.request<TestResult>(`/medical-reports/reports/${reportId}/test-results/`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async searchTestResults(query: string): Promise<{ results: TestResultSearchHit[]; truncated: boolean }> {
    return this.request(`/medical-reports/test-results/search/?q=${encodeURIComponent(query)}`);
  }

  /** The conversation about a report so far. */
  async getReportChat(reportId: number): Promise<ReportChatState> {
    return this.request<ReportChatState>(`/medical-reports/reports/${reportId}/chat/`);
  }

  /** Ask about a report; the reply and the whole conversation come back. */
  async askReportChat(reportId: number, question: string): Promise<ReportChatState> {
    return this.request<ReportChatState>(`/medical-reports/reports/${reportId}/chat/`, {
      method: 'POST',
      body: JSON.stringify({ question }),
    });
  }

  async clearReportChat(reportId: number): Promise<ReportChatState> {
    return this.request<ReportChatState>(`/medical-reports/reports/${reportId}/chat/`, { method: 'DELETE' });
  }

  async deleteTestResult(reportId: number, id: number): Promise<void> {
    return this.request(`/medical-reports/reports/${reportId}/test-results/${id}/`, { method: 'DELETE' });
  }

  async updateTestResult(
    id: number,
    data: Partial<Pick<TestResult, 'value' | 'unit' | 'reference_range' | 'notes'>>
  ): Promise<TestResult> {
    return this.request<TestResult>(`/medical-reports/test-results/${id}/`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }

  async convertTestResultUnit(
    id: number,
    targetUnit: string
  ): Promise<{ id: number; value: string; unit: string }> {
    return this.request(`/medical-reports/test-results/${id}/convert-unit/`, {
      method: 'POST',
      body: JSON.stringify({ target_unit: targetUnit }),
    });
  }

  async validateTestResult(id: number): Promise<TestResultUpdateResponse> {
    return this.request<TestResultUpdateResponse>(`/medical-reports/test-results/${id}/validate/`, {
      method: 'POST',
    });
  }

  async getLabTestUnits(testType: string): Promise<LabTestTypeUnit[]> {
    const q = new URLSearchParams({ test_type: testType });
    return this.request<LabTestTypeUnit[]>(`/lab-tests/units/?${q}`);
  }

  async getLabTestCategories(): Promise<string[]> {
    return this.request<string[]>('/lab-tests/categories/test-types/');
  }

  async getLabTestTypes(
    params?: { category?: string; q?: string; page?: number; active?: 'true' | 'false' | 'all' }
  ): Promise<PaginatedResponse<LabTestType>> {
    const q = new URLSearchParams();
    if (params?.category) q.set('category', params.category);
    if (params?.q) q.set('q', params.q);
    if (params?.page) q.set('page', String(params.page));
    if (params?.active) q.set('active', params.active);
    const query = q.toString();
    return this.request<PaginatedResponse<LabTestType>>(`/lab-tests/types/${query ? `?${query}` : ''}`);
  }

  async getAllLabTestTypes(category?: string, active?: 'true' | 'false' | 'all'): Promise<LabTestType[]> {
    const all: LabTestType[] = [];
    let page = 1;
    while (true) {
      const res = await this.getLabTestTypes({ category, page, active });
      all.push(...(res.results ?? []));
      if (!res.next) break;
      page += 1;
    }
    return all;
  }

  /** Every unit the catalog knows, for the picker on the catalog page. */
  async getAllLabTestUnits(): Promise<LabTestUnit[]> {
    return this.request<LabTestUnit[]>('/lab-tests/units/');
  }

  /** A catalog key free of the ones in use, made from a display name. */
  async suggestLabTestKey(displayName: string): Promise<{ key: string }> {
    const q = new URLSearchParams({ display_name: displayName });
    return this.request<{ key: string }>(`/lab-tests/types/suggest-key/?${q}`);
  }

  /** Add a catalog entry; `relinked` counts the stored results its names claimed. */
  async createLabTestType(data: LabTestTypeInput): Promise<LabTestType & { relinked: number }> {
    return this.request('/lab-tests/types/', { method: 'POST', body: JSON.stringify(data) });
  }

  /** Change a catalog entry, by its key; `relinked` counts the results that moved because of it. */
  async updateLabTestType(name: string, data: Partial<LabTestTypeInput>): Promise<LabTestType & { relinked: number }> {
    return this.request(`/lab-tests/types/${encodeURIComponent(name)}/`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }

  /**
   * Remove a catalog entry. One added in the app is deleted; a built-in one is deactivated, since the
   * catalog loader would put it back on the next deploy. Its results are unlinked, never deleted.
   */
  async deleteLabTestType(name: string): Promise<{ removed: 'deleted' | 'deactivated'; unlinked: number }> {
    return this.request(`/lab-tests/types/${encodeURIComponent(name)}/`, { method: 'DELETE' });
  }

  async convertLabUnits(data: {
    test_type: string;
    value: string;
    from_unit: string;
    to_unit: string;
  }): Promise<UnitConversionResult> {
    return this.request<UnitConversionResult>('/lab-tests/convert/', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async validateLabTestValue(data: {
    test_type: string;
    value: string;
    unit: string;
  }): Promise<LabTestValidationResult> {
    return this.request<LabTestValidationResult>('/lab-tests/validate/', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  /** Results over time for a catalog test (testType) or a printed name matched to the catalog. */
  /** One trend: by catalog test, by a name not linked to the catalog (unlinkedName), or by a typed search (parameter). */
  async getHealthTrends(parameter?: string, testType?: string | null, unlinkedName?: string): Promise<HealthTrendData> {
    const params = new URLSearchParams();
    if (testType) params.set('test_type', testType);
    else if (unlinkedName) params.set('name', unlinkedName);
    else if (parameter) params.set('parameter', parameter);
    const query = params.toString();
    return this.request<HealthTrendData>(`/medical-reports/trends/${query ? `?${query}` : ''}`);
  }

  /** Several tests' trends in one request, so they can be drawn on one time axis. */
  async getMultiHealthTrends(selections: TrendSelection[]): Promise<HealthTrendData[]> {
    const params = new URLSearchParams();
    for (const { kind, value } of selections) {
      if (value) params.append(kind, value);
    }
    const { series } = await this.request<{ series: HealthTrendData[] }>(
      `/medical-reports/trends/multi/?${params}`
    );
    return series;
  }

  async getHealthTrendParameters(): Promise<HealthTrendParameter[]> {
    return this.request<HealthTrendParameter[]>('/medical-reports/trends/parameters/');
  }

  async getTestNameLinks(): Promise<TestNameLink[]> {
    return this.request<TestNameLink[]>('/medical-reports/test-aliases/');
  }

  async createTestNameLink(name: string, testType: string): Promise<{ alias: TestNameLink; relinked: number }> {
    return this.request('/medical-reports/test-aliases/', {
      method: 'POST',
      body: JSON.stringify({ name, test_type: testType }),
    });
  }

  async deleteTestNameLink(id: number): Promise<{ relinked: number }> {
    return this.request(`/medical-reports/test-aliases/${id}/`, { method: 'DELETE' });
  }

  async suggestTestNameLinks(names: string[]): Promise<{ suggestions: TestNameLinkSuggestion[] }> {
    return this.request('/medical-reports/test-aliases/suggest/', {
      method: 'POST',
      body: JSON.stringify({ names }),
    });
  }

  /* ---- Prescriptions ---- */

  async getPrescriptions(): Promise<Prescription[]> {
    return this.listAll<Prescription>('/prescriptions/prescriptions/');
  }

  async getPrescription(id: number): Promise<Prescription> {
    return this.request<Prescription>(`/prescriptions/prescriptions/${id}/`);
  }

  /** The original prescription, fetched with auth because it may be a PDF or a private photo. */
  async getPrescriptionFile(id: number): Promise<Blob> {
    const response = await fetch(`${API_BASE_URL}/prescriptions/prescriptions/${id}/download/`, {
      headers: this.token ? { Authorization: `Token ${this.token}` } : {},
    });
    if (!response.ok) {
      throw new Error(`API Error: ${response.status} ${response.statusText} - `);
    }
    return response.blob();
  }

  async uploadPrescription(
    file: File,
    doctor_name?: string,
    hospital_clinic?: string,
    prescription_date?: string,
    notes?: string
  ): Promise<Prescription> {
    const formData = new FormData();
    formData.append('file', file);
    if (doctor_name) formData.append('doctor_name', doctor_name);
    if (hospital_clinic) formData.append('hospital_clinic', hospital_clinic);
    if (prescription_date) formData.append('prescription_date', prescription_date);
    if (notes) formData.append('notes', notes);

    return this.request<Prescription>('/prescriptions/prescriptions/', {
      method: 'POST',
      body: formData,
    });
  }

  /** Where the background reading of a prescription has got to. */
  async getPrescriptionStatus(id: number): Promise<PrescriptionStatusResponse> {
    return this.request<PrescriptionStatusResponse>(`/prescriptions/prescriptions/${id}/status/`);
  }

  /** Read the prescription again, after the OCR or review model has been set up or changed. */
  async reparsePrescription(id: number): Promise<{ id: number; status: string }> {
    return this.request(`/prescriptions/prescriptions/${id}/reparse/`, { method: 'POST' });
  }

  async getPrescriptionChat(id: number): Promise<ReportChatState> {
    return this.request<ReportChatState>(`/prescriptions/prescriptions/${id}/chat/`);
  }

  async askPrescriptionChat(id: number, question: string): Promise<ReportChatState> {
    return this.request<ReportChatState>(`/prescriptions/prescriptions/${id}/chat/`, {
      method: 'POST',
      body: JSON.stringify({ question }),
    });
  }

  async clearPrescriptionChat(id: number): Promise<ReportChatState> {
    return this.request<ReportChatState>(`/prescriptions/prescriptions/${id}/chat/`, { method: 'DELETE' });
  }

  async deletePrescription(id: number): Promise<void> {
    return this.request(`/prescriptions/prescriptions/${id}/`, { method: 'DELETE' });
  }

  async getMedications(prescriptionId: number): Promise<Medication[]> {
    return this.request<Medication[]>(`/prescriptions/prescriptions/${prescriptionId}/medications/`);
  }

  /** Queue an AI review of a prescription's medicines against the prescription itself. */
  async reviewPrescriptionWithAI(
    id: number, options?: { images?: boolean }
  ): Promise<PrescriptionReviewResponse> {
    return this.request(`/prescriptions/prescriptions/${id}/ai-review/`, {
      method: 'POST',
      body: JSON.stringify({ images: options?.images }),
    });
  }

  async stopPrescriptionReview(id: number): Promise<PrescriptionReviewResponse> {
    return this.request(`/prescriptions/prescriptions/${id}/ai-review/stop/`, { method: 'POST' });
  }

  async acceptPrescriptionSuggestions(id: number, suggestionIds: number[]): Promise<PrescriptionReviewResponse> {
    return this.request(`/prescriptions/prescriptions/${id}/ai-review/accept/`, {
      method: 'POST',
      body: JSON.stringify({ suggestion_ids: suggestionIds }),
    });
  }

  async dismissPrescriptionSuggestion(id: number, suggestionId: number): Promise<PrescriptionReviewResponse> {
    return this.request(`/prescriptions/prescriptions/${id}/ai-review/suggestions/${suggestionId}/`, {
      method: 'DELETE',
    });
  }

  async undoPrescriptionChange(id: number, appliedId: number): Promise<PrescriptionReviewResponse> {
    return this.request(`/prescriptions/prescriptions/${id}/ai-review/applied/${appliedId}/undo/`, {
      method: 'POST',
    });
  }

  async closePrescriptionReview(id: number): Promise<PrescriptionReviewResponse> {
    return this.request(`/prescriptions/prescriptions/${id}/ai-review/close/`, { method: 'DELETE' });
  }

  async createMedication(prescriptionId: number, data: MedicationFields): Promise<Medication> {
    return this.request<Medication>(`/prescriptions/prescriptions/${prescriptionId}/medications/`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateMedication(
    prescriptionId: number, id: number, data: Partial<MedicationFields>
  ): Promise<Medication> {
    return this.request<Medication>(`/prescriptions/prescriptions/${prescriptionId}/medications/${id}/`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }

  async deleteMedication(prescriptionId: number, id: number): Promise<void> {
    return this.request(`/prescriptions/prescriptions/${prescriptionId}/medications/${id}/`, {
      method: 'DELETE',
    });
  }

  /* ---- Symptoms ---- */

  async getSymptoms(): Promise<Symptom[]> {
    return this.listAll<Symptom>('/symptoms/symptoms/');
  }

  async getSymptom(id: number): Promise<Symptom> {
    return this.request<Symptom>(`/symptoms/symptoms/${id}/`);
  }

  async getActiveSymptoms(): Promise<Symptom[]> {
    return this.request<Symptom[]>('/symptoms/symptoms/active/');
  }

  async createSymptom(symptomData: {
    description: string;
    severity: 1 | 2 | 3 | 4;
    duration: 'ACUTE' | 'SUBACUTE' | 'CHRONIC';
    body_part?: string;
    onset_date: string;
    notes?: string;
  }): Promise<Symptom> {
    return this.request<Symptom>('/symptoms/symptoms/', {
      method: 'POST',
      body: JSON.stringify(symptomData),
    });
  }

  async updateSymptom(id: number, data: Partial<Symptom>): Promise<Symptom> {
    return this.request<Symptom>(`/symptoms/symptoms/${id}/`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }

  async deleteSymptom(id: number): Promise<void> {
    return this.request(`/symptoms/symptoms/${id}/`, { method: 'DELETE' });
  }

  async getSymptomLogs(symptomId: number): Promise<SymptomLog[]> {
    return this.request<SymptomLog[]>(`/symptoms/symptoms/${symptomId}/logs/`);
  }

  async createSymptomLog(symptomId: number, data: { severity: number; notes?: string }): Promise<SymptomLog> {
    return this.request<SymptomLog>(`/symptoms/symptoms/${symptomId}/logs/`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  /* ---- Diagnosis ---- */

  async getDiagnoses(): Promise<Diagnosis[]> {
    return this.listAll<Diagnosis>('/diagnosis/diagnoses/');
  }

  async getDiagnosis(id: number): Promise<Diagnosis> {
    return this.request<Diagnosis>(`/diagnosis/diagnoses/${id}/`);
  }

  async previewDiagnosisTimeline(data: {
    period: DiagnosisPeriod;
    summary: string;
    symptoms: string[];
  }): Promise<DiagnosisTimelinePreview> {
    return this.request<DiagnosisTimelinePreview>('/diagnosis/diagnoses/timeline-preview/', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async deleteDiagnosis(id: number): Promise<void> {
    return this.request(`/diagnosis/diagnoses/${id}/`, { method: 'DELETE' });
  }

  async generateDiagnosis(data: {
    symptoms: string[];
    include_medical_history?: boolean;
    include_test_results?: boolean;
    /** 'timeline' sends the user's whole dated history for the period, with their summary. */
    mode?: 'symptoms' | 'timeline';
    period?: DiagnosisPeriod;
    summary?: string;
  }): Promise<Diagnosis> {
    return this.request<Diagnosis>('/diagnosis/diagnoses/generate/', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  /* ---- AI settings ---- */

  async getAIStatus(): Promise<AIStatus> {
    return this.request<AIStatus>('/ai-settings/status/');
  }

  async getAISettings(): Promise<AIServiceSettings[]> {
    const response = await this.request<{ services: AIServiceSettings[] }>('/ai-settings/');
    return response.services;
  }

  async updateAISettings(role: AIRole, data: AIServiceSettingsUpdate): Promise<AIServiceSettings> {
    return this.request<AIServiceSettings>(`/ai-settings/${role}/`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }

  async resetAISettings(role: AIRole): Promise<AIServiceSettings> {
    return this.request<AIServiceSettings>(`/ai-settings/${role}/`, { method: 'DELETE' });
  }

  async testAISettings(role: AIRole, data: AIServiceSettingsUpdate): Promise<AIConnectionCheck> {
    return this.request<AIConnectionCheck>(`/ai-settings/${role}/test/`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }
}

export const apiService = new ApiService();
