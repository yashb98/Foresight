import { RefreshCw, Bell, Calendar } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useQueryClient } from '@tanstack/react-query'
import { format } from '@/lib/utils'

interface TopBarProps {
  title: string
  subtitle?: string
}

export function TopBar({ title, subtitle }: TopBarProps) {
  const queryClient = useQueryClient()

  const handleRefresh = () => {
    queryClient.invalidateQueries()
  }

  return (
    <header className="flex items-center justify-between border-b border-border/50 bg-card/30 backdrop-blur-sm px-6 py-4">
      <div>
        <h1 className="text-lg font-semibold text-foreground">{title}</h1>
        {subtitle && <p className="text-sm text-muted-foreground">{subtitle}</p>}
      </div>

      <div className="flex items-center gap-3">
        <div className="hidden md:flex items-center gap-2 text-xs text-muted-foreground mr-4">
          <Calendar className="h-3.5 w-3.5" />
          <span>{format(new Date(), 'MMM d, yyyy')}</span>
        </div>
        <Button 
          variant="ghost" 
          size="icon" 
          onClick={handleRefresh} 
          title="Refresh all data"
          className="hover:bg-muted/50"
        >
          <RefreshCw className="h-4 w-4" />
        </Button>
        <Button 
          variant="ghost" 
          size="icon" 
          title="Notifications"
          className="relative hover:bg-muted/50"
        >
          <Bell className="h-4 w-4" />
          <span className="absolute top-1.5 right-1.5 h-2 w-2 rounded-full bg-primary" />
        </Button>
      </div>
    </header>
  )
}
