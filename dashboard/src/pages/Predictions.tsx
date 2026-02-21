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
import { formatProbability, formatHealthScore, healthScoreColour } from '@/lib/utils'
import { Zap, BarChart2, Loader2, Sparkles, Brain } from 'lucide-react'
import type { Prediction } from '@/types'

export function Predictions() {
  const [assetId, setAssetId] = useState('')
  const [prediction, setPrediction] = useState<Prediction | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')

  const handlePredict = async () => {
    if (!assetId.trim()) return
    setError('')
    setIsLoading(true)
    try {
      const result = await predictAsset(assetId.trim())
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
        {/* Header card */}
        <Card className="bg-gradient-to-br from-primary/5 via-card to-muted/20">
          <CardContent className="pt-6 pb-6">
            <div className="flex items-center gap-4">
              <div className="h-12 w-12 rounded-xl bg-primary/10 flex items-center justify-center">
                <Brain className="h-6 w-6 text-primary" />
              </div>
              <div>
                <h2 className="text-lg font-semibold">ML-Powered Predictions</h2>
                <p className="text-sm text-muted-foreground">
                  Run inference on any asset to get failure probability predictions with feature explanations.
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Input form */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-primary" />
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
              <Button 
                onClick={handlePredict} 
                disabled={isLoading || !assetId.trim()}
                className="gap-2"
              >
                {isLoading ? (
                  <><Loader2 className="h-4 w-4 animate-spin" /> Predicting…</>
                ) : (
                  <><Zap className="h-4 w-4" /> Run Prediction</>
                )}
              </Button>
            </div>
            {error && (
              <p className="mt-3 text-sm text-destructive bg-destructive/10 px-3 py-2 rounded-lg">{error}</p>
            )}
            <p className="mt-3 text-xs text-muted-foreground">
              The model loads current sensor features from the feature store automatically.
            </p>
          </CardContent>
        </Card>

        {/* Result */}
        {prediction && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Health Score */}
            <Card className="lg:col-span-1 border-primary/20">
              <CardContent className="pt-6 flex flex-col items-center text-center">
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">
                  Health Score
                </p>
                <span className={`text-6xl font-bold ${healthScoreColour(prediction.health_score)}`}>
                  {formatHealthScore(prediction.health_score)}
                </span>
                <Badge 
                  variant={prediction.risk_level as 'critical' | 'high' | 'medium' | 'low'} 
                  className="mt-3 text-xs"
                >
                  {prediction.risk_level.toUpperCase()} RISK
                </Badge>
                <div className="mt-6 w-full space-y-3 text-sm">
                  <div className="flex justify-between py-2 border-b border-border/50">
                    <span className="text-muted-foreground">Failure Prob. (7d)</span>
                    <span className={prediction.failure_prob_7d > 0.3 ? 'text-red-400 font-medium' : 'text-foreground'}>
                      {formatProbability(prediction.failure_prob_7d)}
                    </span>
                  </div>
                  <div className="flex justify-between py-2 border-b border-border/50">
                    <span className="text-muted-foreground">Failure Prob. (30d)</span>
                    <span className={prediction.failure_prob_30d > 0.4 ? 'text-red-400 font-medium' : 'text-foreground'}>
                      {formatProbability(prediction.failure_prob_30d)}
                    </span>
                  </div>
                  <div className="flex justify-between py-2 border-b border-border/50">
                    <span className="text-muted-foreground">Confidence Interval</span>
                    <span className="text-muted-foreground text-xs">
                      [{formatProbability(prediction.confidence_lower)}, {formatProbability(prediction.confidence_upper)}]
                    </span>
                  </div>
                  <div className="flex justify-between py-2">
                    <span className="text-muted-foreground">Model Version</span>
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
                <div className="space-y-5">
                  {prediction.top_3_features.map((feat, i) => (
                    <div key={feat.feature} className="space-y-2">
                      <div className="flex justify-between items-center">
                        <span className="font-medium text-sm text-foreground capitalize">
                          {i + 1}. {feat.feature.replace(/_/g, ' ')}
                        </span>
                        <div className="flex gap-4 text-xs">
                          <span className="text-muted-foreground">
                            Value: <strong className="text-foreground">{feat.value.toFixed(3)}</strong>
                          </span>
                          <span className="text-muted-foreground">
                            Importance: <strong className="text-primary">{(feat.importance * 100).toFixed(1)}%</strong>
                          </span>
                        </div>
                      </div>
                      <div className="h-2.5 bg-muted rounded-full overflow-hidden">
                        <div
                          className="h-full bg-gradient-to-r from-primary to-primary/70 rounded-full transition-all duration-700"
                          style={{ width: `${feat.importance * 100}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
                <div className="mt-6 p-3 rounded-lg bg-muted/30">
                  <p className="text-xs text-muted-foreground">
                    <strong>Explanation:</strong> Feature importance scores show each feature's contribution 
                    to the failure probability estimate. Higher importance values indicate stronger influence 
                    on the prediction outcome.
                  </p>
                  <p className="text-xs text-muted-foreground mt-2">
                    Asset ID: <code className="font-mono text-foreground">{prediction.asset_id}</code>
                  </p>
                </div>
              </CardContent>
            </Card>
          </div>
        )}
      </div>
    </div>
  )
}
