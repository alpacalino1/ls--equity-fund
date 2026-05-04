# Ollama-Cloud Integration Update for Layer 7

## API Preference Update

Based on user preference, replacing Anthropic API with ollama-cloud local inference with smart model rotation.

## Updated API Requirements

1. **Ollama-Cloud Local API** (Primary)
   - Using locally installed models via ollama daemon
   - Smart model rotation for redundancy
   - No external API costs or dependencies

2. **Alpaca API** (`ALPACA_API_KEY` + `ALPACA_SECRET_KEY`)  
   - Unchanged - for real-time portfolio and market data
   - Paper trading mode by default

3. **Polygon.io API** (`POLYGON_API_KEY`) 
   - Unchanged - for enhanced market data (free tier available)

## Ollama-Cloud Model Configuration

Smartest models to use with fallback rotation:

1. **Primary**: `llama3:70b` or `mistral:7b` (local high-performance)
2. **Secondary**: `codellama:7b` (coding-specialized)
3. **Fallback**: `phi:7b` or `gemma:7b` (efficient local models)
4. **Minimal**: `tinyllama` (resource-constrained environments)

## Configuration Changes Required

### .env Updates
```bash
# Remove or comment out:
# ANTHROPIC_API_KEY=sk-ant-...

# Add ollama endpoint (usually localhost:11434)
OLLAMA_ENDPOINT=http://localhost:11434
```

### config.yaml Updates  
```yaml
# Replace reporting.commentary section:
reporting:
  attribution:
    benchmark: "SPY"
    lookback_days: 252
  commentary:
    weekday: "Friday"
    models: 
      - "llama3:70b"    # Primary model
      - "mistral:7b"    # Secondary option  
      - "codellama:7b"  # Coding specialization
      - "phi:7b"        # Efficient fallback
    endpoint: "${OLLAMA_ENDPOINT}"  # From .env
    max_tokens: 1000
    temperature: 0.7
  # ... rest unchanged
```

## Implementation Changes Needed

1. **Replace anthropic imports** with ollama client library
2. **Update API calling logic** to use ollama model rotation
3. **Add model health checks** for automatic fallback
4. **Maintain same response formatting** for compatibility
5. **Keep Claude/JARVIS personality** with ollama models

## Benefits of This Approach

✅ **Zero External API Costs** - All inference local
✅ **Full Control** - No rate limits or service disruptions  
✅ **Privacy** - No data leaves local environment
✅ **Redundancy** - Multiple models for fallback
✅ **Performance** - GPU-accelerated local inference
✅ **Flexibility** - Easy model switching/updating

The JARVIS persona will maintain identical functionality with ollama-cloud replacing Anthropic API as the inference engine.