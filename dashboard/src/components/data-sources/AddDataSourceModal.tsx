"use client"

import { useState } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Switch } from '@/components/ui/switch'
import { Separator } from '@/components/ui/separator'
import { useCreateDataSource, useTestConnection } from '@/hooks/useDataSources'
import { 
  Database, 
  FileSpreadsheet, 
  Globe, 
  Snowflake, 
  Cloud,
  Leaf,
  ArrowLeft,
  CheckCircle2,
  AlertCircle,
  Loader2,
  RefreshCw,
  FolderOpen,
  Settings
} from 'lucide-react'
import type { DataSourceType } from '@/types/dataSource'
import { DATA_SOURCE_LABELS } from '@/types/dataSource'
import { cn } from '@/lib/utils'

interface AddDataSourceModalProps {
  open: boolean
  onClose: () => void
}

type Step = 'select-type' | 'configure' | 'test'

const SOURCE_TYPES: { type: DataSourceType; icon: React.FC<{ className?: string }>; description: string }[] = [
  { type: 'postgresql', icon: Database, description: 'Connect to PostgreSQL database' },
  { type: 'mysql', icon: Database, description: 'Connect to MySQL database' },
  { type: 'mongodb', icon: Leaf, description: 'Connect to MongoDB cluster' },
  { type: 'snowflake', icon: Snowflake, description: 'Connect to Snowflake warehouse' },
  { type: 'bigquery', icon: Cloud, description: 'Connect to Google BigQuery' },
  { type: 'csv', icon: FileSpreadsheet, description: 'Import from CSV file' },
  { type: 'api', icon: Globe, description: 'Connect to REST API endpoint' },
]

export function AddDataSourceModal({ open, onClose }: AddDataSourceModalProps) {
  const [step, setStep] = useState<Step>('select-type')
  const [selectedType, setSelectedType] = useState<DataSourceType | null>(null)
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null)
  
  // Form states
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [isActive, setIsActive] = useState(true)
  
  // Database config
  const [host, setHost] = useState('')
  const [port, setPort] = useState('')
  const [database, setDatabase] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [sslMode, setSslMode] = useState('prefer')
  
  // MongoDB config
  const [connectionString, setConnectionString] = useState('')
  const [mongoDatabase, setMongoDatabase] = useState('')
  
  // CSV config
  const [filePath, setFilePath] = useState('')
  const [delimiter, setDelimiter] = useState(',')
  const [hasHeader, setHasHeader] = useState(true)
  const [encoding, setEncoding] = useState('utf-8')
  
  // API config
  const [baseUrl, setBaseUrl] = useState('')
  const [authType, setAuthType] = useState<'none' | 'bearer' | 'api_key' | 'basic'>('none')
  const [authToken, setAuthToken] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [apiKeyHeader, setApiKeyHeader] = useState('X-API-Key')
  const [apiUsername, setApiUsername] = useState('')
  const [apiPassword, setApiPassword] = useState('')
  const [apiTimeout, setApiTimeout] = useState('30')
  
  // Snowflake config
  const [sfAccount, setSfAccount] = useState('')
  const [sfWarehouse, setSfWarehouse] = useState('')
  const [sfDatabase, setSfDatabase] = useState('')
  const [sfSchema, setSfSchema] = useState('')
  const [sfUsername, setSfUsername] = useState('')
  const [sfPassword, setSfPassword] = useState('')
  const [sfRole, setSfRole] = useState('')
  
  // BigQuery config
  const [bqProjectId, setBqProjectId] = useState('')
  const [bqDataset, setBqDataset] = useState('')
  const [bqCredentials, setBqCredentials] = useState('')
  
  const createMutation = useCreateDataSource()
  const testMutation = useTestConnection()
  
  const resetForm = () => {
    setStep('select-type')
    setSelectedType(null)
    setTestResult(null)
    setName('')
    setDescription('')
    setIsActive(true)
    setHost('')
    setPort('')
    setDatabase('')
    setUsername('')
    setPassword('')
    setSslMode('prefer')
    setConnectionString('')
    setMongoDatabase('')
    setFilePath('')
    setDelimiter(',')
    setHasHeader(true)
    setEncoding('utf-8')
    setBaseUrl('')
    setAuthType('none')
    setAuthToken('')
    setApiKey('')
    setApiKeyHeader('X-API-Key')
    setApiUsername('')
    setApiPassword('')
    setApiTimeout('30')
    setSfAccount('')
    setSfWarehouse('')
    setSfDatabase('')
    setSfSchema('')
    setSfUsername('')
    setSfPassword('')
    setSfRole('')
    setBqProjectId('')
    setBqDataset('')
    setBqCredentials('')
  }
  
  const handleClose = () => {
    resetForm()
    onClose()
  }
  
  const getConfig = () => {
    switch (selectedType) {
      case 'postgresql':
      case 'mysql':
        return {
          host,
          port: parseInt(port) || (selectedType === 'postgresql' ? 5432 : 3306),
          database,
          username,
          password,
          ssl_mode: sslMode,
        }
      case 'mongodb':
        return {
          connection_string: connectionString,
          database: mongoDatabase,
        }
      case 'csv':
        return {
          file_path: filePath,
          delimiter,
          has_header: hasHeader,
          encoding,
        }
      case 'api':
        return {
          base_url: baseUrl,
          auth_type: authType,
          ...(authType === 'bearer' && { auth_token: authToken }),
          ...(authType === 'api_key' && { api_key: apiKey, api_key_header: apiKeyHeader }),
          ...(authType === 'basic' && { username: apiUsername, password: apiPassword }),
          timeout: parseInt(apiTimeout) || 30,
        }
      case 'snowflake':
        return {
          account: sfAccount,
          warehouse: sfWarehouse,
          database: sfDatabase,
          schema: sfSchema,
          username: sfUsername,
          password: sfPassword,
          role: sfRole || undefined,
        }
      case 'bigquery':
        return {
          project_id: bqProjectId,
          dataset: bqDataset,
          credentials_json: bqCredentials || undefined,
        }
      default:
        return {}
    }
  }
  
  const handleTest = async () => {
    if (!selectedType) return
    
    setTestResult(null)
    const result = await testMutation.mutateAsync({
      source_type: selectedType,
      config: getConfig(),
    })
    
    setTestResult({
      success: result.success,
      message: result.message,
    })
  }
  
  const handleSave = async () => {
    if (!selectedType) return
    
    await createMutation.mutateAsync({
      name,
      source_type: selectedType,
      description: description || undefined,
      config: getConfig(),
      is_active: isActive,
    })
    
    handleClose()
  }
  
  const isConfigValid = () => {
    if (!name.trim()) return false
    
    switch (selectedType) {
      case 'postgresql':
      case 'mysql':
        return host && port && database && username && password
      case 'mongodb':
        return connectionString && mongoDatabase
      case 'csv':
        return filePath
      case 'api':
        return baseUrl
      case 'snowflake':
        return sfAccount && sfWarehouse && sfDatabase && sfSchema && sfUsername && sfPassword
      case 'bigquery':
        return bqProjectId && bqDataset
      default:
        return false
    }
  }
  
  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {step !== 'select-type' && (
              <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => setStep('select-type')}>
                <ArrowLeft className="h-4 w-4" />
              </Button>
            )}
            Add Data Source
          </DialogTitle>
          <DialogDescription>
            {step === 'select-type' && 'Select the type of data source you want to connect'}
            {step === 'configure' && `Configure ${selectedType ? DATA_SOURCE_LABELS[selectedType] : ''} connection`}
            {step === 'test' && 'Test your connection before saving'}
          </DialogDescription>
        </DialogHeader>
        
        {step === 'select-type' && (
          <div className="grid grid-cols-2 gap-3 py-4">
            {SOURCE_TYPES.map(({ type, icon: Icon, description }) => (
              <Card
                key={type}
                className="p-4 cursor-pointer hover:border-primary/50 hover:bg-primary/5 transition-all"
                onClick={() => {
                  setSelectedType(type)
                  setStep('configure')
                  if (type === 'postgresql') setPort('5432')
                  if (type === 'mysql') setPort('3306')
                }}
              >
                <div className="flex items-start gap-3">
                  <div className="h-10 w-10 rounded-lg bg-primary/10 flex items-center justify-center">
                    <Icon className="h-5 w-5 text-primary" />
                  </div>
                  <div>
                    <h3 className="font-medium">{DATA_SOURCE_LABELS[type]}</h3>
                    <p className="text-xs text-muted-foreground mt-0.5">{description}</p>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        )}
        
        {step === 'configure' && selectedType && (
          <div className="space-y-4 py-4">
            <div className="space-y-3">
              <div>
                <Label htmlFor="name">Connection Name *</Label>
                <Input
                  id="name"
                  placeholder="e.g., Production PostgreSQL"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </div>
              <div>
                <Label htmlFor="description">Description</Label>
                <Textarea
                  id="description"
                  placeholder="Optional description of this connection"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  rows={2}
                />
              </div>
              <div className="flex items-center gap-2">
                <Switch
                  id="active"
                  checked={isActive}
                  onCheckedChange={setIsActive}
                />
                <Label htmlFor="active" className="cursor-pointer">Active</Label>
              </div>
            </div>
            
            <Separator />
            
            <div className="space-y-4">
              <h4 className="font-medium flex items-center gap-2">
                <Settings className="h-4 w-4" />
                Configuration
              </h4>
              
              {(selectedType === 'postgresql' || selectedType === 'mysql') && (
                <DatabaseConfigForm
                  host={host}
                  setHost={setHost}
                  port={port}
                  setPort={setPort}
                  database={database}
                  setDatabase={setDatabase}
                  username={username}
                  setUsername={setUsername}
                  password={password}
                  setPassword={setPassword}
                  sslMode={sslMode}
                  setSslMode={setSslMode}
                />
              )}
              
              {selectedType === 'mongodb' && (
                <MongoDBConfigForm
                  connectionString={connectionString}
                  setConnectionString={setConnectionString}
                  database={mongoDatabase}
                  setDatabase={setMongoDatabase}
                />
              )}
              
              {selectedType === 'csv' && (
                <CSVConfigForm
                  filePath={filePath}
                  setFilePath={setFilePath}
                  delimiter={delimiter}
                  setDelimiter={setDelimiter}
                  hasHeader={hasHeader}
                  setHasHeader={setHasHeader}
                  encoding={encoding}
                  setEncoding={setEncoding}
                />
              )}
              
              {selectedType === 'api' && (
                <APIConfigForm
                  baseUrl={baseUrl}
                  setBaseUrl={setBaseUrl}
                  authType={authType}
                  setAuthType={setAuthType}
                  authToken={authToken}
                  setAuthToken={setAuthToken}
                  apiKey={apiKey}
                  setApiKey={setApiKey}
                  apiKeyHeader={apiKeyHeader}
                  setApiKeyHeader={setApiKeyHeader}
                  username={apiUsername}
                  setUsername={setApiUsername}
                  password={apiPassword}
                  setPassword={setApiPassword}
                  timeout={apiTimeout}
                  setTimeout={setApiTimeout}
                />
              )}
              
              {selectedType === 'snowflake' && (
                <SnowflakeConfigForm
                  account={sfAccount}
                  setAccount={setSfAccount}
                  warehouse={sfWarehouse}
                  setWarehouse={setSfWarehouse}
                  database={sfDatabase}
                  setDatabase={setSfDatabase}
                  schema={sfSchema}
                  setSchema={setSfSchema}
                  username={sfUsername}
                  setUsername={setSfUsername}
                  password={sfPassword}
                  setPassword={setSfPassword}
                  role={sfRole}
                  setRole={setSfRole}
                />
              )}
              
              {selectedType === 'bigquery' && (
                <BigQueryConfigForm
                  projectId={bqProjectId}
                  setProjectId={setBqProjectId}
                  dataset={bqDataset}
                  setDataset={setBqDataset}
                  credentials={bqCredentials}
                  setCredentials={setBqCredentials}
                />
              )}
            </div>
            
            <div className="flex justify-end gap-3 pt-4">
              <Button variant="outline" onClick={() => setStep('select-type')}>
                Back
              </Button>
              <Button
                onClick={() => setStep('test')}
                disabled={!isConfigValid()}
              >
                Continue
              </Button>
            </div>
          </div>
        )}
        
        {step === 'test' && selectedType && (
          <div className="space-y-4 py-4">
            <Card className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="font-medium">{name}</h4>
                  <p className="text-sm text-muted-foreground">{DATA_SOURCE_LABELS[selectedType]}</p>
                </div>
                <Button
                  variant="outline"
                  onClick={handleTest}
                  disabled={testMutation.isPending}
                >
                  {testMutation.isPending ? (
                    <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Testing...</>
                  ) : (
                    <><RefreshCw className="h-4 w-4 mr-2" /> Test Connection</>
                  )}
                </Button>
              </div>
            </Card>
            
            {testResult && (
              <div className={cn(
                "p-4 rounded-lg flex items-start gap-3",
                testResult.success ? "bg-emerald-400/10 text-emerald-400" : "bg-red-400/10 text-red-400"
              )}>
                {testResult.success ? (
                  <CheckCircle2 className="h-5 w-5 mt-0.5" />
                ) : (
                  <AlertCircle className="h-5 w-5 mt-0.5" />
                )}
                <div>
                  <p className="font-medium">{testResult.success ? 'Connection Successful' : 'Connection Failed'}</p>
                  <p className="text-sm mt-1">{testResult.message}</p>
                </div>
              </div>
            )}
            
            <div className="flex justify-end gap-3 pt-4">
              <Button variant="outline" onClick={() => setStep('configure')}>
                Back
              </Button>
              <Button
                onClick={handleSave}
                disabled={!testResult?.success || createMutation.isPending}
              >
                {createMutation.isPending ? (
                  <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Saving...</>
                ) : (
                  'Save Connection'
                )}
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

function DatabaseConfigForm({
  host, setHost,
  port, setPort,
  database, setDatabase,
  username, setUsername,
  password, setPassword,
  sslMode, setSslMode,
}: {
  host: string; setHost: (v: string) => void
  port: string; setPort: (v: string) => void
  database: string; setDatabase: (v: string) => void
  username: string; setUsername: (v: string) => void
  password: string; setPassword: (v: string) => void
  sslMode: string; setSslMode: (v: string) => void
}) {
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label htmlFor="host">Host *</Label>
          <Input
            id="host"
            placeholder="localhost or IP"
            value={host}
            onChange={(e) => setHost(e.target.value)}
          />
        </div>
        <div>
          <Label htmlFor="port">Port *</Label>
          <Input
            id="port"
            type="number"
            placeholder="5432"
            value={port}
            onChange={(e) => setPort(e.target.value)}
          />
        </div>
      </div>
      <div>
        <Label htmlFor="database">Database *</Label>
        <Input
          id="database"
          placeholder="database_name"
          value={database}
          onChange={(e) => setDatabase(e.target.value)}
        />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label htmlFor="username">Username *</Label>
          <Input
            id="username"
            placeholder="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
        </div>
        <div>
          <Label htmlFor="password">Password *</Label>
          <Input
            id="password"
            type="password"
            placeholder="••••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
      </div>
      <div>
        <Label htmlFor="ssl">SSL Mode</Label>
        <select
          id="ssl"
          className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm"
          value={sslMode}
          onChange={(e) => setSslMode(e.target.value)}
        >
          <option value="disable">Disable</option>
          <option value="allow">Allow</option>
          <option value="prefer">Prefer</option>
          <option value="require">Require</option>
          <option value="verify-ca">Verify CA</option>
          <option value="verify-full">Verify Full</option>
        </select>
      </div>
    </div>
  )
}

function MongoDBConfigForm({
  connectionString, setConnectionString,
  database, setDatabase,
}: {
  connectionString: string; setConnectionString: (v: string) => void
  database: string; setDatabase: (v: string) => void
}) {
  return (
    <div className="space-y-3">
      <div>
        <Label htmlFor="conn-str">Connection String *</Label>
        <Input
          id="conn-str"
          placeholder="mongodb+srv://username:password@cluster.mongodb.net"
          value={connectionString}
          onChange={(e) => setConnectionString(e.target.value)}
        />
        <p className="text-xs text-muted-foreground mt-1">
          MongoDB connection URI with credentials
        </p>
      </div>
      <div>
        <Label htmlFor="mongo-db">Database Name *</Label>
        <Input
          id="mongo-db"
          placeholder="my_database"
          value={database}
          onChange={(e) => setDatabase(e.target.value)}
        />
      </div>
    </div>
  )
}

function CSVConfigForm({
  filePath, setFilePath,
  delimiter, setDelimiter,
  hasHeader, setHasHeader,
  encoding, setEncoding,
}: {
  filePath: string; setFilePath: (v: string) => void
  delimiter: string; setDelimiter: (v: string) => void
  hasHeader: boolean; setHasHeader: (v: boolean) => void
  encoding: string; setEncoding: (v: string) => void
}) {
  return (
    <div className="space-y-3">
      <div>
        <Label htmlFor="file-path">File Path *</Label>
        <div className="flex gap-2">
          <Input
            id="file-path"
            placeholder="/path/to/file.csv or s3://bucket/file.csv"
            value={filePath}
            onChange={(e) => setFilePath(e.target.value)}
            className="flex-1"
          />
          <Button variant="outline" size="icon" type="button">
            <FolderOpen className="h-4 w-4" />
          </Button>
        </div>
      </div>
      <div className="grid grid-cols-3 gap-3">
        <div>
          <Label htmlFor="delimiter">Delimiter</Label>
          <Input
            id="delimiter"
            placeholder=","
            maxLength={1}
            value={delimiter}
            onChange={(e) => setDelimiter(e.target.value)}
          />
        </div>
        <div>
          <Label htmlFor="encoding">Encoding</Label>
          <Input
            id="encoding"
            placeholder="utf-8"
            value={encoding}
            onChange={(e) => setEncoding(e.target.value)}
          />
        </div>
        <div className="flex items-end">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={hasHeader}
              onChange={(e) => setHasHeader(e.target.checked)}
              className="rounded border-input"
            />
            <span className="text-sm">Has header</span>
          </label>
        </div>
      </div>
    </div>
  )
}

function APIConfigForm({
  baseUrl, setBaseUrl,
  authType, setAuthType,
  authToken, setAuthToken,
  apiKey, setApiKey,
  apiKeyHeader, setApiKeyHeader,
  username, setUsername,
  password, setPassword,
  timeout, setTimeout,
}: {
  baseUrl: string; setBaseUrl: (v: string) => void
  authType: 'none' | 'bearer' | 'api_key' | 'basic'
  setAuthType: (v: 'none' | 'bearer' | 'api_key' | 'basic') => void
  authToken: string; setAuthToken: (v: string) => void
  apiKey: string; setApiKey: (v: string) => void
  apiKeyHeader: string; setApiKeyHeader: (v: string) => void
  username: string; setUsername: (v: string) => void
  password: string; setPassword: (v: string) => void
  timeout: string; setTimeout: (v: string) => void
}) {
  return (
    <Tabs defaultValue="connection" className="w-full">
      <TabsList className="grid w-full grid-cols-2">
        <TabsTrigger value="connection">Connection</TabsTrigger>
        <TabsTrigger value="auth">Authentication</TabsTrigger>
      </TabsList>
      
      <TabsContent value="connection" className="space-y-3">
        <div>
          <Label htmlFor="base-url">Base URL *</Label>
          <Input
            id="base-url"
            placeholder="https://api.example.com/v1"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
          />
        </div>
        <div>
          <Label htmlFor="timeout">Timeout (seconds)</Label>
          <Input
            id="timeout"
            type="number"
            placeholder="30"
            value={timeout}
            onChange={(e) => setTimeout(e.target.value)}
          />
        </div>
      </TabsContent>
      
      <TabsContent value="auth" className="space-y-3">
        <div>
          <Label htmlFor="auth-type">Authentication Type</Label>
          <select
            id="auth-type"
            className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm"
            value={authType}
            onChange={(e) => setAuthType(e.target.value as any)}
          >
            <option value="none">None</option>
            <option value="bearer">Bearer Token</option>
            <option value="api_key">API Key</option>
            <option value="basic">Basic Auth</option>
          </select>
        </div>
        
        {authType === 'bearer' && (
          <div>
            <Label htmlFor="bearer-token">Bearer Token</Label>
            <Input
              id="bearer-token"
              type="password"
              placeholder="eyJhbGciOiJIUzI1NiIs..."
              value={authToken}
              onChange={(e) => setAuthToken(e.target.value)}
            />
          </div>
        )}
        
        {authType === 'api_key' && (
          <>
            <div>
              <Label htmlFor="api-key">API Key</Label>
              <Input
                id="api-key"
                type="password"
                placeholder="your-api-key"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="api-key-header">Header Name</Label>
              <Input
                id="api-key-header"
                placeholder="X-API-Key"
                value={apiKeyHeader}
                onChange={(e) => setApiKeyHeader(e.target.value)}
              />
            </div>
          </>
        )}
        
        {authType === 'basic' && (
          <>
            <div>
              <Label htmlFor="basic-user">Username</Label>
              <Input
                id="basic-user"
                placeholder="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="basic-pass">Password</Label>
              <Input
                id="basic-pass"
                type="password"
                placeholder="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
          </>
        )}
      </TabsContent>
    </Tabs>
  )
}

function SnowflakeConfigForm({
  account, setAccount,
  warehouse, setWarehouse,
  database, setDatabase,
  schema, setSchema,
  username, setUsername,
  password, setPassword,
  role, setRole,
}: {
  account: string; setAccount: (v: string) => void
  warehouse: string; setWarehouse: (v: string) => void
  database: string; setDatabase: (v: string) => void
  schema: string; setSchema: (v: string) => void
  username: string; setUsername: (v: string) => void
  password: string; setPassword: (v: string) => void
  role: string; setRole: (v: string) => void
}) {
  return (
    <div className="space-y-3">
      <div>
        <Label htmlFor="sf-account">Account *</Label>
        <Input
          id="sf-account"
          placeholder="xy12345.us-east-1"
          value={account}
          onChange={(e) => setAccount(e.target.value)}
        />
        <p className="text-xs text-muted-foreground mt-1">Your Snowflake account identifier</p>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label htmlFor="sf-warehouse">Warehouse *</Label>
          <Input
            id="sf-warehouse"
            placeholder="COMPUTE_WH"
            value={warehouse}
            onChange={(e) => setWarehouse(e.target.value)}
          />
        </div>
        <div>
          <Label htmlFor="sf-role">Role (optional)</Label>
          <Input
            id="sf-role"
            placeholder="ACCOUNTADMIN"
            value={role}
            onChange={(e) => setRole(e.target.value)}
          />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label htmlFor="sf-database">Database *</Label>
          <Input
            id="sf-database"
            placeholder="MY_DB"
            value={database}
            onChange={(e) => setDatabase(e.target.value)}
          />
        </div>
        <div>
          <Label htmlFor="sf-schema">Schema *</Label>
          <Input
            id="sf-schema"
            placeholder="PUBLIC"
            value={schema}
            onChange={(e) => setSchema(e.target.value)}
          />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label htmlFor="sf-username">Username *</Label>
          <Input
            id="sf-username"
            placeholder="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
        </div>
        <div>
          <Label htmlFor="sf-password">Password *</Label>
          <Input
            id="sf-password"
            type="password"
            placeholder="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
      </div>
    </div>
  )
}

function BigQueryConfigForm({
  projectId, setProjectId,
  dataset, setDataset,
  credentials, setCredentials,
}: {
  projectId: string; setProjectId: (v: string) => void
  dataset: string; setDataset: (v: string) => void
  credentials: string; setCredentials: (v: string) => void
}) {
  return (
    <div className="space-y-3">
      <div>
        <Label htmlFor="bq-project">Project ID *</Label>
        <Input
          id="bq-project"
          placeholder="my-project-123456"
          value={projectId}
          onChange={(e) => setProjectId(e.target.value)}
        />
      </div>
      <div>
        <Label htmlFor="bq-dataset">Dataset *</Label>
        <Input
          id="bq-dataset"
          placeholder="my_dataset"
          value={dataset}
          onChange={(e) => setDataset(e.target.value)}
        />
      </div>
      <div>
        <Label htmlFor="bq-credentials">Service Account JSON (optional)</Label>
        <Textarea
          id="bq-credentials"
          placeholder={`{\n  "type": "service_account",\n  "project_id": "...",\n  ...\n}`}
          value={credentials}
          onChange={(e) => setCredentials(e.target.value)}
          rows={6}
          className="font-mono text-xs"
        />
        <p className="text-xs text-muted-foreground mt-1">
          Leave empty to use application default credentials
        </p>
      </div>
    </div>
  )
}
