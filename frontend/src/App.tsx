import { useEffect, useRef, useState } from 'react'

import type { DragEvent } from 'react'

import HomePage from './HomePage'

import SignInPage from './SignInPage'

import './App.css'

import {

  getCurrentUser,

  uploadDocument,

  createProcessingJob,

  getProcessingJob,
  savePIIReviewDecision,
  finalizeProcessingJob,
  type PIIReviewDecision,
  type UploadedDocument,

  type UserProfile,

  type ProcessingJob,

} from './api/client'

const TOKEN_STORAGE_KEY = 'securepdf_access_token'

const navigation = [

  { label: 'Overview', icon: '⌂' },

  { label: 'Documents', icon: '▤' },

  { label: 'Processing Jobs', icon: '▱' },

  { label: 'Redaction Settings', icon: '⚙' },

  { label: 'Audit Logs', icon: '☷' },

]

const descriptions: Record<string, string> = {

  Overview: 'Monitor your documents and keep sensitive information secure.',

  Documents: 'Manage the PDFs you upload and their processing status.',

  'Processing Jobs': 'Track document processing and review required actions.',

  'Redaction Settings': 'Configure how sensitive information should be handled.',

  'Audit Logs': 'Review recorded security and document-processing events.',

}

const ACTIVE_JOB_STATUSES = new Set([

  'PENDING',

  'PROCESSING',

  'RUNNING',

])

const COMPLETED_JOB_STATUSES = new Set([

  'COMPLETED',

  'SUCCESS',

  'SUCCEEDED',

])

const REVIEW_REQUIRED_STATUSES = new Set([

  'REVIEW_REQUIRED',

])

const FAILED_JOB_STATUSES = new Set([

  'FAILED',

  'CANCELLED',

  'CANCELED',

])

function App() {

  const [activePage, setActivePage] = useState('Home')

  const [selectedFile, setSelectedFile] = useState<File | null>(null)

  const [fileError, setFileError] = useState('')

  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false)

  const [isDraggingFile, setIsDraggingFile] = useState(false)

  const [accessToken, setAccessToken] = useState<string | null>(null)

  const [currentUser, setCurrentUser] = useState<UserProfile | null>(null)

  const [accountMenuOpen, setAccountMenuOpen] = useState(false)

  const [profileError, setProfileError] = useState('')

  const [isRestoringSession, setIsRestoringSession] = useState(true)

  const [isUploading, setIsUploading] = useState(false)

  const [uploadError, setUploadError] = useState('')

  const [uploadedDocument, setUploadedDocument] =

    useState<UploadedDocument | null>(null)

  const [processingJob, setProcessingJob] =

    useState<ProcessingJob | null>(null)

  const [jobError, setJobError] = useState('')

  const [isCreatingJob, setIsCreatingJob] = useState(false)

  const [isRefreshingJob, setIsRefreshingJob] = useState(false)
  const [reviewSavingIds, setReviewSavingIds] = useState<Set<string>>(
    () => new Set(),
  )
  const [reviewError, setReviewError] = useState('')
  const [reviewMessage, setReviewMessage] = useState('')
  const [isFinalizing, setIsFinalizing] = useState(false)
  const [finalizationError, setFinalizationError] = useState('')
  const [finalizationMessage, setFinalizationMessage] = useState('')
  

  const fileInputRef = useRef<HTMLInputElement>(null)

  const isAuthenticated = accessToken !== null

  const isOverview = activePage === 'Overview'

  const isBusy = isUploading || isCreatingJob

  // Restore the session after a page refresh.

  // The saved token is accepted only if the backend validates it.

  useEffect(() => {

    let cancelled = false

    async function restoreSession() {

      try {

        const savedToken = sessionStorage.getItem(TOKEN_STORAGE_KEY)

        if (!savedToken) {

          return

        }

        const profile = await getCurrentUser(savedToken)

        if (cancelled) return

        setAccessToken(savedToken)

        setCurrentUser(profile)

        setActivePage('Overview')

      } catch {

        if (cancelled) return

        sessionStorage.removeItem(TOKEN_STORAGE_KEY)

        setAccessToken(null)

        setCurrentUser(null)

        setActivePage('Home')

      } finally {

        if (!cancelled) {

          setIsRestoringSession(false)

        }

      }

    }

    void restoreSession()

    return () => {

      cancelled = true

    }

  }, [])

  // Store the token only after the backend confirms authentication.

  async function handleAuthenticated(token: string) {

    setProfileError('')

    try {

      const profile = await getCurrentUser(token)

      sessionStorage.setItem(TOKEN_STORAGE_KEY, token)

      setAccessToken(token)

      setCurrentUser(profile)

      setActivePage('Overview')

      setAccountMenuOpen(false)

    } catch {

      sessionStorage.removeItem(TOKEN_STORAGE_KEY)

      setAccessToken(null)

      setCurrentUser(null)

      setProfileError(

        'We could not load your account. Please sign in again.',

      )

      setActivePage('Sign In')

    }

  }

  function signOut() {

    sessionStorage.removeItem(TOKEN_STORAGE_KEY)

    setAccessToken(null)

    setCurrentUser(null)

    setAccountMenuOpen(false)

    setIsMobileMenuOpen(false)

    setSelectedFile(null)

    setFileError('')

    setUploadError('')

    setUploadedDocument(null)

    setProcessingJob(null)

    setJobError('')

    setProfileError('')

    setIsRefreshingJob(false)

    if (fileInputRef.current) {

      fileInputRef.current.value = ''

    }

    setActivePage('Home')

  }

  function returnToHome() {

    setActivePage('Home')

    setIsMobileMenuOpen(false)

    setAccountMenuOpen(false)

  }

  function returnToOverview() {

    setActivePage(isAuthenticated ? 'Overview' : 'Sign In')

    setIsMobileMenuOpen(false)

  }

  function navigateToPage(page: string) {

    if (!isAuthenticated) {

      setActivePage('Sign In')

    } else {

      setActivePage(page)

    }

    setIsMobileMenuOpen(false)

    setAccountMenuOpen(false)

  }

  function selectFile(file?: File) {

    if (isBusy) return

    setFileError('')

    setUploadError('')

    setUploadedDocument(null)

    setProcessingJob(null)

    setJobError('')

    setIsRefreshingJob(false)

    setSelectedFile(null)

    if (!file) return

    if (

      file.type !== 'application/pdf' &&

      !file.name.toLowerCase().endsWith('.pdf')

    ) {

      setFileError('Please select a PDF file.')

      return

    }

    if (file.size > 25 * 1024 * 1024) {

      setFileError('The file exceeds the current 25 MB upload limit.')

      return

    }

    if (file.size === 0) {

      setFileError('The selected file is empty.')

      return

    }

    setSelectedFile(file)

  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {

    event.preventDefault()

    setIsDraggingFile(false)

    if (isBusy) return

    selectFile(event.dataTransfer.files[0])

  }

  // Create a processing job for an uploaded document.

  async function createJobForDocument(

    documentId: string,

    token: string,

  ) {

    setIsCreatingJob(true)

    setJobError('')

    setProcessingJob(null)

    try {

      const job = await createProcessingJob(documentId, token)

      setProcessingJob(job)

    } catch (error) {

      setJobError(

        error instanceof Error

          ? error.message

          : 'The PDF uploaded, but its processing job could not be created.',

      )

    } finally {

      setIsCreatingJob(false)

    }

  }

  async function handleUpload() {

    if (!selectedFile || !accessToken || isBusy) return

    const fileToUpload = selectedFile

    const token = accessToken

    setIsUploading(true)

    setUploadError('')

    setJobError('')

    setUploadedDocument(null)

    setProcessingJob(null)

    try {

      const document = await uploadDocument(fileToUpload, token)

      setUploadedDocument(document)

      setSelectedFile(null)

      if (fileInputRef.current) {

        fileInputRef.current.value = ''

      }

      await createJobForDocument(document.document_id, token)

    } catch (error) {

      setUploadError(

        error instanceof Error

          ? error.message

          : 'Upload failed. Please try again.',

      )

    } finally {

      setIsUploading(false)

    }

  }

  async function handleRetryJob() {

    if (!uploadedDocument || !accessToken || isBusy) return

    await createJobForDocument(

      uploadedDocument.document_id,

      accessToken,

    )

  }

  async function handleReviewDecision(
    candidateId: string,
    decision: PIIReviewDecision,
  ) {
    if (!processingJob || !accessToken || reviewSavingIds.has(candidateId)) {
      return
    }

    setReviewError('')
    setReviewMessage('')
    setFinalizationError('')
    setFinalizationMessage('')
    setReviewSavingIds((current) => new Set(current).add(candidateId))

    try {
      await savePIIReviewDecision(
        processingJob.document_id,
        candidateId,
        decision,
        accessToken,
      )

      setProcessingJob((current) => {
        if (!current) return current

        return {
          ...current,
          pii_entities: current.pii_entities.map((candidate) =>
            candidate.id === candidateId
              ? {
                  ...candidate,
                  review_decision: decision,
                  review_status:
                    decision === 'REDACT'
                      ? 'approved_for_redaction'
                      : 'kept',
                }
              : candidate,
          ),
        }
      })
      setReviewMessage('Review decision saved successfully.')
    } catch (error) {
      setReviewError(
        error instanceof Error
          ? error.message
          : 'Unable to save the review decision.',
      )
    } finally {
      setReviewSavingIds((current) => {
        const next = new Set(current)
        next.delete(candidateId)
        return next
      })
    }
  }

  async function handleFinalizeRedaction() {
    if (!processingJob || !accessToken || isFinalizing) return

    const candidates = processingJob.pii_entities ?? []
    const allReviewed =
      candidates.length > 0 &&
      candidates.every(
        (candidate) =>
          candidate.review_decision === 'REDACT' ||
          candidate.review_decision === 'KEEP',
      )

    if (!allReviewed) {
      setFinalizationError(
        'Save a REDACT or KEEP decision for every candidate before finalizing.',
      )
      return
    }

    setIsFinalizing(true)
    setFinalizationError('')
    setFinalizationMessage('')
    setReviewError('')

    try {
      const result = await finalizeProcessingJob(
        processingJob.document_id,
        processingJob.job_id,
        accessToken,
      )

      const latestJob = await getProcessingJob(
        processingJob.job_id,
        accessToken,
      )
      setProcessingJob(latestJob)
      setFinalizationMessage(
        `Redaction completed. ${result.redacted_candidates} candidate(s) redacted and ${result.kept_candidates} candidate(s) kept.`,
      )
    } catch (error) {
      setFinalizationError(
        error instanceof Error
          ? error.message
          : 'Unable to finalize the PDF.',
      )
    } finally {
      setIsFinalizing(false)
    }
  }

  // Poll active jobs. RUNNING is included because the backend may

  // use that status instead of PROCESSING.

  useEffect(() => {

    if (!processingJob || !accessToken) return

    const jobId = processingJob.job_id

    const initialStatus = processingJob.status.toUpperCase()

    if (!ACTIVE_JOB_STATUSES.has(initialStatus)) return

    let cancelled = false

    let requestRunning = false

    async function refreshJob() {

      if (cancelled || requestRunning) return

      requestRunning = true

      if (!cancelled) {

        setIsRefreshingJob(true)

      }

      try {

        const latestJob = await getProcessingJob(jobId, accessToken!)

        if (!cancelled) {

          setProcessingJob(latestJob)

          setJobError('')

        }

      } catch (error) {

        if (!cancelled) {

          setJobError(

            error instanceof Error

              ? `Unable to refresh job status: ${error.message}`

              : 'Unable to refresh job status.',

          )

        }

      } finally {

        requestRunning = false

        if (!cancelled) {

          setIsRefreshingJob(false)

        }

      }

    }

    // Fetch immediately, then continue polling every three seconds.

    void refreshJob()

    const intervalId = window.setInterval(() => {

      void refreshJob()

    }, 3000)

    return () => {

      cancelled = true

      window.clearInterval(intervalId)

    }

  }, [processingJob?.job_id, processingJob?.status, accessToken])

  // Avoid briefly rendering the public home page while restoring a session.

  if (isRestoringSession) {

    return (

      <div className="app-shell">

        <main className="main-area">

          <div className="page-content">

            <p className="feedback" role="status">

              Restoring your SecurePDF session...

            </p>

          </div>

        </main>

      </div>

    )

  }

  if (activePage === 'Home') {

    return (

      <HomePage

        onGetStarted={() =>

          setActivePage(isAuthenticated ? 'Overview' : 'Sign In')

        }

        onSignIn={() => setActivePage('Sign In')}

      />

    )

  }

  if (activePage === 'Sign In') {

    return (

      <SignInPage

        onAuthenticated={handleAuthenticated}

        onBackToHome={returnToHome}

      />

    )

  }

  const jobStatus = processingJob?.status.toUpperCase() ?? ''

  const jobCompleted = COMPLETED_JOB_STATUSES.has(jobStatus)

  const jobRequiresReview = REVIEW_REQUIRED_STATUSES.has(jobStatus)

  const jobFailed = FAILED_JOB_STATUSES.has(jobStatus)

  const jobActive = ACTIVE_JOB_STATUSES.has(jobStatus)

  return (

    <div className="app-shell">

      {isMobileMenuOpen && (

        <button

          className="sidebar-backdrop"

          type="button"

          aria-label="Close navigation menu"

          onClick={() => setIsMobileMenuOpen(false)}

        />

      )}

      <aside

        id="workspace-sidebar"

        className={`sidebar ${isMobileMenuOpen ? 'sidebar-open' : ''}`}

      >

        <a

          className="brand"

          href="#home"

          aria-label="Return to SecurePDF home page"

          onClick={(event) => {

            event.preventDefault()

            returnToHome()

          }}

        >

          <span className="brand-mark">S</span>

          <span>SecurePDF</span>

        </a>

        <div className="nav-label">GENERAL</div>

        <nav className="navigation" aria-label="General navigation">

          <button

            className="nav-item"

            onClick={returnToHome}

            type="button"

          >

            <span className="nav-icon" aria-hidden="true">⌂</span>

            <span>Home page</span>

          </button>

        </nav>

        <div className="nav-label">WORKSPACE</div>

        <nav className="navigation" aria-label="Workspace navigation">

          {navigation.slice(0, 4).map((item) => (

            <button

              className={`nav-item ${activePage === item.label ? 'active' : ''}`}

              key={item.label}

              onClick={() => navigateToPage(item.label)}

              type="button"

              aria-current={activePage === item.label ? 'page' : undefined}

            >

              <span className="nav-icon" aria-hidden="true">{item.icon}</span>

              <span>{item.label}</span>

            </button>

          ))}

        </nav>

        <div className="nav-label system-label">SECURITY</div>

        <nav className="navigation" aria-label="Security navigation">

          {navigation.slice(4).map((item) => (

            <button

              className={`nav-item ${activePage === item.label ? 'active' : ''}`}

              key={item.label}

              onClick={() => navigateToPage(item.label)}

              type="button"

              aria-current={activePage === item.label ? 'page' : undefined}

            >

              <span className="nav-icon" aria-hidden="true">{item.icon}</span>

              <span>{item.label}</span>

            </button>

          ))}

        </nav>

        <div className="sidebar-footer">

          <span className="status-dot" />

          <span>Secure workspace</span>

        </div>

      </aside>

      <main className="main-area">

        <header className="topbar">

          <button

            className="mobile-menu-button"

            type="button"

            aria-label={isMobileMenuOpen ? 'Close menu' : 'Open menu'}

            aria-expanded={isMobileMenuOpen}

            aria-controls="workspace-sidebar"

            onClick={() => setIsMobileMenuOpen((open) => !open)}

          >

            <span aria-hidden="true">{isMobileMenuOpen ? '✕' : '☰'}</span>

          </button>

          <div className="breadcrumb">

            SecurePDF <span>/</span> {activePage}

          </div>

          <div className="topbar-right">

            <span className="environment-label">

              <span className="status-dot" />

              {isAuthenticated

                ? 'Authenticated workspace'

                : 'Local workspace'}

            </span>

            {isAuthenticated && currentUser && (

              <div className="account-container">

                <button

                  className="account-trigger"

                  type="button"

                  aria-label="Open account menu"

                  aria-expanded={accountMenuOpen}

                  onClick={() => setAccountMenuOpen((open) => !open)}

                >

                  <span className="account-avatar" aria-hidden="true">

                    {currentUser.name.trim().charAt(0).toUpperCase() || 'U'}

                  </span>

                  <span className="account-trigger-name">

                    {currentUser.name}

                  </span>

                  <span aria-hidden="true">

                    {accountMenuOpen ? '▴' : '▾'}

                  </span>

                </button>

                {accountMenuOpen && (

                  <>

                    <button

                      className="account-dismiss"

                      type="button"

                      aria-label="Close account menu"

                      onClick={() => setAccountMenuOpen(false)}

                    />

                    <div className="account-menu">

                      <div className="account-profile">

                        <span className="account-avatar account-avatar-large">

                          {currentUser.name.trim().charAt(0).toUpperCase() || 'U'}

                        </span>

                        <div className="account-profile-details">

                          <strong>{currentUser.name}</strong>

                          <span>{currentUser.email}</span>

                        </div>

                      </div>

                      <div className="account-menu-divider" />

                      <button

                        className="account-menu-item"

                        type="button"

                        onClick={() => {

                          setAccountMenuOpen(false)

                          navigateToPage('Account details')

                        }}

                      >

                        <span aria-hidden="true">◉</span>

                        Account details

                      </button>

                      <button

                        className="account-menu-item account-signout"

                        type="button"

                        onClick={signOut}

                      >

                        <span aria-hidden="true">↪</span>

                        Sign out

                      </button>

                    </div>

                  </>

                )}

              </div>

            )}

            {!isAuthenticated && (

              <button

                className="secondary-button"

                type="button"

                onClick={() => setActivePage('Sign In')}

              >

                Sign in

              </button>

            )}

          </div>

        </header>

        <div className="page-content">

          {profileError && (

            <p className="feedback error" role="alert">{profileError}</p>

          )}

          <section className="welcome-panel">

            <div className="welcome-copy">

              <span className="eyebrow">DOCUMENT SECURITY WORKSPACE</span>

              <h1>

                {isOverview ? 'Your documents, protected.' : activePage}

              </h1>

              <p>

                {descriptions[activePage] ??

                  'Explore your SecurePDF workspace.'}

              </p>

              {isOverview && (

                <button

                  className="primary-button"

                  onClick={() => {

                    const uploadPanel = document.getElementById('upload-panel')

                    if (uploadPanel) {

                      uploadPanel.scrollIntoView({

                        behavior: 'smooth',

                        block: 'center',

                      })

                    } else {

                      fileInputRef.current?.click()

                    }

                  }}

                  type="button"

                >

                  <span aria-hidden="true">↑</span> Upload a PDF

                </button>

              )}

            </div>

            <div className="welcome-art" aria-hidden="true">

              <div className="document-illustration">

                <span className="document-fold" />

                <span className="document-line long" />

                <span className="document-line" />

                <span className="document-line short" />

                <span className="pdf-label">PDF</span>

              </div>

              <div className="shield-illustration">✓</div>

              <span className="art-caption">Privacy by design</span>

            </div>

          </section>

          {isOverview ? (

            <>

              <section className="stats-grid" aria-label="Document statistics">

                <StatCard icon="▤" label="Total documents" value="—" tone="blue" />

                <StatCard icon="✓" label="Completed" value="—" tone="green" />

                <StatCard icon="◷" label="In progress" value="—" tone="amber" />

                <StatCard icon="!" label="Failed" value="—" tone="red" />

              </section>

              <section className="content-grid">

                <div className="panel upload-panel" id="upload-panel">

                  <div className="panel-heading">

                    <div>

                      <h2>Upload a document</h2>

                      <p>Select a PDF to prepare it for processing.</p>

                    </div>

                    <span className="format-badge">PDF · Max 25 MB</span>

                  </div>

                  <div

                    className={`dropzone ${isDraggingFile ? 'drag-active' : ''}`}

                    onDragEnter={(event) => {

                      event.preventDefault()

                      if (!isBusy) setIsDraggingFile(true)

                    }}

                    onDragOver={(event) => {

                      event.preventDefault()

                      event.dataTransfer.dropEffect = 'copy'

                      if (!isBusy) setIsDraggingFile(true)

                    }}

                    onDragLeave={(event) => {

                      event.preventDefault()

                      if (

                        !event.currentTarget.contains(

                          event.relatedTarget as Node | null,

                        )

                      ) {

                        setIsDraggingFile(false)

                      }

                    }}

                    onDrop={handleDrop}

                  >

                    <div className="upload-icon" aria-hidden="true">↑</div>

                    <h3>Drop your PDF here</h3>

                    <p>or browse files on your device</p>

                    <button

                      className="secondary-button"

                      onClick={() => fileInputRef.current?.click()}

                      type="button"

                      disabled={isBusy}

                    >

                      Choose PDF

                    </button>

                    <input

                      ref={fileInputRef}

                      type="file"

                      accept=".pdf,application/pdf"

                      className="visually-hidden"

                      aria-label="Choose a PDF file"

                      disabled={isBusy}

                      onChange={(event) => selectFile(event.target.files?.[0])}

                    />

                    <span className="upload-hint">

                      Your file stays on your device until you upload it.

                    </span>

                  </div>

                  {fileError && (

                    <p className="feedback error" role="alert">{fileError}</p>

                  )}

                  {selectedFile && (

                    <div className="selected-file" role="status">

                      <span className="file-symbol">PDF</span>

                      <div className="selected-file-info">

                        <strong>{selectedFile.name}</strong>

                        <span>

                          {(selectedFile.size / (1024 * 1024)).toFixed(2)} MB

                          {' '}· Ready to upload

                        </span>

                      </div>

                      <button

                        className="remove-file"

                        type="button"

                        aria-label="Remove selected file"

                        disabled={isBusy}

                        onClick={() => {

                          setSelectedFile(null)

                          setFileError('')

                          setUploadError('')

                          setJobError('')

                          setProcessingJob(null)

                          if (fileInputRef.current) {

                            fileInputRef.current.value = ''

                          }

                        }}

                      >

                        Remove

                      </button>

                    </div>

                  )}

                  <button

                    className="primary-button"

                    type="button"

                    onClick={handleUpload}

                    disabled={!selectedFile || isBusy || !accessToken}

                  >

                    {isUploading

                      ? 'Uploading PDF...'

                      : isCreatingJob

                        ? 'Creating processing job...'

                        : 'Upload document'}

                  </button>

                  {isUploading && (

                    <p className="feedback" role="status">

                      Uploading your PDF to SecurePDF...

                    </p>

                  )}

                  {isCreatingJob && (

                    <p className="feedback" role="status">

                      PDF uploaded. Creating your processing job...

                    </p>

                  )}

                  {uploadError && (

                    <p className="feedback error" role="alert">

                      {uploadError}

                    </p>

                  )}

                  {uploadedDocument && (

                    <div className="upload-success">

                      <h3>PDF uploaded successfully</h3>

                      <p>

                        <strong>Filename:</strong> {uploadedDocument.filename}

                      </p>

                      <p>

                        <strong>File size:</strong>{' '}

                        {(uploadedDocument.size_bytes / 1024).toFixed(1)} KB

                      </p>

                      <p>

                        <strong>Pages:</strong> {uploadedDocument.page_count}

                      </p>

                      <p>

                        <strong>Document type:</strong>{' '}

                        {uploadedDocument.document_type}

                      </p>

                      <p>

                        <strong>Upload status:</strong> {uploadedDocument.status}

                      </p>

                    </div>

                  )}

                  {jobError && (

                    <div className="feedback error" role="alert">

                      <p>

                        {processingJob

                          ? 'The processing job could not be refreshed.'

                          : 'The PDF uploaded successfully, but job creation failed.'}

                        {' '}{jobError}

                      </p>

                      {!processingJob && (

                        <button

                          className="secondary-button"

                          type="button"

                          disabled={isBusy || !uploadedDocument || !accessToken}

                          onClick={handleRetryJob}

                        >

                          Retry job creation

                        </button>

                      )}

                    </div>

                  )}

                  {processingJob && (

                    <div className="upload-success">

                      <h3>Processing job</h3>

                      <p>

                        <strong>Status:</strong> {processingJob.status}

                      </p>

                      <div className="job-progress">

                        <div className="job-progress-label">

                          <span>Progress</span>

                          <strong>

                            {Math.min(100, Math.max(0, processingJob.progress))}%

                          </strong>

                        </div>

                        <progress

                          value={Math.min(

                            100,

                            Math.max(0, processingJob.progress),

                          )}

                          max={100}

                          aria-label="Processing progress"

                        />

                      </div>

                      {jobActive && (

                        <p>

                          {jobStatus === 'PENDING'

                            ? 'Waiting for a worker to process your document...'

                            : 'Your document is being processed.'}

                        </p>

                      )}

                      {jobCompleted && (

                        <p>Processing completed successfully.</p>

                      )}

                      {jobRequiresReview && (

                        <p role="status">

                          Automated processing finished. Your document requires

                          review before the workflow can proceed. No redacted

                          output is confirmed by this status alone.

                        </p>

                      )}

                      {jobRequiresReview && processingJob.pii_entities && (
                        <section className="pii-review-section" aria-labelledby="pii-review-heading">
                          <div className="panel-heading compact">
                            <div>
                              <h2 id="pii-review-heading">PII Detection Results</h2>
                              <p>Review each candidate and save a REDACT or KEEP decision.</p>
                            </div>
                            <span className="format-badge">
                              {processingJob.pii_entities.length} candidate(s)
                            </span>
                          </div>

                          {processingJob.pii_entities.length === 0 ? (
                            <p className="feedback">
                              No PII candidates were returned for this job.
                            </p>
                          ) : (
                            <div className="pii-review-list">
                              {processingJob.pii_entities.map((candidate) => {
                                const saving = reviewSavingIds.has(candidate.id)
                                const decision = candidate.review_decision
                                const saved =
                                  decision === 'REDACT' || decision === 'KEEP'

                                return (
                                  <article className="panel pii-candidate-card" key={candidate.id}>
                                    <div className="panel-heading compact">
                                      <div>
                                        <span className="format-badge">
                                          {candidate.entity_type}
                                        </span>
                                        <h3>{candidate.text}</h3>
                                      </div>
                                      <span className="format-badge">
                                        {saved ? `SAVED: ${decision}` : 'REVIEW REQUIRED'}
                                      </span>
                                    </div>

                                    <div className="pii-candidate-metadata">
                                      <span>
                                        <strong>Confidence:</strong>{' '}
                                        {candidate.confidence == null
                                          ? 'Unavailable'
                                          : `${(candidate.confidence * 100).toFixed(2)}%`}
                                      </span>
                                      <span>
                                        <strong>Page:</strong> {candidate.page_number}
                                      </span>
                                      <span>
                                        <strong>Source:</strong> {candidate.source}
                                      </span>
                                      <span>
                                        <strong>Bounding boxes:</strong>{' '}
                                        {candidate.bounding_boxes?.length ?? 0}
                                      </span>
                                    </div>

                                    <div className="pii-review-actions">
                                      <button
                                        className={decision === 'REDACT' ? 'primary-button' : 'secondary-button'}
                                        type="button"
                                        disabled={saving || isFinalizing}
                                        aria-pressed={decision === 'REDACT'}
                                        onClick={() => void handleReviewDecision(candidate.id, 'REDACT')}
                                      >
                                        {saving ? 'Saving...' : 'REDACT'}
                                      </button>
                                      <button
                                        className={decision === 'KEEP' ? 'primary-button' : 'secondary-button'}
                                        type="button"
                                        disabled={saving || isFinalizing}
                                        aria-pressed={decision === 'KEEP'}
                                        onClick={() => void handleReviewDecision(candidate.id, 'KEEP')}
                                      >
                                        {saving ? 'Saving...' : 'KEEP'}
                                      </button>
                                    </div>
                                  </article>
                                )
                              })}
                            </div>
                          )}

                          {reviewError && (
                            <p className="feedback error" role="alert">{reviewError}</p>
                          )}
                          {reviewMessage && (
                            <p className="feedback" role="status">{reviewMessage}</p>
                          )}
                          {finalizationError && (
                            <p className="feedback error" role="alert">{finalizationError}</p>
                          )}
                          {finalizationMessage && (
                            <p className="feedback" role="status">{finalizationMessage}</p>
                          )}

                          <button
                            className="primary-button"
                            type="button"
                            disabled={
                              isFinalizing ||
                              reviewSavingIds.size > 0 ||
                              processingJob.pii_entities.length === 0 ||
                              !processingJob.pii_entities.every(
                                (candidate) =>
                                  candidate.review_decision === 'REDACT' ||
                                  candidate.review_decision === 'KEEP',
                              )
                            }
                            onClick={() => void handleFinalizeRedaction()}
                          >
                            {isFinalizing ? 'Finalizing PDF...' : 'Finalize redaction'}
                          </button>
                          <p className="prototype-note">
                            Finalization uses saved backend decisions. Review the resulting PDF before sharing it.
                          </p>
                        </section>
                      )}

                      {jobFailed && (

                        <p className="feedback error">

                          {processingJob.error_message ||

                            'Processing failed. Please review the job details.'}

                        </p>

                      )}

                      {isRefreshingJob && (

                        <p className="feedback" aria-live="polite">

                          Refreshing job status...

                        </p>

                      )}

                      {jobError && (

                        <p className="feedback error" role="alert">

                          {jobError}

                        </p>

                      )}

                    </div>

                  )}

                  <p className="prototype-note">

                    Job status is retrieved from the backend. PII detection

                    and redaction completion must be verified separately.

                  </p>

                </div>

                <div className="right-column">

                  <div className="panel list-panel">

                    <div className="panel-heading compact">

                      <div>

                        <h2>Recent documents</h2>

                        <p>Your document history will appear here.</p>

                      </div>

                    </div>

                    <EmptyState

                      icon="▤"

                      title="Document list not connected yet"

                      description="Your uploaded PDFs are saved by the backend. The document history view will be connected later."

                    />

                  </div>

                  <div className="panel list-panel">

                    <div className="panel-heading compact">

                      <div>

                        <h2>Processing jobs</h2>

                        <p>Monitor processing activity.</p>

                      </div>

                    </div>

                    {processingJob ? (

                      <EmptyState

                        icon="▱"

                        title="Processing job available"

                        description={`Current status: ${processingJob.status}`}

                      />

                    ) : (

                      <EmptyState

                        icon="▱"

                        title="No processing jobs displayed"

                        description="Create a job by uploading a PDF. The full job history will be connected later."

                      />

                    )}

                  </div>

                </div>

              </section>

            </>

          ) : (

            <section className="panel placeholder-panel">

              <div className="placeholder-icon" aria-hidden="true">◇</div>

              <h2>{activePage}</h2>

              <p>{`${activePage} will be implemented in a later step.`}</p>

              <button

                className="secondary-button"

                onClick={returnToOverview}

                type="button"

              >

                Return to overview

              </button>

            </section>

          )}

          <footer className="page-footer">

            <span>SecurePDF</span>

            <span>

              Protecting sensitive information, one document at a time.

            </span>

          </footer>

        </div>

      </main>

    </div>

  )

}

function StatCard({

  icon,

  label,

  value,

  tone,

}: {

  icon: string

  label: string

  value: string

  tone: string

}) {

  return (

    <div className="stat-card">

      <span className={`stat-icon ${tone}`} aria-hidden="true">{icon}</span>

      <div>

        <strong>{value}</strong>

        <span>{label}</span>

      </div>

    </div>

  )

}

function EmptyState({

  icon,

  title,

  description,

}: {

  icon: string

  title: string

  description: string

}) {

  return (

    <div className="empty-state">

      <span className="empty-icon" aria-hidden="true">{icon}</span>

      <strong>{title}</strong>

      <span>{description}</span>

    </div>

  )

}

export default App
