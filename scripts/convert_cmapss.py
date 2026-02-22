#!/usr/bin/env python3
"""
FORESIGHT — NASA CMAPSS Data Converter
Converts CMAPSS turbofan engine degradation dataset to FORESIGHT format
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
import argparse


def convert_cmapss_to_foresight(input_file: str, output_file: str, asset_prefix: str = "ENGINE"):
    """
    Convert CMAPSS data to FORESIGHT sensor reading format.
    
    CMAPSS columns:
    1. engine_id
    2. cycle (time)
    3-5. 3 sensor readings (T2, T24, T30)
    6. T50 (temperature)
    7-8. P2, P15 (pressure)
    9. P30 (pressure)
    10-14. Nf, Nc, epr, Ps30, phi
    15-17. NRf, NRc, BPR
    18-21. farB, htBleed, Nf_dmd, PCNfR_dmd
    22. W31
    23. W32
    """
    
    # CMAPSS column names
    columns = [
        'engine_id', 'cycle',
        'sensor_1', 'sensor_2', 'sensor_3',  # T2, T24, T30
        'T50', 'P2', 'P15', 'P30',           # Temperatures & Pressures
        'Nf', 'Nc', 'epr', 'Ps30', 'phi',    # Speed & Performance
        'NRf', 'NRc', 'BPR',
        'farB', 'htBleed', 'Nf_dmd', 'PCNfR_dmd',
        'W31', 'W32'
    ]
    
    # Read CMAPSS data (space-separated)
    print(f"Reading {input_file}...")
    df = pd.read_csv(input_file, sep=' ', header=None, names=columns)
    
    # Map sensors to meaningful names
    sensor_mapping = {
        'T50': ('temperature', 'celsius'),
        'P30': ('pressure', 'bar'),
        'Nf': ('rpm', 'rpm'),
        'Nc': ('rpm_core', 'rpm'),
    }
    
    readings = []
    base_time = datetime(2024, 1, 1, 0, 0, 0)
    
    print(f"Converting {len(df)} records...")
    
    for _, row in df.iterrows():
        engine_id = int(row['engine_id'])
        cycle = int(row['cycle'])
        timestamp = base_time + timedelta(hours=cycle)
        asset_id = f"{asset_prefix}-{engine_id:03d}"
        
        # Convert each sensor
        for col, (sensor_type, unit) in sensor_mapping.items():
            if col in row:
                readings.append({
                    'timestamp': timestamp.isoformat(),
                    'tenant_id': '550e8400-e29b-41d4-a716-446655440000',
                    'asset_id': asset_id,
                    'sensor_id': f"{asset_id}-{sensor_type.upper()}",
                    'sensor_type': sensor_type,
                    'value': round(float(row[col]), 4),
                    'unit': unit,
                    'quality': 'good'
                })
    
    # Save to CSV
    output_df = pd.DataFrame(readings)
    output_df.to_csv(output_file, index=False)
    
    print(f"✅ Converted {len(readings)} sensor readings")
    print(f"📁 Saved to {output_file}")
    
    # Print summary
    assets = output_df['asset_id'].nunique()
    sensors = output_df['sensor_id'].nunique()
    time_range = output_df['timestamp'].agg(['min', 'max'])
    
    print(f"\n📊 Summary:")
    print(f"   Assets: {assets}")
    print(f"   Sensors: {sensors}")
    print(f"   Time Range: {time_range['min']} to {time_range['max']}")
    
    return output_df


def create_simple_test_data(output_file: str, num_assets: int = 5, hours: int = 24):
    """Create simple synthetic test data that mimics real sensors."""
    
    import random
    
    readings = []
    base_time = datetime(2024, 1, 15, 0, 0, 0)
    tenant_id = '550e8400-e29b-41d4-a716-446655440000'
    
    sensor_configs = {
        'temperature': {'unit': 'celsius', 'min': 60, 'max': 90, 'nominal': 75},
        'vibration': {'unit': 'mm/s', 'min': 2, 'max': 12, 'nominal': 5},
        'pressure': {'unit': 'bar', 'min': 10, 'max': 45, 'nominal': 30},
        'flow': {'unit': 'm3/h', 'min': 50, 'max': 180, 'nominal': 120},
    }
    
    print(f"Generating test data: {num_assets} assets, {hours} hours...")
    
    for asset_num in range(num_assets):
        asset_id = f"PUMP-{1000 + asset_num:04d}"
        
        # Generate readings every 5 minutes
        for minute in range(0, hours * 60, 5):
            timestamp = base_time + timedelta(minutes=minute)
            
            for sensor_type, config in sensor_configs.items():
                # Add some realistic variation
                noise = random.uniform(-2, 2)
                trend = (minute / (hours * 60)) * 5  # Slight drift over time
                value = config['nominal'] + noise + trend
                value = max(config['min'], min(config['max'], value))
                
                readings.append({
                    'timestamp': timestamp.isoformat(),
                    'tenant_id': tenant_id,
                    'asset_id': asset_id,
                    'sensor_id': f"{asset_id}-{sensor_type.upper()}",
                    'sensor_type': sensor_type,
                    'value': round(value, 3),
                    'unit': config['unit'],
                    'quality': 'good'
                })
    
    df = pd.DataFrame(readings)
    df.to_csv(output_file, index=False)
    
    print(f"✅ Generated {len(readings)} readings")
    print(f"📁 Saved to {output_file}")
    
    return df


def main():
    parser = argparse.ArgumentParser(description='Convert data to FORESIGHT format')
    parser.add_argument('--cmapss', help='Convert CMAPSS file')
    parser.add_argument('--generate', action='store_true', help='Generate synthetic test data')
    parser.add_argument('--assets', type=int, default=5, help='Number of assets (for --generate)')
    parser.add_argument('--hours', type=int, default=24, help='Hours of data (for --generate)')
    parser.add_argument('-o', '--output', default='data/processed/sensor_readings.csv', help='Output file')
    
    args = parser.parse_args()
    
    if args.cmapss:
        convert_cmapss_to_foresight(args.cmapss, args.output)
    elif args.generate:
        create_simple_test_data(args.output, args.assets, args.hours)
    else:
        # Default: generate simple test data
        create_simple_test_data(args.output, 5, 24)


if __name__ == '__main__':
    main()
