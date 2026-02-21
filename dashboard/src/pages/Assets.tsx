import { TopBar } from '@/components/layout/TopBar'
import { AssetTable } from '@/components/assets/AssetTable'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Cpu, TrendingUp, AlertCircle } from 'lucide-react'

export function Assets() {
  return (
    <div className="flex flex-col h-full overflow-hidden">
      <TopBar
        title="Asset Fleet"
        subtitle="All monitored assets with real-time health scores"
      />
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {/* Info cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Card className="bg-gradient-to-br from-card to-muted/20">
            <CardContent className="pt-4 pb-4 flex items-center gap-3">
              <div className="h-10 w-10 rounded-lg bg-blue-400/10 flex items-center justify-center">
                <Cpu className="h-5 w-5 text-blue-400" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Total Assets</p>
                <p className="text-lg font-semibold">Monitored in real-time</p>
              </div>
            </CardContent>
          </Card>
          <Card className="bg-gradient-to-br from-card to-muted/20">
            <CardContent className="pt-4 pb-4 flex items-center gap-3">
              <div className="h-10 w-10 rounded-lg bg-emerald-400/10 flex items-center justify-center">
                <TrendingUp className="h-5 w-5 text-emerald-400" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Health Scores</p>
                <p className="text-lg font-semibold">Updated every minute</p>
              </div>
            </CardContent>
          </Card>
          <Card className="bg-gradient-to-br from-card to-muted/20">
            <CardContent className="pt-4 pb-4 flex items-center gap-3">
              <div className="h-10 w-10 rounded-lg bg-orange-400/10 flex items-center justify-center">
                <AlertCircle className="h-5 w-5 text-orange-400" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Risk Detection</p>
                <p className="text-lg font-semibold">ML-powered predictions</p>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Asset Table */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-semibold">Asset Inventory</CardTitle>
          </CardHeader>
          <CardContent>
            <AssetTable />
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
