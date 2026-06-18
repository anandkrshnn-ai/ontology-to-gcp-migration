# Lighthouse Pilot: Logistics Enterprise SLA Monitor

This pilot proves that the V7 Migration Framework can successfully replicate Palantir's ultra-low latency operational dashboards (Slate/Contour) using native GCP streaming architecture.

## Architecture

1. **Telemetry Generator**: Simulates high-throughput logistics events (package scanned, vehicle delayed, delivered).
2. **Cloud Pub/Sub**: Ingests telemetry securely and durably (`logistics-telemetry` topic).
3. **Cloud Dataflow (Apache Beam)**: Processes the stream, applying business logic to calculate SLA breaches in real-time (e.g., packages delayed over 2 hours).
4. **Cloud Bigtable**: Stores the highly transient package state. 
    - **Row Key Design**: `<hash(package_id)>#<package_id>#<timestamp>` to prevent hotspotting at enterprise scale.
5. **Streamlit Dashboard**: A fast, read-heavy operational UI serving as the direct replacement for Palantir Slate.

## How to Run the Pilot Locally (Mocked)

**1. Install Dependencies**
```bash
pip install apache-beam[gcp] google-cloud-pubsub google-cloud-bigtable streamlit faker
```

**2. Start the Telemetry Generator**
```bash
python generate_telemetry.py --local
```

**3. Run the Streaming Pipeline (DirectRunner)**
```bash
python streaming_pipeline.py --runner DirectRunner
```

**4. Launch the SLA Dashboard**
```bash
streamlit run sla_dashboard.py
```
