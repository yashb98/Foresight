/**
 * Data Source Types
 */

export type DataSourceType = 
  | 'postgresql' 
  | 'mysql' 
  | 'mongodb' 
  | 'csv' 
  | 'api' 
  | 'snowflake' 
  | 'bigquery'

export type ConnectionStatus = 'active' | 'inactive' | 'error' | 'testing'

export type ImportJobStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'

export interface DatabaseConfig {
  host: string
  port: number
  database: string
  username: string
  password: string
  ssl_mode?: string
}

export interface MongoConfig {
  connection_string: string
  database: string
}

export interface CSVConfig {
  file_path: string
  delimiter?: string
  has_header?: boolean
  encoding?: string
}

export interface APIConfig {
  base_url: string
  auth_type?: 'none' | 'bearer' | 'api_key' | 'basic'
  auth_token?: string
  api_key?: string
  api_key_header?: string
  username?: string
  password?: string
  headers?: Record<string, string>
  timeout?: number
}

export interface SnowflakeConfig {
  account: string
  warehouse: string
  database: string
  schema: string
  username: string
  password: string
  role?: string
}

export interface BigQueryConfig {
  project_id: string
  dataset: string
  credentials_json?: string
}

export type DataSourceConfig = 
  | DatabaseConfig 
  | MongoConfig 
  | CSVConfig 
  | APIConfig 
  | SnowflakeConfig 
  | BigQueryConfig

export interface DataSource {
  id: string
  tenant_id: string
  name: string
  source_type: DataSourceType
  description?: string
  config: Record<string, unknown>
  is_active: boolean
  status: ConnectionStatus
  last_tested_at?: string
  last_error?: string
  created_at: string
  updated_at?: string
}

export interface DataSourceListResponse {
  total: number
  sources: DataSource[]
}

export interface TestConnectionRequest {
  source_type: DataSourceType
  config: Record<string, unknown>
}

export interface TestConnectionResponse {
  success: boolean
  message: string
  details?: Record<string, unknown>
}

export interface ImportJob {
  id: string
  source_id: string
  tenant_id: string
  target_table: string
  status: ImportJobStatus
  query?: string
  mapping: Record<string, string>
  schedule?: string
  records_imported: number
  records_failed: number
  error_message?: string
  started_at?: string
  completed_at?: string
  created_at: string
}

export interface CreateDataSourceRequest {
  name: string
  source_type: DataSourceType
  description?: string
  config: Record<string, unknown>
  is_active?: boolean
}

export interface UpdateDataSourceRequest {
  name?: string
  description?: string
  config?: Record<string, unknown>
  is_active?: boolean
}

export interface CreateImportJobRequest {
  source_id: string
  target_table: string
  query?: string
  mapping?: Record<string, string>
  schedule?: string
}

export const DATA_SOURCE_LABELS: Record<DataSourceType, string> = {
  postgresql: 'PostgreSQL',
  mysql: 'MySQL',
  mongodb: 'MongoDB',
  csv: 'CSV File',
  api: 'REST API',
  snowflake: 'Snowflake',
  bigquery: 'BigQuery',
}

export const DATA_SOURCE_ICONS: Record<DataSourceType, string> = {
  postgresql: 'database',
  mysql: 'database',
  mongodb: 'leaf',
  csv: 'file-spreadsheet',
  api: 'globe',
  snowflake: 'snowflake',
  bigquery: 'cloud',
}

export const CONNECTION_STATUS_COLORS: Record<ConnectionStatus, string> = {
  active: 'text-emerald-400 bg-emerald-400/10',
  inactive: 'text-muted-foreground bg-muted',
  error: 'text-red-400 bg-red-400/10',
  testing: 'text-yellow-400 bg-yellow-400/10',
}

export const IMPORT_STATUS_COLORS: Record<ImportJobStatus, string> = {
  pending: 'text-muted-foreground bg-muted',
  running: 'text-yellow-400 bg-yellow-400/10',
  completed: 'text-emerald-400 bg-emerald-400/10',
  failed: 'text-red-400 bg-red-400/10',
  cancelled: 'text-orange-400 bg-orange-400/10',
}
