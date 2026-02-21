import { TopBar } from '@/components/layout/TopBar'
import { AlertFeed } from '@/components/alerts/AlertFeed'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Bell, CheckCircle, Clock } from 'lucide-react'

export function Alerts() {
  return (
    <div className="flex flex-col h-full overflow-hidden">
      <TopBar
        title="Alert Management"
        subtitle="Real-time alerts from the Spark streaming pipeline"
      />
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {/* Stats cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Card className="bg-gradient-to-br from-card to-muted/20">
            <CardContent className="pt-4 pb-4 flex items-center gap-3">
              <div className="h-10 w-10 rounded-lg bg-red-400/10 flex items-center justify-center">
                <Bell className="h-5 w-5 text-red-400" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Active Alerts</p>
                <p className="text-lg font-semibold">Real-time monitoring</p>
              </div>
            </CardContent>
          </Card>
          <Card className="bg-gradient-to-br from-card to-muted/20">
            <CardContent className="pt-4 pb-4 flex items-center gap-3">
              <div className="h-10 w-10 rounded-lg bg-emerald-400/10 flex items-center justify-center">
                <CheckCircle className="h-5 w-5 text-emerald-400" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Resolution</p>
                <p className="text-lg font-semibold">Track & manage alerts</p>
              </div>
            </CardContent>
          </Card>
          <Card className="bg-gradient-to-br from-card to-muted/20">
            <CardContent className="pt-4 pb-4 flex items-center gap-3">
              <div className="h-10 w-10 rounded-lg bg-blue-400/10 flex items-center justify-center">
                <Clock className="h-5 w-5 text-blue-400" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Updates</p>
                <p className="text-lg font-semibold">Every 30 seconds</p>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Alert Feed */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-semibold">Live Alert Feed</CardTitle>
          </CardHeader>
          <CardContent>
            <AlertFeed maxItems={50} showFilters={true} />
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
