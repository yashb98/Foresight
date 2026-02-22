# FORESIGHT — Real-time Dashboard Guide

How to enable live updates when new data arrives.

---

## 🎯 Problem: Why No Real-time Updates?

### Current Architecture (Polling)
```
Dashboard → API → Database
    ↑___________↓
   (Every 30 seconds)
```

The dashboard asks for data every 30 seconds. It doesn't know when new data arrives.

---

## ✅ Solution: WebSockets + Kafka Bridge

### New Architecture (Real-time)
```
Sensor Data → Kafka → Spark → MongoDB
                  ↓
           WebSocket Bridge
                  ↓
            Dashboard (Live)
```

When new data arrives, it's **pushed** to the dashboard immediately.

---

## 🚀 How to Enable Real-time Updates

### Step 1: Start Services

```bash
# Start Docker (if not running)
open -a Docker

# Start all services
./scripts/start.sh

# Wait for services to be ready
docker-compose ps
```

### Step 2: Verify WebSocket Support

The API now includes WebSocket endpoints. Check they're available:

```bash
# Health check
curl http://localhost:8000/health

# Should show: {"status": "healthy"}
```

### Step 3: Test Real-time Dashboard

Open the test dashboard in your browser:

```bash
open http://localhost:8000/static/realtime_test.html
```

Or directly:
```
http://localhost:8000/static/realtime_test.html
```

Click **"Connect"** to start receiving real-time data.

---

## 📡 WebSocket API Reference

### Connection URL
```
ws://localhost:8000/ws/dashboard/{tenant_id}?token=JWT_TOKEN
```

### Example Connection
```javascript
const ws = new WebSocket(
    'ws://localhost:8000/ws/dashboard/550e8400-e29b-41d4-a716-446655440000?token=eyJhbG...'
);

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log('Received:', data);
};
```

### Message Types (Received)

| Type | Data | Description |
|------|------|-------------|
| `sensor_update` | `{asset_id, sensor_type, value, unit}` | New sensor reading |
| `alert_triggered` | `{id, asset_id, title, severity}` | New alert generated |
| `health_update` | `{asset_id, score, risk_level}` | Health score changed |
| `refresh` | - | Request full dashboard refresh |
| `connected` | `{message}` | Connection successful |
| `heartbeat` | `{timestamp}` | Keep-alive ping |

### Message Types (Send)

```javascript
// Subscribe to channels
ws.send(JSON.stringify({
    type: 'subscribe',
    channels: ['sensor_data', 'alerts', 'health_scores']
}));

// Ping (keep connection alive)
ws.send(JSON.stringify({ type: 'ping' }));
```

---

## 🔄 How It Works

### Data Flow

```
1. New CSV uploaded
   ↓
2. sensor_ingestor.py sends to Kafka
   ↓
3. Spark Streaming processes
   ↓
4. Kafka-WebSocket Bridge detects
   ↓
5. Pushes to all connected dashboards
```

### Components

| Component | File | Purpose |
|-----------|------|---------|
| WebSocket Router | `api/routers/realtime.py` | Manages connections |
| Kafka Bridge | `api/routers/streaming_ws.py` | Streams Kafka to WebSockets |
| Test Dashboard | `dashboard/public/realtime_test.html` | Live demo UI |

---

## 🧪 Testing Real-time Updates

### Test 1: Sensor Data Streaming

```bash
# Terminal 1: Start watching the test dashboard
open http://localhost:8000/static/realtime_test.html
# Click "Connect"

# Terminal 2: Generate and ingest data
python scripts/convert_cmapss.py --generate --assets 3 --hours 1
python ingestion/sensor_ingestor.py data/processed/sensor_readings.csv
```

**Expected:** Dashboard updates live as each sensor reading arrives.

---

### Test 2: Alert Notifications

```bash
# Create an alert rule that will trigger
python scripts/test_api.py

# Or use curl:
curl -X POST http://localhost:8000/alerts/550e8400-e29b-41d4-a716-446655440000/rules \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Alert",
    "metric": "temperature",
    "operator": ">",
    "threshold_value": 50,
    "severity": "critical"
  }'
```

**Expected:** When sensor data exceeds threshold, alert appears instantly.

---

### Test 3: Multiple Dashboard Clients

Open the test page in 3 browser tabs:
- Tab 1: Chrome
- Tab 2: Firefox  
- Tab 3: Safari

Connect all to the same tenant. When you ingest data, **all 3 update simultaneously**.

---

## 🔌 Integrating with React Dashboard

### Option 1: WebSocket Hook

```typescript
// hooks/useWebSocket.ts
import { useEffect, useState, useCallback } from 'react';

export function useWebSocket(tenantId: string, token: string) {
    const [connected, setConnected] = useState(false);
    const [lastMessage, setLastMessage] = useState(null);
    const [socket, setSocket] = useState<WebSocket | null>(null);

    useEffect(() => {
        const ws = new WebSocket(
            `ws://localhost:8000/ws/dashboard/${tenantId}?token=${token}`
        );

        ws.onopen = () => {
            setConnected(true);
            ws.send(JSON.stringify({
                type: 'subscribe',
                channels: ['sensor_data', 'alerts', 'health_scores']
            }));
        };

        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            setLastMessage(data);
        };

        ws.onclose = () => setConnected(false);
        
        setSocket(ws);

        return () => ws.close();
    }, [tenantId, token]);

    return { connected, lastMessage, socket };
}
```

### Option 2: Real-time Component

```typescript
// components/RealtimeAlerts.tsx
import { useEffect } from 'react';
import { useWebSocket } from '../hooks/useWebSocket';
import { toast } from 'sonner'; // or your toast library

export function RealtimeAlerts({ tenantId, token }) {
    const { lastMessage } = useWebSocket(tenantId, token);

    useEffect(() => {
        if (!lastMessage) return;

        switch (lastMessage.type) {
            case 'alert_triggered':
                toast.error(`Alert: ${lastMessage.data.title}`, {
                    description: `Severity: ${lastMessage.data.severity}`
                });
                break;
                
            case 'sensor_update':
                // Update sensor charts
                console.log('New reading:', lastMessage.data);
                break;
                
            case 'health_update':
                // Update health score displays
                console.log('Health update:', lastMessage.data);
                break;
                
            case 'refresh':
                // Trigger full dashboard refresh
                window.location.reload();
                break;
        }
    }, [lastMessage]);

    return null; // Invisible component
}
```

### Option 3: Polling Fallback (Hybrid)

For production, use both:

```typescript
function useRealtimeData(tenantId: string, token: string) {
    // WebSocket for real-time
    const { connected, lastMessage } = useWebSocket(tenantId, token);
    
    // Polling as fallback
    const { data, refetch } = useQuery({
        queryKey: ['dashboard', tenantId],
        queryFn: () => fetchDashboardData(tenantId, token),
        refetchInterval: connected ? false : 30000, // Poll only if WS disconnected
    });

    // Merge real-time updates
    useEffect(() => {
        if (lastMessage?.type === 'sensor_update') {
            // Update local cache
            queryClient.setQueryData(['dashboard', tenantId], (old) => ({
                ...old,
                latestReading: lastMessage.data
            }));
        }
    }, [lastMessage]);

    return { data, connected };
}
```

---

## 📊 Comparison: Polling vs WebSockets

| Feature | Polling | WebSockets |
|---------|---------|------------|
| **Latency** | 5-30 seconds | <100ms |
| **Server Load** | High (constant requests) | Low (event-driven) |
| **Battery Usage** | High | Low |
| **Complexity** | Simple | Medium |
| **Reliability** | High | Medium (needs reconnection) |
| **Scalability** | Poor | Excellent |

---

## 🔧 Configuration Options

### Environment Variables

```bash
# .env

# WebSocket settings
WS_HEARTBEAT_INTERVAL=30
WS_MAX_CONNECTIONS_PER_TENANT=100

# Kafka bridge settings
KAFKA_BRIDGE_ENABLED=true
KAFKA_BRIDGE_BATCH_SIZE=100
KAFKA_BRIDGE_FLUSH_INTERVAL=1000
```

### Disable Real-time (if needed)

```python
# In api/main.py, comment out:
# from api.routers import realtime
# app.include_router(realtime.router)
# start_streaming_bridge()
```

---

## 🐛 Troubleshooting

### Issue: WebSocket connection fails

```bash
# Check if API is running
curl http://localhost:8000/health

# Check WebSocket endpoint exists
curl -I http://localhost:8000/ws/dashboard/test

# Should return: HTTP/1.1 400 Bad Request (expected, needs WS upgrade)
```

### Issue: No real-time updates

```bash
# Check Kafka bridge is running
docker-compose logs api | grep -i "streaming bridge"

# Should show: "Streaming bridge started"

# Check Kafka has data
docker-compose exec kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic sensor_readings \
  --from-beginning
```

### Issue: Dashboard not updating

Open browser console (F12) and check:
```javascript
// Should show WebSocket connected
const ws = new WebSocket('ws://localhost:8000/ws/dashboard/TENANT_ID?token=TOKEN');
ws.onmessage = (e) => console.log('Received:', e.data);
```

---

## 🎓 Summary

| What | Before | After |
|------|--------|-------|
| **Data Updates** | Every 30 seconds (polling) | Real-time (WebSocket) |
| **Alert Latency** | 30 seconds | <100ms |
| **Server Load** | 1000s of HTTP requests | Few WebSocket connections |
| **User Experience** | Stale data | Live streaming data |

---

## 🚀 Quick Start

```bash
# 1. Start everything
./scripts/start.sh

# 2. Open real-time dashboard
open http://localhost:8000/static/realtime_test.html

# 3. Click "Connect"

# 4. In another terminal, ingest data
python scripts/seed_data.py --assets 5 --readings-hours 1

# 5. Watch dashboard update live! 🎉
```

---

**Your dashboard is now REAL-TIME!** ⚡
