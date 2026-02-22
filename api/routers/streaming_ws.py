#!/usr/bin/env python3
"""
FORESIGHT — Kafka to WebSocket Bridge
Streams real-time data from Kafka to WebSocket clients
"""

import asyncio
import json
import threading
from datetime import datetime
from kafka import KafkaConsumer
import asyncpg

from api.routers.realtime import notify_sensor_update, notify_alert_triggered
from common.config import settings
from common.logging_config import get_logger

logger = get_logger(__name__)


class KafkaWebSocketBridge:
    """
    Bridges Kafka messages to WebSocket clients.
    Runs in a background thread and pushes updates to connected dashboards.
    """
    
    def __init__(self):
        self.consumer = None
        self.running = False
        self.thread = None
    
    def start(self):
        """Start the Kafka consumer in a background thread."""
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._consume_loop, daemon=True)
        self.thread.start()
        logger.info("Kafka-WebSocket bridge started")
    
    def stop(self):
        """Stop the consumer."""
        self.running = False
        if self.consumer:
            self.consumer.close()
        logger.info("Kafka-WebSocket bridge stopped")
    
    def _consume_loop(self):
        """Main consumption loop (runs in thread)."""
        try:
            self.consumer = KafkaConsumer(
                'sensor_readings',
                bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
                value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                auto_offset_reset='latest',
                group_id='websocket-bridge',
                enable_auto_commit=True
            )
            
            logger.info("Kafka consumer connected, waiting for messages...")
            
            for message in self.consumer:
                if not self.running:
                    break
                
                try:
                    data = message.value
                    tenant_id = data.get('tenant_id')
                    
                    if tenant_id:
                        # Push to WebSocket clients
                        asyncio.run_coroutine_threadsafe(
                            notify_sensor_update(tenant_id, data),
                            asyncio.get_event_loop()
                        )
                
                except Exception as e:
                    logger.error(f"Error processing Kafka message: {e}")
        
        except Exception as e:
            logger.exception(f"Kafka consumer error: {e}")


class DatabaseChangePoller:
    """
    Polls PostgreSQL for alert changes and pushes to WebSockets.
    Alternative to triggers for simplicity.
    """
    
    def __init__(self):
        self.running = False
        self.last_alert_id = None
    
    async def start(self):
        """Start polling for database changes."""
        self.running = True
        
        while self.running:
            try:
                # Connect to PostgreSQL
                conn = await asyncpg.connect(settings.DATABASE_URL)
                
                # Query for new alerts since last check
                query = """
                    SELECT id, tenant_id, asset_id, alert_type, severity, 
                           title, metric_value, created_at
                    FROM alerts
                    WHERE created_at > NOW() - INTERVAL '5 seconds'
                    ORDER BY created_at DESC
                    LIMIT 10
                """
                
                rows = await conn.fetch(query)
                
                for row in rows:
                    alert_data = {
                        'id': str(row['id']),
                        'asset_id': str(row['asset_id']),
                        'alert_type': row['alert_type'],
                        'severity': row['severity'],
                        'title': row['title'],
                        'metric_value': float(row['metric_value']) if row['metric_value'] else None,
                        'created_at': row['created_at'].isoformat()
                    }
                    
                    await notify_alert_triggered(str(row['tenant_id']), alert_data)
                
                await conn.close()
                
                # Poll every 5 seconds
                await asyncio.sleep(5)
            
            except Exception as e:
                logger.error(f"Database poller error: {e}")
                await asyncio.sleep(10)
    
    def stop(self):
        """Stop the poller."""
        self.running = False


# Global instances
kafka_bridge = KafkaWebSocketBridge()
db_poller = DatabaseChangePoller()


def start_streaming_bridge():
    """Start all streaming bridges."""
    kafka_bridge.start()
    # Database poller is started as async task
    asyncio.create_task(db_poller.start())


def stop_streaming_bridge():
    """Stop all streaming bridges."""
    kafka_bridge.stop()
    db_poller.stop()
