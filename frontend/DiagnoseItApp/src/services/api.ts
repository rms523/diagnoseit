/**
 * React Native API client for DiagnoseIt.
 * Token persistence is handled by AuthContext (SecureStore); this module only holds the in-memory token.
 */
import Constants from 'expo-constants';

const CONFIGURED_API_URL =
  process.env.EXPO_PUBLIC_API_URL ||
  Constants.expoConfig?.extra?.apiUrl;

if (
  !__DEV__
  && (
    !CONFIGURED_API_URL
    || !/^https:\/\//i.test(CONFIGURED_API_URL)
  )
) {
  throw new Error('An HTTPS EXPO_PUBLIC_API_URL must be set for release builds');
}

const API_BASE_URL = CONFIGURED_API_URL || 'http://localhost:8000/api';

export function getApiOrigin(): string {
  return API_BASE_URL.replace(/\/api\/?$/, '');
}

export function mediaUrl(path: string): string {
  if (path.startsWith('http')) return path;
  return `${getApiOrigin()}${path.startsWith('/') ? path : `/${path}`}`;
}

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
  created_at?: string;
  updated_at?: string;
}

export type ReportParseStatus = 'PENDING' | 'PROCESSING' | 'COMPLETED' | 'FAILED';

export interface MedicalReport {
  id: number;
  title: string;
  report_type: string;
  lab_name?: string;
  report_date: string;
  file?: string;
  parsed_data: Record<string, unknown>;
  is_parsed: boolean;
  status?: ReportParseStatus;
  parse_error?: string;
  test_results: TestResult[];
  notes?: string;
  created_at: string;
  updated_at: string;
}

export interface ReportStatusResponse {
  id: number;
  status: ReportParseStatus;
  is_parsed: boolean;
  parse_error: string;
}

export interface PrescriptionStatusResponse extends ReportStatusResponse {
  medication_count: number;
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

export interface TestResult {
  id: number;
  test_type_name?: string;
  test_name: string;
  value: string;
  unit: string;
  reference_range: string;
  status: 'NORMAL' | 'HIGH' | 'LOW' | 'ABNORMAL';
  notes: string;
  created_at: string;
}

export interface TestResultUpdateResponse {
  id: number;
  value: string;
  unit: string;
  status: string;
}

export interface Prescription {
  id: number;
  doctor_name?: string;
  hospital_clinic?: string;
  prescription_date: string;
  file?: string;
  parsed_data: Record<string, unknown>;
  is_parsed: boolean;
  status?: ReportParseStatus;
  parse_error?: string;
  medications: Medication[];
  notes: string;
  created_at: string;
  updated_at: string;
}

export interface Medication {
  id: number;
  medication_name: string;
  dosage: string;
  frequency: string;
  duration: string;
  instructions: string;
  created_at: string;
}

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
  created_at: string;
  updated_at: string;
}

export interface HealthTrendPoint {
  date: string;
  value: string;
  unit: string;
  status: string;
  reference_range: string;
}

export interface HealthTrendData {
  parameter: string;
  trends: HealthTrendPoint[];
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
  category: string;
  default_unit?: string;
  normal_min?: string | null;
  normal_max?: string | null;
  aliases?: string[];
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

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

/** React Native file descriptor for multipart uploads */
export interface UploadFile {
  uri: string;
  name: string;
  type: string;
}

class ApiService {
  private token: string | null = null;

  getToken(): string | null {
    return this.token;
  }

  setToken(token: string) {
    this.token = token;
  }

  clearToken() {
    this.token = null;
  }

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const url = `${API_BASE_URL}${endpoint}`;
    const headers: Record<string, string> = {};

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
      throw new Error(`API Error: ${response.status} ${response.statusText} - ${errorText}`);
    }

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

  async uploadMedicalReport(
    file: UploadFile,
    title: string,
    report_type: string = 'LAB',
    lab_name?: string,
    report_date?: string,
    notes?: string
  ): Promise<MedicalReport> {
    const formData = new FormData();
    formData.append('file', { uri: file.uri, name: file.name, type: file.type } as unknown as Blob);
    formData.append('title', title);
    formData.append('report_type', report_type);
    if (lab_name) formData.append('lab_name', lab_name);
    if (report_date) formData.append('report_date', report_date);
    if (notes) formData.append('notes', notes);

    return this.request<MedicalReport>('/medical-reports/reports/', {
      method: 'POST',
      body: formData,
    });
  }

  async bulkUploadMedicalReports(files: UploadFile[]): Promise<BulkUploadResult> {
    const formData = new FormData();
    files.forEach(file => {
      formData.append('files', { uri: file.uri, name: file.name, type: file.type } as unknown as Blob);
    });
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

  async getHealthTrends(parameter?: string): Promise<HealthTrendData> {
    const query = parameter ? `?parameter=${encodeURIComponent(parameter)}` : '';
    return this.request<HealthTrendData>(`/medical-reports/trends/${query}`);
  }

  /* ---- Lab Tests ---- */

  async getLabTestUnits(testType: string): Promise<LabTestTypeUnit[]> {
    const q = new URLSearchParams({ test_type: testType });
    return this.request<LabTestTypeUnit[]>(`/lab-tests/units/?${q}`);
  }

  async getLabTestCategories(): Promise<string[]> {
    return this.request<string[]>('/lab-tests/categories/test-types/');
  }

  async getLabTestTypes(params?: { category?: string; q?: string; page?: number }): Promise<PaginatedResponse<LabTestType>> {
    const q = new URLSearchParams();
    if (params?.category) q.set('category', params.category);
    if (params?.q) q.set('q', params.q);
    if (params?.page) q.set('page', String(params.page));
    const query = q.toString();
    return this.request<PaginatedResponse<LabTestType>>(`/lab-tests/types/${query ? `?${query}` : ''}`);
  }

  async getAllLabTestTypes(category?: string): Promise<LabTestType[]> {
    const all: LabTestType[] = [];
    let page = 1;
    while (true) {
      const res = await this.getLabTestTypes({ category, page });
      all.push(...(res.results ?? []));
      if (!res.next) break;
      page += 1;
    }
    return all;
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

  /* ---- Prescriptions ---- */

  async getPrescriptions(): Promise<Prescription[]> {
    return this.listAll<Prescription>('/prescriptions/prescriptions/');
  }

  async getPrescription(id: number): Promise<Prescription> {
    return this.request<Prescription>(`/prescriptions/prescriptions/${id}/`);
  }

  async getPrescriptionStatus(id: number): Promise<PrescriptionStatusResponse> {
    return this.request<PrescriptionStatusResponse>(`/prescriptions/prescriptions/${id}/status/`);
  }

  async uploadPrescription(
    file: UploadFile,
    doctor_name?: string,
    hospital_clinic?: string,
    prescription_date?: string,
    notes?: string
  ): Promise<Prescription> {
    const formData = new FormData();
    formData.append('file', { uri: file.uri, name: file.name, type: file.type } as unknown as Blob);
    if (doctor_name) formData.append('doctor_name', doctor_name);
    if (hospital_clinic) formData.append('hospital_clinic', hospital_clinic);
    if (prescription_date) formData.append('prescription_date', prescription_date);
    if (notes) formData.append('notes', notes);

    return this.request<Prescription>('/prescriptions/prescriptions/', {
      method: 'POST',
      body: formData,
    });
  }

  async deletePrescription(id: number): Promise<void> {
    return this.request(`/prescriptions/prescriptions/${id}/`, { method: 'DELETE' });
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

  async createSymptomLog(
    symptomId: number,
    data: { severity: number; notes?: string }
  ): Promise<SymptomLog> {
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

  async deleteDiagnosis(id: number): Promise<void> {
    return this.request(`/diagnosis/diagnoses/${id}/`, { method: 'DELETE' });
  }

  async generateDiagnosis(data: {
    symptoms: string[];
    include_medical_history?: boolean;
    include_test_results?: boolean;
  }): Promise<Diagnosis> {
    return this.request<Diagnosis>('/diagnosis/diagnoses/generate/', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }
}

export const apiService = new ApiService();
