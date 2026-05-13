export type Website = {
  id: number
  url: string
  company_name: string
  logo_url: string
  created_at: string
  updated_at: string
}

export type Scan = {
  id: number
  website_id: number
  status: string
  progress: number
  message: string
  items_found: number
  items_processed: number
  error: string
  created_at: string
  started_at: string | null
  completed_at: string | null
  duration_seconds: number
  normal_db_size_mb: number
  vector_db_size_mb: number
  scan_max_parallel_items: number
}

export type DocumentItem = {
  id: number
  website_id: number
  source_url: string
  title: string
  content_type: string
  file_name: string
  storage_path: string
  text_hash: string
  summary: string
  display_summary: string
  vector_status: string
  created_at: string
}

export type DocumentDetail = DocumentItem & {
  text_content: string
}

export type ModelConfig = {
  id: number
  provider: string
  model: string
  purpose: string
  best_for: string
  is_default: boolean
  is_available: boolean
}

export type User = {
  id: number
  email: string
  name: string
  role: string
  is_active: boolean
  created_at: string
  last_login_at: string | null
}

export type ProviderSettings = {
  openai_configured: boolean
  openrouter_configured: boolean
  google_auth_enabled: boolean
  google_client_secret_configured: boolean
  google_client_id: string
  app_url: string
  app_url_origin: string
  google_redirect_uri: string
  google_authorized_domains: string[]
  default_summary_provider: string
  default_summary_model: string
  default_embedding_provider: string
  default_embedding_model: string
  scan_max_items: number
  scan_max_file_mb: number
  scan_max_depth: number
  scan_max_parallel_items: number
  warnings: string[]
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...(options?.headers ?? {}) },
    ...options
  })
  if (!response.ok) throw new Error(await response.text())
  return response.json()
}

export const api = {
  health: () => request<{ status: string }>('/api/health'),
  session: () => request<User>('/api/auth/session'),
  login: (credential: string) => request<User>('/api/auth/google', { method: 'POST', body: JSON.stringify({ credential }) }),
  websites: () => request<Website[]>('/api/websites'),
  createWebsite: (url: string, company_name: string, logo_url = '') => request<Website>('/api/websites', { method: 'POST', body: JSON.stringify({ url, company_name, logo_url }) }),
  updateWebsite: (id: number, data: { url?: string; company_name?: string; logo_url?: string }) => request<Website>(`/api/websites/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  resetWebsite: (id: number) => request<{ status: string }>(`/api/websites/${id}/reset`, { method: 'POST' }),
  deleteWebsite: (id: number) => request<{ status: string }>(`/api/websites/${id}`, { method: 'DELETE' }),
  detectCompanyName: (url: string) => request<{ company_name: string; logo_url: string }>(`/api/detect-company-name?url=${encodeURIComponent(url)}`, { method: 'POST' }),
  startScan: (website_id: number) => request<Scan>('/api/scans', { method: 'POST', body: JSON.stringify({ website_id }) }),
  getScan: (id: number) => request<Scan>(`/api/scans/${id}`),
  documents: (websiteId: number) => request<DocumentItem[]>(`/api/websites/${websiteId}/documents`),
  document: (id: number) => request<DocumentDetail>(`/api/documents/${id}`),
  models: () => request<ModelConfig[]>('/api/models'),
  refreshModels: () => request<ModelConfig[]>('/api/models/refresh', { method: 'POST' }),
  users: () => request<User[]>('/api/users'),
  updateUserRole: (id: number, role: string) => request<User>(`/api/users/${id}/role?role=${encodeURIComponent(role)}`, { method: 'PATCH' }),
  providerSettings: () => request<ProviderSettings>('/api/settings/providers'),
  saveProviderSettings: (data: Partial<ProviderSettings> & { openai_api_key?: string; openrouter_api_key?: string; google_client_secret?: string }) =>
    request<ProviderSettings>('/api/settings/providers', { method: 'PUT', body: JSON.stringify(data) }),
  mcp: () => request<{ tools: { name: string; description: string }[] }>('/mcp')
}
