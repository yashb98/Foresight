/**
 * Predictions Page — on-demand ML inference for a given asset
 */

import { useState } from 'react'
import { TopBar } from '@/components/layout/TopBar'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { predictAsset } from '@/api/endpoints'
import { useAuthStore } from '@/store/auth'
import { formatProbability, formatHealthScore, healthScoreColour } from '@/lib/utils'
import { Zap, BarChart2, Loader2 } from 'lucide-react'
import type { Prediction } from '@/types'

export function Predictions() {
  const [assetId, setAssetId] = useState('')
  const [prediction, setPrediction] = useState<Prediction | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')

  const tenantId = useAuthStore((s) => s.tenantId)

  const handlePredict = async () => {
    if (!assetId.trim() || !tenantId) return
    setError('')
    setIsLoading(true)
    try {
      const result = await predictAsset(tenantId, assetId.trim())
      setPrediction(result)
    } catch (err: unknown) {
      const apiErr = err as { message?: string }
      setError(apiErr?.message ?? 'Prediction failed.')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <TopBar
        title="On-Demand Predictions"
        subtitle="Run real-time ML inference for any asset"
      />
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {/* Input form */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Zap className="h-4 w-4 text-primary" />
              Run Prediction
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex gap-3">
              <Input
                placeholder="Enter Asset ID (UUID)"
                value={assetId}
                onChange={(e) => setAssetId(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handlePredict()}
                className="flex-1 font-mono"
              />
              <Button onClick={handlePredict} disabled={isLoading || !assetId.trim()}>
                {isLoading ? (
                  <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Predicting…</>
                ) : (
                  'Run Prediction'
                )}
              </Button>
            </div>
            {error && (
              <p className="mt-2 text-sm text-destructive">{error}</p>
            )}
            <p className="mt-2 text-xs text-muted-foreground">
              The model loads current sensor features from the feature store automatically.
            </p>
          </CardContent>
        </Card>

        {/* Result */}
        {prediction && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {/* Health Score */}
            <Card className="lg:col-span-1">
              <CardContent className="pt-6 flex flex-col items-center text-center">
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">
                  Health Score
                </p>
                <span className={`text-6xl font-bold ${healthScoreColour(prediction.health_score)}`}>
                  {formatHealthScore(prediction.health_score)}
                </span>
                <Badge variant={prediction.risk_level as 'critical' | 'high' | 'medium' | 'low'} className="mt-3">
                  {prediction.risk_level.toUpperCase()} RISK
                </Badge>
                <div className="mt-4 w-full space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Failure Prob. 7d</span>
                    <span className={prediction.failure_prob_7d > 0.3 ? 'text-red-400 font-medium' : 'text-foreground'}>
                      {formatProbability(prediction.failure_prob_7d)}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Failure Prob. 30d</span>
                    <span className={prediction.failure_prob_30d > 0.4 ? 'text-red-400 font-medium' : 'text-foreground'}>
                      {formatProbability(prediction.failure_prob_30d)}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Confidence</span>
                    <span className="text-muted-foreground text-xs">
                      [{formatProbability(prediction.confidence_lower)}, {formatProbability(prediction.confidence_upper)}]
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Model</span>
                    <span className="text-xs font-mono text-muted-foreground">{prediction.model_version}</span>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Top 3 Features */}
            <Card className="lg:col-span-2">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-semibold flex items-center gap-2">
                  <BarChart2 className="h-4 w-4 text-primary" />
                  Top Contributing Features
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  {prediction.top_3_features.map((feat, i) => (
                    <div key={feat.feature} className="space-y-1.5">
                      <div className="flex justify-between text-sm">
                        <span className="font-medium text-foreground capitalize">
                          {i + 1}. {feat.feature.replace(/_/g, ' ')}
                        </span>
                        <div className="flex gap-3 text-xs text-muted-foreground">
                          <span>Value: <strong className="text-foreground">{feat.value.toFixed(3)}</strong></span>
                          <span>Importance: <strong className="text-primary">{(feat.importance * 100).toFixed(1)}%</strong></span>
                        </div>
                      </div>
                      <div className="h-2 bg-muted rounded-full overflow-hidden">
                        <div
                          className="h-full bg-primary rounded-full transition-all duration-700"
                          style={{ width: `${feat.importance * 100}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
                <p className="mt-4 text-xs text-muted-foreground">
                  Feature importance scores show each feature's contribution to the failure probability estimate.
                  Asset ID: <code className="font-mono">{prediction.asset_id}</code>
                </p>
              </CardContent>
            </Card>
          </div>
        )}
      </div>
    </div>
  )
}
