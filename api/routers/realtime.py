# =============================================================================
# FORESIGHT API — Real-time WebSocket Endpoints
# Live dashboard updates via WebSockets
# =============================================================================

import asyncio
import json
from typing import Dict, Set
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
from starlette.websockets import WebSocketState

from api.dependencies import get_current_user, decode_token
from common.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/ws", tags=["WebSocket"])

# =============================================================================
# Connection Manager for WebSockets
# =============================================================================

class ConnectionManager:
    """Manages WebSocket connections by tenant."""
    
    def __init__(self):
        # tenant_id -> set of WebSocket connections
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        # Track connection metadata
        self.connection_info: Dict[WebSocket, dict] = {}
    
    async def connect(self, websocket: WebSocket, tenant_id: str, user_info: dict):
        """Accept and store a new WebSocket connection."""
        await websocket.accept()
        
        if tenant_id not in self.active_connections:
            self.active_connections[tenant_id] = set()
        
        self.active_connections[tenant_id].add(websocket)
        self.connection_info[websocket] = {
            "tenant_id": tenant_id,
            "user_id": user_info.get("user_id"),
            "email": user_info.get("email"),
            "connected_at": datetime.utcnow().isoformat()
        }
        
        logger.info(f"WebSocket connected: {user_info.get('email')} for tenant {tenant_id}")
    
    def disconnect(self, websocket: WebSocket, tenant_id: str):
        """Remove a WebSocket connection."""
        if tenant_id in self.active_connections:
            self.active_connections[tenant_id].discard(websocket)
            
            # Clean up empty tenant sets
            if not self.active_connections[tenant_id]:
                del self.active_connections[tenant_id]
        
        self.connection_info.pop(websocket, None)
        logger.info(f"WebSocket disconnected for tenant {tenant_id}")
    
    async def broadcast_to_tenant(self, tenant_id: str, message: dict):
        """Broadcast a message to all connections for a tenant."""
        if tenant_id not in self.active_connections:
            return
        
        # Convert message to JSON
        message_json = json.dumps(message, default=str)
        
        # Send to all connected clients for this tenant
        disconnected = []
        for connection in self.active_connections[tenant_id]:
            try:
                if connection.client_state == WebSocketState.CONNECTED:
                    await connection.send_text(message_json)
            except Exception as e:
                logger.warning(f"Failed to send WebSocket message: {e}")
                disconnected.append(connection)
        
        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect(conn, tenant_id)
    
    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """Send a message to a specific client."""
        try:
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.send_text(json.dumps(message, default=str))
        except Exception as e:
            logger.warning(f"Failed to send personal message: {e}")
    
    def get_connection_count(self, tenant_id: str = None) -> int:
        """Get number of active connections."""
        if tenant_id:
            return len(self.active_connections.get(tenant_id, set()))
        return sum(len(conns) for conns in self.active_connections.values())


# Global connection manager instance
manager = ConnectionManager()


# =============================================================================
# WebSocket Endpoints
# =============================================================================

@router.websocket("/dashboard/{tenant_id}")
async def dashboard_websocket(websocket: WebSocket, tenant_id: str):
    """
    WebSocket endpoint for real-time dashboard updates.
    
    Connection URL: ws://localhost:8000/ws/dashboard/{tenant_id}?token=JWT_TOKEN
    
    Messages received from client:
    - {"type": "subscribe", "channels": ["alerts", "sensor_data", "health_scores"]}
    - {"type": "ping"}
    
    Messages sent to client:
    - {"type": "sensor_update", "data": {...}}
    - {"type": "alert_triggered", "data": {...}}
    - {"type": "health_update", "data": {...}}
    - {"type": "pong"}
    """
    # Verify token from query parameter
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="Missing authentication token")
        return
    
    payload = decode_token(token)
    if not payload:
        await websocket.close(code=4002, reason="Invalid token")
        return
    
    # Verify tenant access
    if str(payload.get("tenant_id")) != tenant_id:
        await websocket.close(code=4003, reason="Tenant access denied")
        return
    
    # Accept connection
    await manager.connect(websocket, tenant_id, payload)
    
    try:
        # Send initial connection success message
        await manager.send_personal_message({
            "type": "connected",
            "message": "Successfully connected to real-time dashboard",
            "tenant_id": tenant_id,
            "timestamp": datetime.utcnow().isoformat()
        }, websocket)
        
        # Keep connection alive and handle client messages
        while True:
            try:
                # Wait for messages from client (with timeout)
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=30.0
                )
                
                # Parse client message
                try:
                    message = json.loads(data)
                    msg_type = message.get("type", "unknown")
                    
                    if msg_type == "ping":
                        await manager.send_personal_message({
                            "type": "pong",
                            "timestamp": datetime.utcnow().isoformat()
                        }, websocket)
                    
                    elif msg_type == "subscribe":
                        channels = message.get("channels", [])
                        await manager.send_personal_message({
                            "type": "subscribed",
                            "channels": channels,
                            "message": f"Subscribed to: {', '.join(channels)}"
                        }, websocket)
                    
                    else:
                        await manager.send_personal_message({
                            "type": "error",
                            "message": f"Unknown message type: {msg_type}"
                        }, websocket)
                
                except json.JSONDecodeError:
                    await manager.send_personal_message({
                        "type": "error",
                        "message": "Invalid JSON format"
                    }, websocket)
            
            except asyncio.TimeoutError:
                # Send heartbeat to keep connection alive
                await manager.send_personal_message({
                    "type": "heartbeat",
                    "timestamp": datetime.utcnow().isoformat()
                }, websocket)
    
    except WebSocketDisconnect:
        manager.disconnect(websocket, tenant_id)
    except Exception as e:
        logger.exception(f"WebSocket error: {e}")
        manager.disconnect(websocket, tenant_id)


@router.websocket("/alerts/{tenant_id}")
async def alerts_websocket(websocket: WebSocket, tenant_id: str):
    """Dedicated WebSocket endpoint for real-time alerts only."""
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="Missing authentication token")
        return
    
    payload = decode_token(token)
    if not payload or str(payload.get("tenant_id")) != tenant_id:
        await websocket.close(code=4003, reason="Access denied")
        return
    
    await manager.connect(websocket, tenant_id, payload)
    
    try:
        await manager.send_personal_message({
            "type": "connected",
            "channel": "alerts",
            "message": "Subscribed to real-time alerts"
        }, websocket)
        
        # Keep connection open
        while True:
            await asyncio.sleep(60)  # Just keep alive
    
    except WebSocketDisconnect:
        manager.disconnect(websocket, tenant_id)


# =============================================================================
# HTTP Endpoints for Broadcasting
# =============================================================================

@router.post("/{tenant_id}/broadcast")
async def broadcast_message(
    tenant_id: str,
    message: dict,
    current_user: dict = Depends(get_current_user)
):
    """
    Broadcast a message to all connected dashboard clients.
    Used internally by other services to push updates.
    """
    if str(current_user["tenant_id"]) != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    await manager.broadcast_to_tenant(tenant_id, message)
    return {"status": "broadcasted", "connections": manager.get_connection_count(tenant_id)}


@router.get("/{tenant_id}/connections")
async def get_connection_stats(
    tenant_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get WebSocket connection statistics."""
    if str(current_user["tenant_id"]) != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return {
        "tenant_id": tenant_id,
        "active_connections": manager.get_connection_count(tenant_id),
        "total_connections": manager.get_connection_count()
    }


# =============================================================================
# Helper Functions for Other Modules
# =============================================================================

async def notify_sensor_update(tenant_id: str, sensor_data: dict):
    """Notify all dashboard clients of new sensor data."""
    await manager.broadcast_to_tenant(tenant_id, {
        "type": "sensor_update",
        "timestamp": datetime.utcnow().isoformat(),
        "data": sensor_data
    })


async def notify_alert_triggered(tenant_id: str, alert_data: dict):
    """Notify all dashboard clients of a new alert."""
    await manager.broadcast_to_tenant(tenant_id, {
        "type": "alert_triggered",
        "timestamp": datetime.utcnow().isoformat(),
        "data": alert_data
    })


async def notify_health_update(tenant_id: str, health_data: dict):
    """Notify all dashboard clients of health score updates."""
    await manager.broadcast_to_tenant(tenant_id, {
        "type": "health_update",
        "timestamp": datetime.utcnow().isoformat(),
        "data": health_data
    })


async def notify_dashboard_refresh(tenant_id: str):
    """Request all dashboards to refresh their data."""
    await manager.broadcast_to_tenant(tenant_id, {
        "type": "refresh",
        "timestamp": datetime.utcnow().isoformat(),
        "message": "New data available, please refresh"
    })
