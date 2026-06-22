-- Phase 0: Control Plane Metadata Tables
-- These tables support audit, replay, rollback, dependency tracking, and graph regeneration planning.

CREATE TABLE raw_yaml_registry (
    yaml_hash STRING(64) NOT NULL,
    yaml_content STRING(MAX) NOT NULL,
    ingestion_timestamp TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
    source_system STRING(MAX),
    status STRING(50) NOT NULL -- PENDING, PROCESSED, ERROR
) PRIMARY KEY (yaml_hash);

CREATE TABLE canonical_object_types (
    object_type_id STRING(256) NOT NULL,
    yaml_hash STRING(64) NOT NULL,
    api_version STRING(50),
    kind STRING(50),
    name STRING(256) NOT NULL,
    schema_version STRING(50),
    table_name STRING(256) NOT NULL,
    primary_key_field STRING(128) NOT NULL,
    attributes JSON,
    extensions JSON,
    status STRING(50) NOT NULL, -- ACTIVE, PENDING, DEPRECATED
    last_updated TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true)
) PRIMARY KEY (object_type_id);

CREATE TABLE canonical_relationship_types (
    relationship_id STRING(256) NOT NULL,
    yaml_hash STRING(64) NOT NULL,
    api_version STRING(50),
    name STRING(256) NOT NULL,
    source_object_type_id STRING(256) NOT NULL,
    target_object_type_id STRING(256) NOT NULL,
    edge_table_name STRING(256) NOT NULL,
    attributes JSON,
    extensions JSON,
    status STRING(50) NOT NULL, -- ACTIVE, PENDING, DEPRECATED
    last_updated TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true)
) PRIMARY KEY (relationship_id);

CREATE TABLE schema_change_log (
    change_id STRING(36) NOT NULL,
    entity_id STRING(256) NOT NULL, -- Refers to object_type_id or relationship_id
    entity_type STRING(50) NOT NULL, -- OBJECT, RELATIONSHIP
    change_type STRING(50) NOT NULL, -- ADDITIVE, COMPATIBLE, BREAKING
    diff_summary JSON,
    created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true)
) PRIMARY KEY (change_id);

CREATE TABLE deployment_audit (
    deployment_id STRING(36) NOT NULL,
    deployment_type STRING(50) NOT NULL, -- RELATIONAL_DDL, GRAPH_DDL
    ddl_statement STRING(MAX) NOT NULL,
    applied_by STRING(256) NOT NULL,
    applied_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
    status STRING(50) NOT NULL, -- SUCCESS, FAILED
    error_message STRING(MAX)
) PRIMARY KEY (deployment_id);

CREATE TABLE rule_audit (
    audit_id STRING(36) NOT NULL,
    table_name STRING(256) NOT NULL,
    row_key STRING(256) NOT NULL,
    rule_id STRING(50) NOT NULL,
    status STRING(50) NOT NULL, -- PASS, FAIL
    error_message STRING(MAX),
    evaluated_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true)
) PRIMARY KEY (audit_id);
