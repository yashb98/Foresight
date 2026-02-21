import { TopBar } from '@/components/layout/TopBar'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useAuthStore } from '@/store/auth'

export function Settings() {
  const tenantId = useAuthStore((s) => s.tenantId)

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <TopBar title="Settings" subtitle="Tenant configuration and preferences" />
      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Tenant Information</CardTitle>
            <CardDescription>Your tenant credentials and configuration</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div>
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-1">Tenant ID</p>
              <code className="text-sm font-mono text-foreground bg-muted px-2 py-1 rounded">{tenantId}</code>
            </div>
          </CardContent>
        </Card>

        <Card className="border-dashed">
          <CardContent className="py-8 text-center text-muted-foreground text-sm">
            Additional settings (notifications, integrations, API keys) coming in a future release.
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
