import streamlit as st
import pandas as pd
import random
import time
from datetime import datetime

# Streamlit Page Config
st.set_page_config(page_title="Logistics SLA Monitor", layout="wide", page_icon="📦")

def fetch_live_data_mock():
    """Simulates fetching the latest row states from Bigtable (Sub-10ms query)."""
    # Simulate a fast Bigtable query latency
    time.sleep(0.01) 
    
    data = []
    for i in range(15):
        pkg_id = f"PKG-{1000 + i}"
        
        # Artificial probabilities
        status_choices = ["IN_TRANSIT", "AT_HUB", "DELAYED", "DELIVERED"]
        status = random.choices(status_choices, weights=[0.4, 0.3, 0.2, 0.1])[0]
        
        sla_breach = "Yes" if status == "DELAYED" else "No"
        delay_reason = random.choice(["WEATHER", "TRAFFIC", "CUSTOMS", "VEHICLE_BREAKDOWN"]) if status == "DELAYED" else "-"
        
        data.append({
            "Package ID": pkg_id,
            "Last Update": datetime.utcnow().strftime("%H:%M:%S UTC"),
            "Status": status,
            "SLA Breach": sla_breach,
            "Delay Reason": delay_reason
        })
    return pd.DataFrame(data)

st.title("📦 Live Logistics SLA Monitor")
st.markdown("### Replacing Palantir Slate / Contour with GCP Native Tooling")
st.markdown("**Architecture**: `Pub/Sub -> Dataflow (Beam) -> Bigtable -> UI` | **Target Latency**: `< 50ms`")

# Key Metrics
st.header("Real-Time Network Status")
col1, col2, col3 = st.columns(3)

df = fetch_live_data_mock()

active_packages = len(df[df["Status"] != "DELIVERED"])
breaches = len(df[df["SLA Breach"] == "Yes"])
latency = f"{random.randint(8, 14)} ms"

col1.metric("Active Packages in Network", active_packages)
col2.metric("Critical SLA Breaches", breaches, delta=breaches, delta_color="inverse")
col3.metric("Bigtable P99 Read Latency", latency)

st.divider()

st.subheader("🔴 Active SLA Breaches (Action Required)")
breach_df = df[df["SLA Breach"] == "Yes"]
if breach_df.empty:
    st.success("No active SLA breaches.")
else:
    st.dataframe(breach_df, use_container_width=True)

st.subheader("🟢 Full Network Telemetry Stream")
st.dataframe(df, use_container_width=True)

# Auto-refresh logic representation (for demonstration purposes)
st.caption("Auto-refreshing every 2 seconds...")
time.sleep(2)
st.rerun()
