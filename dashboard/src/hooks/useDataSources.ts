import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  fetchDataSources,
  fetchDataSource,
  createDataSource,
  updateDataSource,
  deleteDataSource,
  testConnection,
  testSavedConnection,
  createImportJob,
  fetchImportJobs,
  runImportJob,
  getImportJobStatus,
  cancelImportJob,
  getPipelineStatus,
} from '@/api/endpoints'
import type { CreateDataSourceRequest, UpdateDataSourceRequest, CreateImportJobRequest } from '@/types/dataSource'

export function useDataSources(activeOnly?: boolean) {
  return useQuery({
    queryKey: ['data-sources', activeOnly],
    queryFn: () => fetchDataSources(activeOnly),
    staleTime: 30_000,
  })
}

export function useDataSource(sourceId: string | null) {
  return useQuery({
    queryKey: ['data-source', sourceId],
    queryFn: () => fetchDataSource(sourceId!),
    enabled: !!sourceId,
    staleTime: 30_000,
  })
}

export function useCreateDataSource() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: CreateDataSourceRequest) => createDataSource(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['data-sources'] })
    },
  })
}

export function useUpdateDataSource() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ sourceId, payload }: { sourceId: string; payload: UpdateDataSourceRequest }) =>
      updateDataSource(sourceId, payload),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['data-sources'] })
      queryClient.invalidateQueries({ queryKey: ['data-source', variables.sourceId] })
    },
  })
}

export function useDeleteDataSource() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (sourceId: string) => deleteDataSource(sourceId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['data-sources'] })
    },
  })
}

export function useTestConnection() {
  return useMutation({
    mutationFn: testConnection,
  })
}

export function useTestSavedConnection() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: testSavedConnection,
    onSuccess: (_, sourceId) => {
      queryClient.invalidateQueries({ queryKey: ['data-source', sourceId] })
      queryClient.invalidateQueries({ queryKey: ['data-sources'] })
    },
  })
}

export function useCreateImportJob() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ sourceId, payload }: { sourceId: string; payload: CreateImportJobRequest }) =>
      createImportJob(sourceId, payload),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['import-jobs', variables.sourceId] })
      queryClient.invalidateQueries({ queryKey: ['pipeline-status'] })
    },
  })
}

export function useImportJobs(sourceId: string | null) {
  return useQuery({
    queryKey: ['import-jobs', sourceId],
    queryFn: () => fetchImportJobs(sourceId!),
    enabled: !!sourceId,
    refetchInterval: 5000, // Poll every 5 seconds for active jobs
  })
}

export function useRunImportJob() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: runImportJob,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['import-jobs'] })
      queryClient.invalidateQueries({ queryKey: ['pipeline-status'] })
      queryClient.invalidateQueries({ queryKey: ['fleet-summary'] })
      queryClient.invalidateQueries({ queryKey: ['assets'] })
    },
  })
}

export function useImportJobStatus(jobId: string | null) {
  return useQuery({
    queryKey: ['import-job-status', jobId],
    queryFn: () => getImportJobStatus(jobId!),
    enabled: !!jobId,
    refetchInterval: (data) => {
      // Keep polling while job is running
      if (data?.status === 'running' || data?.status === 'pending') {
        return 2000 // Poll every 2 seconds
      }
      return false
    },
  })
}

export function useCancelImportJob() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: cancelImportJob,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['import-jobs'] })
      queryClient.invalidateQueries({ queryKey: ['import-job-status'] })
    },
  })
}

export function usePipelineStatus() {
  return useQuery({
    queryKey: ['pipeline-status'],
    queryFn: getPipelineStatus,
    refetchInterval: 10000, // Poll every 10 seconds
  })
}
