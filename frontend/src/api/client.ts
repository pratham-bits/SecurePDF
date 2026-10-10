const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'
).replace(/\/+$/, '')

// ─────────────────────────────────────────────
// Authentication types
// ─────────────────────────────────────────────

export type LoginRequest = {
  email: string
  password: string
}

export type TokenResponse = {
  access_token: string
  token_type: string
}

export type UserProfile = {
  id: string
  name: string
  email: string
}

// ─────────────────────────────────────────────
// Document types
// ─────────────────────────────────────────────

export type UploadedDocument = {
  document_id: string
  filename: string
  size_bytes: number
  page_count: number
  document_type: string
  status: string
  sha256_hash: string
}

// ─────────────────────────────────────────────
// PII candidate types
// ─────────────────────────────────────────────

export type PIIReviewDecision = 'REDACT' | 'KEEP'

export type PIIReviewStatus =
  | 'detected'
  | 'review_required'
  | 'approved_for_redaction'
  | 'kept'
  | string

export type BoundingBox = {
  x0: number
  y0: number
  x1: number
  y1: number
}

export type PIICandidate = {
  id: string
  entity_type: string
  text: string
  confidence: number | null
  page_number: number
  bounding_boxes: BoundingBox[]
  source: string
  review_status: PIIReviewStatus
  review_decision?: PIIReviewDecision | null
}

// ─────────────────────────────────────────────
// Processing job types
// ─────────────────────────────────────────────

export type ProcessingJob = {
  job_id: string
  document_id: string
  job_type: string
  status: string
  progress: number
  attempt_count: number
  error_code: string | null
  error_message: string | null
  started_at: string | null
  completed_at: string | null
  created_at: string
  pii_entities: PIICandidate[]
}

// ─────────────────────────────────────────────
// Error handling
// ─────────────────────────────────────────────

async function readError(response: Response): Promise<string> {
  try {
    const data: unknown = await response.json()

    if (
      typeof data === 'object' &&
      data !== null &&
      'detail' in data
    ) {
      const detail = (data as { detail: unknown }).detail

      if (typeof detail === 'string') {
        return detail
      }

      if (Array.isArray(detail)) {
        return detail
          .map((item) => {
            if (
              typeof item === 'object' &&
              item !== null &&
              'msg' in item
            ) {
              return String(item.msg)
            }

            return String(item)
          })
          .join('; ')
      }
    }
  } catch {
    // The server may return an empty or non-JSON error response.
  }

  return `Request failed (${response.status} ${response.statusText})`
}

// ─────────────────────────────────────────────
// Generic API request helper
// ─────────────────────────────────────────────

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, options)

  if (!response.ok) {
    throw new Error(await readError(response))
  }

  return response.json() as Promise<T>
}

// ─────────────────────────────────────────────
// Authentication API
// ─────────────────────────────────────────────

export async function login(
  credentials: LoginRequest,
): Promise<TokenResponse> {
  return request<TokenResponse>('/api/v1/auth/login', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(credentials),
  })
}

export async function getCurrentUser(
  accessToken: string,
): Promise<UserProfile> {
  return request<UserProfile>('/api/v1/auth/me', {
    method: 'GET',
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  })
}

// ─────────────────────────────────────────────
// Document upload API
// ─────────────────────────────────────────────

export async function uploadDocument(
  file: File,
  accessToken: string,
): Promise<UploadedDocument> {
  const formData = new FormData()
  formData.append('file', file)

  return request<UploadedDocument>('/api/v1/documents/upload', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
    body: formData,
  })
}

// ─────────────────────────────────────────────
// Processing job creation API
// ─────────────────────────────────────────────

export async function createProcessingJob(
  documentId: string,
  accessToken: string,
): Promise<ProcessingJob> {
  return request<ProcessingJob>(
    `/api/v1/documents/${encodeURIComponent(documentId)}/jobs`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${accessToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        job_type: 'PDF_PROCESSING',
      }),
    },
  )
}

// ─────────────────────────────────────────────
// Processing job status API
// ─────────────────────────────────────────────

export async function getProcessingJob(
  jobId: string,
  accessToken: string,
): Promise<ProcessingJob> {
  return request<ProcessingJob>(
    `/api/v1/jobs/${encodeURIComponent(jobId)}`,
    {
      method: 'GET',
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
    },
  )
}

// ─────────────────────────────────────────────
// PII review decision API
// ─────────────────────────────────────────────

export async function savePIIReviewDecision(
  documentId: string,
  candidateId: string,
  decision: PIIReviewDecision,
  accessToken: string,
): Promise<unknown> {
  return request<unknown>(
    `/api/v1/documents/${encodeURIComponent(documentId)}/pii-entities/${encodeURIComponent(candidateId)}/decision`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${accessToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ decision }),
    },
  )
}


export type FinalizeProcessingJobResponse = {
  job_id: string
  document_id: string
  status: string
  progress: number
  redacted_storage_key: string
  candidates_processed: number
  redacted_candidates: number
  kept_candidates: number
}

export async function finalizeProcessingJob(
  documentId: string,
  jobId: string,
  accessToken: string,
): Promise<FinalizeProcessingJobResponse> {
  return request<FinalizeProcessingJobResponse>(
    `/api/v1/documents/${encodeURIComponent(documentId)}` +
      `/jobs/${encodeURIComponent(jobId)}/finalize`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
    },
  )
}