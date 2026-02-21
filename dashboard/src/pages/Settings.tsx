import { TopBar } from '@/components/layout/TopBar'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { 
  Settings2, 
  Database, 
  Bell, 
  Shield, 
  Github,
  Info,
  CheckCircle2,
  Server
} from 'lucide-react'

export function Settings() {
  return (
    <div className="flex flex-col h-full overflow-hidden">
      <TopBar title="Settings" subtitle="Application configuration and system information" />
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {/* System Status */}
        <Card className="bg-gradient-to-br from-emerald-500/5 via-card to-muted/20 border-emerald-500/20">
          <CardContent className="pt-6 pb-6">
            <div className="flex items-center gap-4">
              <div className="h-12 w-12 rounded-xl bg-emerald-400/10 flex items-center justify-center">
                <CheckCircle2 className="h-6 w-6 text-emerald-400" />
              </div>
              <div className="flex-1">
                <h2 className="text-lg font-semibold">All Systems Operational</h2>
                <p className="text-sm text-muted-foreground">
                  All services are running normally. Last checked: {new Date().toLocaleString()}
                </p>
              </div>
              <Badge variant="outline" className="text-emerald-400 border-emerald-400/30">
                v0.1.0
              </Badge>
            </div>
          </CardContent>
        </Card>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* System Information */}
          <Card>
            <CardHeader>
              <CardTitle className="text-sm flex items-center gap-2">
                <Info className="h-4 w-4 text-primary" />
                System Information
              </CardTitle>
              <CardDescription>Version and build details</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex justify-between items-center py-2">
                <span className="text-sm text-muted-foreground">Version</span>
                <code className="text-sm font-mono bg-muted px-2 py-1 rounded">v0.1.0</code>
              </div>
              <Separator />
              <div className="flex justify-between items-center py-2">
                <span className="text-sm text-muted-foreground">Environment</span>
                <Badge variant="secondary">Production</Badge>
              </div>
              <Separator />
              <div className="flex justify-between items-center py-2">
                <span className="text-sm text-muted-foreground">API Status</span>
                <div className="flex items-center gap-2">
                  <div className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
                  <span className="text-sm">Connected</span>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Services */}
          <Card>
            <CardHeader>
              <CardTitle className="text-sm flex items-center gap-2">
                <Server className="h-4 w-4 text-primary" />
                Services
              </CardTitle>
              <CardDescription>Connected backend services</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center gap-3 py-2">
                <div className="h-8 w-8 rounded-lg bg-blue-400/10 flex items-center justify-center">
                  <Database className="h-4 w-4 text-blue-400" />
                </div>
                <div className="flex-1">
                  <p className="text-sm font-medium">PostgreSQL Database</p>
                  <p className="text-xs text-muted-foreground">Primary data store</p>
                </div>
                <div className="h-2 w-2 rounded-full bg-emerald-400" />
              </div>
              <Separator />
              <div className="flex items-center gap-3 py-2">
                <div className="h-8 w-8 rounded-lg bg-orange-400/10 flex items-center justify-center">
                  <Database className="h-4 w-4 text-orange-400" />
                </div>
                <div className="flex-1">
                  <p className="text-sm font-medium">MongoDB</p>
                  <p className="text-xs text-muted-foreground">Time-series data</p>
                </div>
                <div className="h-2 w-2 rounded-full bg-emerald-400" />
              </div>
              <Separator />
              <div className="flex items-center gap-3 py-2">
                <div className="h-8 w-8 rounded-lg bg-purple-400/10 flex items-center justify-center">
                  <Server className="h-4 w-4 text-purple-400" />
                </div>
                <div className="flex-1">
                  <p className="text-sm font-medium">ML Model Server</p>
                  <p className="text-xs text-muted-foreground">Prediction service</p>
                </div>
                <div className="h-2 w-2 rounded-full bg-emerald-400" />
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Coming Soon */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <Card className="border-dashed opacity-60">
            <CardHeader>
              <CardTitle className="text-sm flex items-center gap-2">
                <Bell className="h-4 w-4 text-muted-foreground" />
                Notifications
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                Email and webhook notification settings coming soon.
              </p>
            </CardContent>
          </Card>
          <Card className="border-dashed opacity-60">
            <CardHeader>
              <CardTitle className="text-sm flex items-center gap-2">
                <Settings2 className="h-4 w-4 text-muted-foreground" />
                Integrations
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                Third-party integrations and API keys coming soon.
              </p>
            </CardContent>
          </Card>
          <Card className="border-dashed opacity-60">
            <CardHeader>
              <CardTitle className="text-sm flex items-center gap-2">
                <Shield className="h-4 w-4 text-muted-foreground" />
                Security
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                Security settings and audit logs coming soon.
              </p>
            </CardContent>
          </Card>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-center gap-2 text-xs text-muted-foreground pt-4">
          <Github className="h-3.5 w-3.5" />
          <span>FORESIGHT Predictive Maintenance Platform</span>
          <span>·</span>
          <span>© {new Date().getFullYear()}</span>
        </div>
      </div>
    </div>
  )
}
