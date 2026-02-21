import { TopBar } from '@/components/layout/TopBar'
import { AssetTable } from '@/components/assets/AssetTable'

export function Assets() {
  return (
    <div className="flex flex-col h-full overflow-hidden">
      <TopBar
        title="Asset Fleet"
        subtitle="All monitored assets with real-time health scores"
      />
      <div className="flex-1 overflow-y-auto p-6">
        <AssetTable />
      </div>
    </div>
  )
}
