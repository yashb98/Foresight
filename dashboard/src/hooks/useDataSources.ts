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
    },
  })
}

export function useImportJobs(sourceId: string | null) {
  return useQuery({
    queryKey: ['import-jobs', sourceId],
    queryFn: () => fetchImportJobs(sourceId!),
    enabled: !!sourceId,
  })
}
