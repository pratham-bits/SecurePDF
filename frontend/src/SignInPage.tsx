
import { useState, type FormEvent } from 'react'
import { login } from './api/client'
import './App.css'

type SignInPageProps = {
  onAuthenticated: (accessToken: string) => void
  onBackToHome: () => void
}

function SignInPage({
  onAuthenticated,
  onBackToHome,
}: SignInPageProps) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')

    if (isSubmitting) return

    setIsSubmitting(true)

    try {
      const response = await login({
        email: email.trim(),
        password,
      })

      if (
        !response.access_token ||
        response.token_type.toLowerCase() !== 'bearer'
      ) {
        throw new Error('The server returned an invalid login response.')
      }

      onAuthenticated(response.access_token)
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Unable to sign in. Please try again.',
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <main className="auth-page">
      <header className="auth-header">
        <button
          className="auth-brand"
          type="button"
          onClick={onBackToHome}
          aria-label="Return to SecurePDF home"
        >
          <span className="auth-brand-mark">S</span>
          <span>SecurePDF</span>
        </button>

        <button
          className="auth-home-link"
          type="button"
          onClick={onBackToHome}
        >
          ← Back to home
        </button>
      </header>

      <section className="auth-layout">
        <div className="auth-intro">
          <span className="auth-eyebrow">YOUR DOCUMENT SECURITY WORKSPACE</span>

          <h1>
            Welcome back.
            <br />
            <span>Your privacy matters.</span>
          </h1>

          <p>
            Sign in to manage your documents, monitor processing jobs,
            and protect sensitive information in your PDFs.
          </p>

          <div className="auth-security-note">
            <span aria-hidden="true">✓</span>
            Authenticated access to your workspace
          </div>
        </div>

        <div className="auth-card">
          <div className="auth-card-heading">
            <h2>Sign in to SecurePDF</h2>
            <p>Enter your account credentials to continue.</p>
          </div>

          <form className="auth-form" onSubmit={handleSubmit}>
            <div className="auth-field">
              <label htmlFor="signin-email">Email address</label>
              <input
                id="signin-email"
                type="email"
                name="email"
                autoComplete="email"
                placeholder="you@example.com"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
                maxLength={254}
                disabled={isSubmitting}
              />
            </div>

            <div className="auth-field">
              <label htmlFor="signin-password">Password</label>
              <input
                id="signin-password"
                type="password"
                name="password"
                autoComplete="current-password"
                placeholder="Enter your password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
                disabled={isSubmitting}
              />
            </div>

            {error && (
              <div className="auth-error" role="alert">
                <span aria-hidden="true">!</span>
                <span>{error}</span>
              </div>
            )}

            <button
              className="home-button auth-submit"
              type="submit"
              disabled={isSubmitting}
            >
              {isSubmitting ? 'Signing in…' : 'Sign in'}
              {!isSubmitting && <span aria-hidden="true">→</span>}
            </button>
          </form>

          <p className="auth-footer-note">
            Your credentials are sent to the SecurePDF backend over
            the configured API connection.
          </p>
        </div>
      </section>
    </main>
  )
}

export default SignInPage
