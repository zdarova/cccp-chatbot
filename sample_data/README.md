# Sample Data

## Audio Files
- `call-sample-001.wav` — Sample call recording (placeholder for demo)
- `call-sample-002.wav` — Sample call recording (placeholder for demo)

These are minimal WAV files used to test the Azure OpenAI Whisper transcription pipeline.
In production, real recordings would be ingested from Genesys via Blob Storage.

## Usage
```bash
# Process a sample recording through the post-call pipeline
python pipeline/run.py sample_data/call-sample-001.wav --metadata '{"call_id": "CALL-SAMPLE-001", "customer_id": "C-1001", "agent_id": "AGT-12", "call_centre": "Milano"}'
```
