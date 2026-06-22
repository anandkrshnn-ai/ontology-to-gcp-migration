FROM apache/beam_python3.11_sdk:2.53.0

WORKDIR /opt/dataflow

# Copy dependencies first for caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all dataflow code
COPY . /opt/dataflow/

# Ensure main pipeline is executable
RUN chmod +x pipeline.py
