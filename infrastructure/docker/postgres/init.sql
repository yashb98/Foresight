-- =============================================================================
-- FORESIGHT — PostgreSQL Initialisation Script
-- Creates additional databases needed by Airflow and MLflow in the same
-- PostgreSQL instance. The main 'foresight' DB is created by POSTGRES_DB env var.
-- =============================================================================

-- Airflow database
SELECT 'CREATE DATABASE airflow'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'airflow')\gexec

-- MLflow database
SELECT 'CREATE DATABASE mlflow'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'mlflow')\gexec

-- Grant all privileges to the application user
GRANT ALL PRIVILEGES ON DATABASE airflow TO foresight_user;
GRANT ALL PRIVILEGES ON DATABASE mlflow TO foresight_user;
GRANT ALL PRIVILEGES ON DATABASE foresight TO foresight_user;

\echo 'PostgreSQL init complete: foresight, airflow, mlflow databases ready.'
