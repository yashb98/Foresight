/**
 * Login Page — JWT credential form
 */

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Zap, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { login } from '@/api/endpoints'
import { useAuthStore } from '@/store/auth'

export function Login() {
  const [clientId, setClientId] = useState('')
  const [clientSecret, setClientSecret] = useState('')
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  const { login: storeLogin } = useAuthStore()
  const navigate = useNavigate()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setIsLoading(true)

    try {
      const token = await login(clientId, clientSecret)
      storeLogin(token.access_token, token.tenant_id)
      navigate('/dashboard', { replace: true })
    } catch (err: unknown) {
      const apiErr = err as { message?: string }
      setError(apiErr?.message ?? 'Authentication failed. Please check your credentials.')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-primary mb-4">
            <Zap className="h-8 w-8 text-primary-foreground" />
          </div>
          <h1 className="text-2xl font-bold text-foreground">FORESIGHT</h1>
          <p className="text-sm text-muted-foreground mt-1">Predictive Asset Maintenance Platform</p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Sign In</CardTitle>
            <CardDescription>
              Enter your tenant credentials to access the dashboard
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-foreground" htmlFor="client-id">
                  Client ID
                </label>
                <Input
                  id="client-id"
                  type="text"
                  placeholder="your-client-id"
                  value={clientId}
                  onChange={(e) => setClientId(e.target.value)}
                  required
                  autoComplete="username"
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-sm font-medium text-foreground" htmlFor="client-secret">
                  Client Secret
                </label>
                <Input
                  id="client-secret"
                  type="password"
                  placeholder="••••••••••••"
                  value={clientSecret}
                  onChange={(e) => setClientSecret(e.target.value)}
                  required
                  autoComplete="current-password"
                />
              </div>

              {error && (
                <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                  {error}
                </div>
              )}

              <Button type="submit" className="w-full" disabled={isLoading}>
                {isLoading ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Authenticating…
                  </>
                ) : (
                  'Sign In'
                )}
              </Button>
            </form>

            {/* Dev hint */}
            <div className="mt-4 rounded-md bg-muted/50 px-3 py-2 text-xs text-muted-foreground space-y-1">
              <p><strong>Demo credentials (no database needed):</strong></p>
              <p>
                <code className="text-primary">tenant1</code>
                {' / '}
                <code className="text-primary">password123</code>
                {' '}— Meridian Power &amp; Water
              </p>
              <p>
                <code className="text-primary">tenant2</code>
                {' / '}
                <code className="text-primary">password456</code>
                {' '}— TransRail Infrastructure
              </p>
            </div>
          </CardContent>
        </Card>

        <p className="mt-6 text-center text-xs text-muted-foreground">
          © {new Date().getFullYear()} FORESIGHT · Predictive Asset Maintenance
        </p>
      </div>
    </div>
  )
}
