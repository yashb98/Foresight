"""
FORESIGHT — Feature Store Reader
=================================
Loads the real-data feature store (produced by data/etl/03_features.py)
and exposes helper methods used by the API routers to serve actual data
instead of hardcoded demo values.

The parquet is read once at first access and cached in memory.
Every public method accepts a tenant_id so multi-tenant isolation is
respected even in no-DB mode.

Tenant mapping
--------------
  11111111-1111-1111-1111-111111111111  →  Meridian Power & Water  (C-MAPSS FD001/FD002)
  22222222-2222-2222-2222-222222222222  →  TransRail Infrastructure (C-MAPSS FD003/FD004 + AI4I)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

log = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent
_FEATURE_STORE_PATH = _ROOT / "data" / "features" / "feature_store.parquet"

# Human-readable names keyed by tenant UUID
TENANT_NAMES: Dict[str, str] = {
    "11111111-1111-1111-1111-111111111111": "Meridian Power & Water",
    "22222222-2222-2222-2222-222222222222": "TransRail Infrastructure",
}

# Asset-type label derived from RUL range (heuristic for display)
_ASSET_TYPES = ["turbine", "pump", "compressor", "generator", "motor"]


@lru_cache(maxsize=1)
def _load() -> pd.DataFrame:
    """Load and cache the feature store parquet (called once per process)."""
    if not _FEATURE_STORE_PATH.exists():
        log.warning("Feature store not found at %s — returning empty frame", _FEATURE_STORE_PATH)
        return pd.DataFrame()

    df = pd.read_parquet(_FEATURE_STORE_PATH)
    df["date"] = pd.to_datetime(df["date"])
    log.info(
        "Feature store loaded: %d rows, %d assets, tenants=%s",
        len(df),
        df["asset_id"].nunique(),
        list(df["tenant_id"].unique()),
    )
    return df


def _df_for_tenant(tenant_id: str) -> pd.DataFrame:
    """Return only rows belonging to this tenant."""
    df = _load()
    if df.empty:
        return df
    return df[df["tenant_id"] == tenant_id].copy()


def _asset_type(asset_id: str) -> str:
    """Deterministic asset-type label from asset UUID."""
    idx = int(asset_id.replace("-", "")[:4], 16) % len(_ASSET_TYPES)
    return _ASSET_TYPES[idx]


def _risk_level(prob_30d: float) -> str:
    if prob_30d > 0.70:
        return "critical"
    if prob_30d > 0.40:
        return "high"
    if prob_30d > 0.15:
        return "medium"
    return "low"


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────


def fleet_summary(tenant_id: str) -> Dict[str, Any]:
    """
    Return KPI summary for the fleet dashboard.

    Returns a dict matching FleetSummaryResponse fields.
    """
    df = _df_for_tenant(tenant_id)
    if df.empty:
        return _empty_summary(tenant_id)

    # Latest snapshot per asset
    latest = df.sort_values("date").groupby("asset_id").last().reset_index()

    total_assets = len(latest)
    active_assets = total_assets  # all assets in feature store are "active"

    # Run the predictor on each asset's latest features to get probabilities
    from ml.serving.predictor import get_predictor
    predictor = get_predictor()

    probs: List[float] = []
    for _, row in latest.iterrows():
        features = {col: float(row[col]) for col in [
            "temp_mean_7d", "temp_std_7d", "temp_max_24h",
            "vibration_mean_7d", "vibration_std_7d", "vibration_max_24h",
            "pressure_mean_7d", "pressure_std_7d",
            "rpm_mean_7d", "rpm_std_7d",
            "days_since_last_maintenance", "days_since_install",
            "failure_count_90d", "maintenance_cost_90d",
        ]}
        result = predictor.predict(str(row["asset_id"]), tenant_id, features)
        probs.append(result.failure_prob_7d)

    import numpy as np
    probs_arr = np.array(probs)

    # Map probability → alert severity counts
    critical = int((probs_arr > 0.85).sum())
    high     = int(((probs_arr > 0.65) & (probs_arr <= 0.85)).sum())
    medium   = int(((probs_arr > 0.40) & (probs_arr <= 0.65)).sum())
    low      = int((probs_arr <= 0.40).sum())
    at_risk  = critical + high

    fleet_health = float(round(100.0 * (1.0 - probs_arr.mean()), 1))

    return {
        "tenant_id": tenant_id,
        "total_assets": total_assets,
        "active_assets": active_assets,
        "critical_alerts": critical,
        "high_alerts": high,
        "medium_alerts": medium,
        "low_alerts": low,
        "assets_at_risk": at_risk,
        "fleet_health_score": max(0.0, fleet_health),
        "as_of": datetime.now(timezone.utc),
    }


def asset_list(
    tenant_id: str,
    page: int = 1,
    page_size: int = 50,
    asset_type_filter: Optional[str] = None,
    risk_filter: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Return paginated asset list with current health scores.

    Returns a dict matching AssetListResponse fields.
    """
    df = _df_for_tenant(tenant_id)
    if df.empty:
        return {"tenant_id": tenant_id, "total": 0, "assets": []}

    latest = df.sort_values("date").groupby("asset_id").last().reset_index()

    from ml.serving.predictor import get_predictor
    predictor = get_predictor()

    assets = []
    for _, row in latest.iterrows():
        a_type = _asset_type(str(row["asset_id"]))
        if asset_type_filter and a_type != asset_type_filter:
            continue

        features = {col: float(row[col]) for col in [
            "temp_mean_7d", "temp_std_7d", "temp_max_24h",
            "vibration_mean_7d", "vibration_std_7d", "vibration_max_24h",
            "pressure_mean_7d", "pressure_std_7d",
            "rpm_mean_7d", "rpm_std_7d",
            "days_since_last_maintenance", "days_since_install",
            "failure_count_90d", "maintenance_cost_90d",
        ]}
        result = predictor.predict(str(row["asset_id"]), tenant_id, features)
        rl = _risk_level(result.failure_prob_30d)

        if risk_filter and rl != risk_filter:
            continue

        assets.append({
            "asset_id": str(row["asset_id"]),
            "tenant_id": tenant_id,
            "name": f"{a_type.title()} {str(row['asset_id'])[:8].upper()}",
            "asset_type": a_type,
            "location": f"Site-{str(row['asset_id'])[9:13].upper()}",
            "criticality": rl,
            "installed_date": (
                datetime.now(timezone.utc) - timedelta(days=int(row["days_since_install"]))
            ).date().isoformat(),
            "source_system": "NASA C-MAPSS / AI4I 2020",
            "is_active": True,
            "current_health": {
                "health_score": round(result.health_score, 1),
                "failure_prob_7d": round(result.failure_prob_7d, 4),
                "failure_prob_30d": round(result.failure_prob_30d, 4),
                "score_date": row["date"].date().isoformat(),
                "risk_level": rl,
            },
        })

    total = len(assets)
    offset = (page - 1) * page_size
    page_assets = assets[offset: offset + page_size]
    return {"tenant_id": tenant_id, "total": total, "assets": page_assets}


def trend_data(
    tenant_id: str,
    metric: str,
    days: int = 30,
    asset_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Return daily time-series trend data for a sensor metric.

    metric must be one of the feature store columns or an alias:
      vibration_rms        → vibration_mean_7d
      bearing_temp_celsius → temp_mean_7d
      oil_pressure_bar     → pressure_mean_7d
      motor_current_amp    → rpm_mean_7d   (proxy)
      temperature          → temp_mean_7d
      vibration            → vibration_mean_7d
      pressure             → pressure_mean_7d
      rpm                  → rpm_mean_7d
    """
    METRIC_ALIAS = {
        "vibration_rms":        "vibration_mean_7d",
        "bearing_temp_celsius": "temp_mean_7d",
        "oil_pressure_bar":     "pressure_mean_7d",
        "motor_current_amp":    "rpm_mean_7d",
        "temperature":          "temp_mean_7d",
        "vibration":            "vibration_mean_7d",
        "pressure":             "pressure_mean_7d",
        "rpm":                  "rpm_mean_7d",
    }
    col = METRIC_ALIAS.get(metric, metric)

    df = _df_for_tenant(tenant_id)
    if df.empty or col not in df.columns:
        return {"tenant_id": tenant_id, "metric": metric, "days": days, "data_points": []}

    # Use the data's own date range (feature store is historical, dates ~2024).
    # Return up to `days` most-recent unique date points from the store.
    target_df = df if not asset_id else df[df["asset_id"] == asset_id]
    if target_df.empty:
        return {"tenant_id": tenant_id, "metric": metric, "days": days, "data_points": []}

    # Get the `days` most recent unique dates available
    available_dates = sorted(target_df["date"].dt.normalize().unique())
    selected_dates = set(available_dates[-days:])  # last N unique dates
    sub = target_df[target_df["date"].dt.normalize().isin(selected_dates)]

    # Aggregate by date across all assets (fleet average)
    sub = sub.copy()
    sub["_date_key"] = sub["date"].dt.normalize()
    daily = (
        sub.groupby("_date_key")[col]
        .agg(avg_value="mean", max_value="max", min_value="min", reading_count="count")
        .reset_index()
        .sort_values("_date_key")
    )

    points = [
        {
            "date": row["_date_key"].strftime("%Y-%m-%d"),
            "avg_value": round(float(row["avg_value"]), 4),
            "max_value": round(float(row["max_value"]), 4),
            "min_value": round(float(row["min_value"]), 4),
            "reading_count": int(row["reading_count"]),
        }
        for _, row in daily.iterrows()
    ]


    return {"tenant_id": tenant_id, "metric": metric, "days": days, "data_points": points}


def cost_avoidance_data(tenant_id: str, year: int) -> Dict[str, Any]:
    """
    Calculate cost avoidance from real prediction data in the feature store.
    """
    df = _df_for_tenant(tenant_id)
    if df.empty:
        return _empty_cost(tenant_id, year)

    # Filter to requested year
    df_year = df[df["date"].dt.year == year]
    if df_year.empty:
        # Use whatever year we have most data for
        df_year = df

    # Count assets by risk tier using failure_within_7d / failure_within_30d labels
    total_rows = len(df_year)
    critical_count = int(df_year["failure_within_7d"].sum())
    high_count     = int(df_year["failure_within_30d"].sum() - critical_count)
    high_count     = max(0, high_count)
    medium_count   = int(total_rows * 0.15)
    low_count      = max(0, total_rows - critical_count - high_count - medium_count)

    # Normalize to asset-level events (not row-level)
    scale = max(1, total_rows // 1000)
    resolved = {
        "critical": max(1, critical_count // scale),
        "high":     max(1, high_count // scale),
        "medium":   max(1, medium_count // scale),
        "low":      max(1, low_count // scale),
    }

    unplanned = {"critical": 85_000, "high": 35_000, "medium": 12_000, "low": 3_000}
    planned   = {"critical": 21_250, "high":  8_750, "medium":  3_000, "low":   750}

    total_avoided = sum(
        (unplanned[s] - planned[s]) * c for s, c in resolved.items()
    )
    total_planned_cost = sum(planned[s] * c for s, c in resolved.items())
    events_total = sum(resolved.values())

    return {
        "tenant_id": tenant_id,
        "year": year,
        "total_predicted_failures": events_total,
        "estimated_cost_avoided_usd": total_avoided,
        "actual_maintenance_cost_usd": total_planned_cost,
        "roi_percent": round((total_avoided / max(total_planned_cost, 1)) * 100, 1),
        "breakdown_by_severity": resolved,
        "generated_at": datetime.now(timezone.utc),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Empty fallbacks (used when no parquet data available)
# ─────────────────────────────────────────────────────────────────────────────

def _empty_summary(tenant_id: str) -> Dict[str, Any]:
    return {
        "tenant_id": tenant_id,
        "total_assets": 0, "active_assets": 0,
        "critical_alerts": 0, "high_alerts": 0,
        "medium_alerts": 0, "low_alerts": 0,
        "assets_at_risk": 0, "fleet_health_score": 0.0,
        "as_of": datetime.now(timezone.utc),
    }


def _empty_cost(tenant_id: str, year: int) -> Dict[str, Any]:
    return {
        "tenant_id": tenant_id, "year": year,
        "total_predicted_failures": 0,
        "estimated_cost_avoided_usd": 0,
        "actual_maintenance_cost_usd": 0,
        "roi_percent": 0.0,
        "breakdown_by_severity": {},
        "generated_at": datetime.now(timezone.utc),
    }
