import { TopBar } from '@/components/layout/TopBar'
import { AlertFeed } from '@/components/alerts/AlertFeed'

export function Alerts() {
  return (
    <div className="flex flex-col h-full overflow-hidden">
      <TopBar
        title="Alert Management"
        subtitle="Real-time alerts from the Spark streaming pipeline"
      />
      <div className="flex-1 overflow-y-auto p-6">
        <AlertFeed maxItems={50} showFilters={true} />
      </div>
    </div>
  )
}
