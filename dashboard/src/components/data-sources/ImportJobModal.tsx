"use client"

import { useState } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Card } from '@/components/ui/card'
import { useCreateImportJob, useRunImportJob, useImportJobStatus } from '@/hooks/useDataSources'
import { 
  Play, 
  Loader2, 
  CheckCircle2, 
  AlertCircle,
  Database,
  Table,
  FileJson,
  Settings
} from 'lucide-react'
import type { DataSource } from '@/types/dataSource'
import { cn } from '@/lib/utils'

interface ImportJobModalProps {
  open: boolean
  onClose: () => void
  source: DataSource | null
}

export function ImportJobModal({ open, onClose, source }: ImportJobModalProps) {
  const [step, setStep] = useState<'configure' | 'running' | 'complete'>('configure')
  const [targetTable, setTargetTable] = useState('')
  const [query, setQuery] = useState('')
  const [mapping, setMapping] = useState('')
  const [jobId, setJobId] = useState<string | null>(null)
  
  const createMutation = useCreateImportJob()
  const runMutation = useRunImportJob()
  const { data: jobStatus } = useImportJobStatus(jobId)
  
  const handleStartImport = async () => {
    if (!source) return
    
    // Create import job
    const job = await createMutation.mutateAsync({
      sourceId: source.id,
      payload: {
        source_id: source.id,
        target_table: targetTable,
        query: query || undefined,
        mapping: mapping ? JSON.parse(mapping) : {},
      }
    })
    
    setJobId(job.id)
    setStep('running')
    
    // Run the import
    await runMutation.mutateAsync(job.id)
  }
  
  const handleClose = () => {
    setStep('configure')
    setTargetTable('')
    setQuery('')
    setMapping('')
    setJobId(null)
    onClose()
  }
  
  // Auto-advance when complete
  if (step === 'running' && jobStatus?.status === 'completed') {
    setStep('complete')
  }
  
  if (step === 'running' && jobStatus?.status === 'failed') {
    setStep('complete')
  }
  
  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Database className="h-5 w-5 text-primary" />
            Import Data from {source?.name}
          </DialogTitle>
          <DialogDescription>
            Configure and run data import from {source?.source_type}
          </DialogDescription>
        </DialogHeader>
        
        {step === 'configure' && (
          <div className="space-y-4 py-4">
            <Tabs defaultValue="basic" className="w-full">
              <TabsList className="grid w-full grid-cols-2">
                <TabsTrigger value="basic">Basic</TabsTrigger>
                <TabsTrigger value="advanced">Advanced</TabsTrigger>
              </TabsList>
              
              <TabsContent value="basic" className="space-y-4">
                <div>
                  <Label htmlFor="target-table">Target Table *</Label>
                  <Input
                    id="target-table"
                    placeholder="e.g., raw_sensor_data"
                    value={targetTable}
                    onChange={(e) => setTargetTable(e.target.value)}
                  />
                  <p className="text-xs text-muted-foreground mt-1">
                    Table where data will be imported (will be created if not exists)
                  </p>
                </div>
                
                <div>
                  <Label htmlFor="query">Query / Filter (optional)</Label>
                  <Textarea
                    id="query"
                    placeholder={source?.source_type === 'mongodb' 
                      ? '{ "status": "active" }' 
                      : 'SELECT * FROM table WHERE date > 2024-01-01'}
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    rows={3}
                  />
                </div>
              </TabsContent>
              
              <TabsContent value="advanced" className="space-y-4">
                <div>
                  <Label htmlFor="mapping">Column Mapping (JSON)</Label>
                  <Textarea
                    id="mapping"
                    placeholder={`{\n  "source_column": "target_column",\n  "old_name": "new_name"\n}`}
                    value={mapping}
                    onChange={(e) => setMapping(e.target.value)}
                    rows={6}
                    className="font-mono text-xs"
                  />
                  <p className="text-xs text-muted-foreground mt-1">
                    Map source columns to different target column names
                  </p>
                </div>
              </TabsContent>
            </Tabs>
            
            <div className="flex justify-end gap-3 pt-4">
              <Button variant="outline" onClick={handleClose}>
                Cancel
              </Button>
              <Button 
                onClick={handleStartImport}
                disabled={!targetTable || createMutation.isPending}
                className="gap-2"
              >
                {createMutation.isPending ? (
                  <><Loader2 className="h-4 w-4 animate-spin" /> Creating...</>
                ) : (
                  <><Play className="h-4 w-4" /> Start Import</>
                )}
              </Button>
            </div>
          </div>
        )}
        
        {step === 'running' && (
          <div className="py-8 flex flex-col items-center">
            <Loader2 className="h-12 w-12 text-primary animate-spin mb-4" />
            <h3 className="text-lg font-medium">Importing Data...</h3>
            <p className="text-sm text-muted-foreground mt-1">
              {jobStatus?.status === 'pending' && 'Waiting to start...'}
              {jobStatus?.status === 'running' && 'Processing records...'}
            </p>
            
            {jobStatus && (
              <div className="mt-6 grid grid-cols-2 gap-4 w-full max-w-xs">
                <Card className="p-3 text-center">
                  <p className="text-2xl font-bold text-emerald-400">
                    {jobStatus.records_imported || 0}
                  </p>
                  <p className="text-xs text-muted-foreground">Imported</p>
                </Card>
                <Card className="p-3 text-center">
                  <p className="text-2xl font-bold text-red-400">
                    {jobStatus.records_failed || 0}
                  </p>
                  <p className="text-xs text-muted-foreground">Failed</p>
                </Card>
              </div>
            )}
          </div>
        )}
        
        {step === 'complete' && (
          <div className="py-8 flex flex-col items-center">
            {jobStatus?.status === 'completed' ? (
              <>
                <CheckCircle2 className="h-12 w-12 text-emerald-400 mb-4" />
                <h3 className="text-lg font-medium">Import Complete!</h3>
                <p className="text-sm text-muted-foreground mt-1">
                  Successfully imported {jobStatus?.records_imported} records
                </p>
              </>
            ) : (
              <>
                <AlertCircle className="h-12 w-12 text-red-400 mb-4" />
                <h3 className="text-lg font-medium">Import Failed</h3>
                <p className="text-sm text-muted-foreground mt-1">
                  {jobStatus?.error_message || 'An error occurred during import'}
                </p>
              </>
            )}
            
            <div className="mt-6 grid grid-cols-2 gap-4 w-full max-w-xs">
              <Card className="p-3 text-center">
                <p className="text-2xl font-bold text-emerald-400">
                  {jobStatus?.records_imported || 0}
                </p>
                <p className="text-xs text-muted-foreground">Imported</p>
              </Card>
              <Card className="p-3 text-center">
                <p className="text-2xl font-bold text-red-400">
                  {jobStatus?.records_failed || 0}
                </p>
                <p className="text-xs text-muted-foreground">Failed</p>
              </Card>
            </div>
            
            <Button onClick={handleClose} className="mt-6">
              Close
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
