
type HomePageProps = {
  onGetStarted: () => void
  onSignIn: () => void
}

function HomePage({ onGetStarted, onSignIn }: HomePageProps) {
  return (
    <div className="home-page">
      <header className="home-header">
        <a className="home-brand" href="#home" aria-label="SecurePDF home">
          <span className="home-brand-mark">S</span>
          <span>SecurePDF</span>
        </a>

        <nav className="home-nav" aria-label="Main navigation">
          <a href="#features">Features</a>
          <a href="#how-it-works">How it works</a>
          <a href="#security">Security</a>
        </nav>

        <div className="home-header-actions">
          <button className="home-signin" onClick={onSignIn}>
            Sign in
          </button>
          <button className="home-button home-button-small" onClick={onGetStarted}>
            Get started
            <span aria-hidden="true">→</span>
          </button>
        </div>
      </header>

      <main id="home">
        <section className="home-hero">
          <div className="home-hero-copy">
            <div className="home-eyebrow">
              <span className="home-eyebrow-dot" />
              DOCUMENT PRIVACY, MADE SIMPLER
            </div>

            <h1>
              Your documents.
              <br />
              Your privacy.
              <br />
              <span>Our priority.</span>
            </h1>

            <p className="home-hero-description">
              Identify sensitive information in your PDFs and prepare
              documents for safer sharing with SecurePDF's
              automated redaction workflow.
            </p>

            <div className="home-hero-actions">
              <button className="home-button" onClick={onGetStarted}>
                Protect a document
                <span aria-hidden="true">→</span>
              </button>
              <a className="home-secondary-link" href="#how-it-works">
                See how it works
              </a>
            </div>

            <div className="home-trust-note">
              <span aria-hidden="true">✓</span>
              Designed to help protect sensitive information
            </div>
          </div>

          <div className="home-visual" aria-label="Illustration of PDF privacy protection">
            <div className="home-orbit home-orbit-one" />
            <div className="home-orbit home-orbit-two" />

            <div className="home-document">
              <div className="home-document-top">
                <span className="home-pdf-icon">PDF</span>
                <span className="home-document-tag">Document preview</span>
              </div>
              <div className="home-document-title">Personal information</div>
              <div className="home-document-line line-wide" />
              <div className="home-document-line line-medium" />
              <div className="home-document-line line-short" />

              <div className="home-redaction-row">
                <span className="home-redaction-label">Name</span>
                <span className="home-redaction-block" />
              </div>
              <div className="home-redaction-row">
                <span className="home-redaction-label">Email</span>
                <span className="home-redaction-block redaction-long" />
              </div>
              <div className="home-redaction-row">
                <span className="home-redaction-label">Phone</span>
                <span className="home-redaction-block redaction-medium" />
              </div>
              <div className="home-document-footer">
                <span className="home-mini-dot" />
                Privacy-focused processing
              </div>
            </div>

            <div className="home-shield">
              <span aria-hidden="true">✓</span>
            </div>

            <div className="home-floating-card">
              <span className="home-floating-icon">✦</span>
              <div>
                <strong>PII detection</strong>
                <span>Find sensitive details</span>
              </div>
            </div>
          </div>
        </section>

        <section className="home-benefits" aria-label="SecurePDF benefits">
          <div>
            <span className="home-benefit-icon">◎</span>
            <div>
              <strong>Identify sensitive data</strong>
              <p>Find potential PII in supported PDFs.</p>
            </div>
          </div>
          <div>
            <span className="home-benefit-icon">▰</span>
            <div>
              <strong>Redact with purpose</strong>
              <p>Prepare sensitive content for removal.</p>
            </div>
          </div>
          <div>
            <span className="home-benefit-icon">✓</span>
            <div>
              <strong>Verify the result</strong>
              <p>Check that the redaction workflow succeeds.</p>
            </div>
          </div>
        </section>

        <section className="home-section" id="features">
          <div className="home-section-heading">
            <span className="home-section-label">BUILT FOR DOCUMENT PRIVACY</span>
            <h2>More confidence in every document.</h2>
            <p>
              A practical workflow for finding and protecting personal
              information in digital and scanned PDF files.
            </p>
          </div>

          <div className="home-feature-grid">
            <article className="home-feature-card">
              <span className="home-feature-icon">⌕</span>
              <h3>Intelligent PII detection</h3>
              <p>
                Combine recognizable data patterns with contextual
                detection to identify potential sensitive information.
              </p>
            </article>

            <article className="home-feature-card">
              <span className="home-feature-icon">▤</span>
              <h3>Digital and scanned PDFs</h3>
              <p>
                Extract existing PDF text and use OCR where scanned
                pages require text recognition.
              </p>
            </article>

            <article className="home-feature-card">
              <span className="home-feature-icon">✓</span>
              <h3>Redaction and verification</h3>
              <p>
                Apply redactions and verify processing results before
                treating an output as ready to use.
              </p>
            </article>
          </div>
        </section>

        <section className="home-process-section" id="how-it-works">
          <div className="home-section-heading">
            <span className="home-section-label">HOW IT WORKS</span>
            <h2>Four steps toward safer sharing.</h2>
            <p>
              A clear workflow that helps you understand what happens
              to your document at each stage.
            </p>
          </div>

          <div className="home-steps">
            <article className="home-step">
              <span className="home-step-number">01</span>
              <h3>Upload</h3>
              <p>Select the PDF you want to process.</p>
            </article>
            <article className="home-step">
              <span className="home-step-number">02</span>
              <h3>Detect</h3>
              <p>Extract text and identify potential PII.</p>
            </article>
            <article className="home-step">
              <span className="home-step-number">03</span>
              <h3>Redact</h3>
              <p>Review flagged information and apply redactions.</p>
            </article>
            <article className="home-step">
              <span className="home-step-number">04</span>
              <h3>Verify</h3>
              <p>Check the result before sharing the document.</p>
            </article>
          </div>
        </section>

        <section className="home-security" id="security">
          <div className="home-security-mark" aria-hidden="true">✓</div>
          <div>
            <span className="home-section-label">PRIVACY BY DESIGN</span>
            <h2>Protect the information that matters.</h2>
            <p>
              SecurePDF is being built around controlled document
              processing, authenticated access, and verification of
              redaction results. Always review the output before sharing.
            </p>
          </div>
          <button className="home-button" onClick={onGetStarted}>
            Explore SecurePDF <span aria-hidden="true">→</span>
          </button>
        </section>
      </main>

      <footer className="home-footer">
        <a className="home-brand" href="#home">
          <span className="home-brand-mark">S</span>
          <span>SecurePDF</span>
        </a>
        <span>Your documents. Your privacy. Our priority.</span>
        <a href="#home">Back to top ↑</a>
      </footer>
    </div>
  )
}

export default HomePage
