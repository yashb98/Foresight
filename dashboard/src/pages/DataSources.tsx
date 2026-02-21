/**
 * Data Sources Page — Manage external data connections
 */

import { useState } from 'react'
import { TopBar } from '@/components/layout/TopBar'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Input } from '@/components/ui/input'
import { 
  useDataSources, 
  useDeleteDataSource, 
  useTestSavedConnection 
} from '@/hooks/useDataSources'
import { 
  Database, 
  FileSpreadsheet, 
  Globe, 
  Snowflake, 
  Cloud,
  Leaf,
  Plus, 
  Trash2, 
  RefreshCw, 
  CheckCircle2, 
  XCircle,
  AlertCircle,
  Clock,
  Search,
  Settings2,
  Plug,
  MoreVertical
} from 'lucide-react'
import type { DataSource, DataSourceType, ConnectionStatus } from '@/types/dataSource'
import { 
  DATA_SOURCE_LABELS, 
  CONNECTION_STATUS_COLORS 
} from '@/types/dataSource'
import { cn } from '@/lib/utils'

const SOURCE_ICONS: Record<DataSourceType, React.FC<{ className?: string }>> = {
  postgresql: Database,
  mysql: Database,
  mongodb: Leaf,
  csv: FileSpreadsheet,
  api: Globe,
  snowflake: Snowflake,
  bigquery: Cloud,
}

export function DataSources() {
  const [search, setSearch] = useState('')
  const { data, isLoading } = useDataSources()
  const sources = data?.sources ?? []
  
  const filtered = sources.filter(s => 
    s.name.toLowerCase().includes(search.toLowerCase()) ||
    s.source_type.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <TopBar
        title="Data Sources"
        subtitle="Connect to external databases, APIs, and files"
      />
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {/* Stats */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <StatCard
            title="Total Sources"
            value={sources.length}
            icon={Database}
            color="text-blue-400"
            bgColor="bg-blue-400/10"
          />
          <StatCard
            title="Active"
            value={sources.filter(s => s.status === 'active').length}
            icon={CheckCircle2}
            color="text-emerald-400"
            bgColor="bg-emerald-400/10"
          />
          <StatCard
            title="Error"
            value={sources.filter(s => s.status === 'error').length}
            icon={XCircle}
            color="text-red-400"
            bgColor="bg-red-400/10"
          />
          <StatCard
            title="Available Types"
            value={Object.keys(DATA_SOURCE_LABELS).length}
            icon={Plug}
            color="text-primary"
            bgColor="bg-primary/10"
          />
        </div>

        {/* Toolbar */}
        <div className="flex items-center gap-4">
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search data sources..."
              className="pl-9"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <Button className="gap-2">
            <Plus className="h-4 w-4" />
            Add Connection
          </Button>
        </div>

        {/* Sources Grid */}
        {isLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-48" />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <EmptyState />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {filtered.map((source) => (
              <SourceCard key={source.id} source={source} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function StatCard({ 
  title, 
  value, 
  icon: Icon, 
  color, 
  bgColor 
}: { 
  title: string
  value: number
  icon: React.FC<{ className?: string }>
  color: string
  bgColor: string
}) {
  return (
    <Card>
      <CardContent className="pt-4 pb-4 flex items-center gap-3">
        <div className={cn("h-10 w-10 rounded-lg flex items-center justify-center", bgColor)}>
          <Icon className={cn("h-5 w-5", color)} />
        </div>
        <div>
          <p className="text-xs text-muted-foreground">{title}</p>
          <p className="text-2xl font-semibold">{value}</p>
        </div>
      </CardContent>
    </Card>
  )
}

function SourceCard({ source }: { source: DataSource }) {
  const testMutation = useTestSavedConnection()
  const deleteMutation = useDeleteDataSource()
  const Icon = SOURCE_ICONS[source.source_type]
  
  const handleTest = () => {
    testMutation.mutate(source.id)
  }
  
  const handleDelete = () => {
    if (confirm('Are you sure you want to delete this data source?')) {
      deleteMutation.mutate(source.id)
    }
  }

  return (
    <Card className={cn(
      "relative overflow-hidden transition-all hover:border-primary/30",
      !source.is_active && "opacity-60"
    )}>
      <CardContent className="pt-5 pb-4">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-lg bg-primary/10 flex items-center justify-center">
              <Icon className="h-5 w-5 text-primary" />
            </div>
            <div>
              <h3 className="font-medium text-foreground">{source.name}</h3>
              <p className="text-xs text-muted-foreground">
                {DATA_SOURCE_LABELS[source.source_type]}
              </p>
            </div>
          </div>
          <StatusBadge status={source.status} />
        </div>

        {source.description && (
          <p className="mt-3 text-sm text-muted-foreground line-clamp-2">
            {source.description}
          </p>
        )}

        <div className="mt-4 flex items-center gap-4 text-xs text-muted-foreground">
          <div className="flex items-center gap-1">
            <Clock className="h-3.5 w-3.5" />
            {source.last_tested_at 
              ? `Tested ${new Date(source.last_tested_at).toLocaleDateString()}`
              : 'Never tested'
            }
          </div>
        </div>

        {source.last_error && (
          <div className="mt-3 p-2 rounded bg-red-400/10 text-xs text-red-400">
            <AlertCircle className="h-3.5 w-3.5 inline mr-1" />
            {source.last_error}
          </div>
        )}

        <div className="mt-4 flex items-center gap-2">
          <Button 
            variant="outline" 
            size="sm" 
            className="flex-1 gap-1.5"
            onClick={handleTest}
            disabled={testMutation.isPending}
          >
            {testMutation.isPending ? (
              <RefreshCw className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <RefreshCw className="h-3.5 w-3.5" />
            )}
            Test
          </Button>
          <Button 
            variant="outline" 
            size="sm" 
            className="flex-1 gap-1.5"
          >
            <Settings2 className="h-3.5 w-3.5" />
            Configure
          </Button>
          <Button 
            variant="ghost" 
            size="icon" 
            className="h-8 w-8 text-muted-foreground hover:text-destructive"
            onClick={handleDelete}
            disabled={deleteMutation.isPending}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

function StatusBadge({ status }: { status: ConnectionStatus }) {
  return (
    <Badge 
      variant="outline" 
      className={cn(
        "text-[10px] font-medium capitalize",
        CONNECTION_STATUS_COLORS[status]
      )}
    >
      {status}
    </Badge>
  )
}

function EmptyState() {
  return (
    <Card className="border-dashed">
      <CardContent className="py-16 flex flex-col items-center text-muted-foreground">
        <div className="h-16 w-16 rounded-full bg-muted/50 flex items-center justify-center mb-4">
          <Database className="h-8 w-8 opacity-30" />
        </div>
        <p className="text-lg font-medium">No data sources configured</p>
        <p className="text-sm mt-1">Add your first connection to start importing data</p>
        <Button className="mt-4 gap-2">
          <Plus className="h-4 w-4" />
          Add Connection
        </Button>
      </CardContent>
    </Card>
  )
}
