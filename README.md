# Kafka Consumer for LLM Conversation Simulation

A high-performance Kafka consumer that simulates conversations using LLM APIs. Designed to handle 10K simultaneous events as burst workload with rate limiting, concurrency control, and comprehensive monitoring.

## Features

- **Scalable Architecture**: 5 consumer instances processing 100 concurrent conversations
- **Rate Limiting**: Configurable RPS limits to LLM backend (default: 50 RPS total)
- **LiteLLM Integration**: Support for any LLM provider (OpenAI, Anthropic, Bedrock, etc.)
- **Robust Error Handling**: Circuit breaker, exponential backoff, automatic retries
- **Progress Tracking**: Real-time batch progress with ETA calculations
- **Graceful Shutdown**: Ensures in-flight conversations complete before shutdown

## Architecture

```
Kafka Topic (10K burst) → [5 Consumer Instances] → [Rate-Limited Worker Pool] → [LiteLLM] → [Summary POST]
```

### Performance Expectations

| Configuration    | Throughput       | 10K Completion Time |
| ---------------- | ---------------- | ------------------- |
| Current (50 RPS) | ~100 concurrent  | 25-40 minutes       |
| Scaled (500 RPS) | ~1000 concurrent | 2-5 minutes         |

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Python 3.11+ (for local development)
- Kafka cluster (or use included docker-compose setup)
- LLM API access (OpenAI, Anthropic, etc.)

### Using Docker Compose (Recommended)

1. **Clone and configure**:

   ```bash
   cd consumer
   cp .env.example .env
   # Edit .env with your LLM API key and configuration
   ```

2. **Start all services**:

   ```bash
   docker-compose up -d
   ```

   This starts:

   - Kafka + Zookeeper
   - 5 consumer instances
   - Grafana (metrics visualization)

3. **Access monitoring**:
   - Grafana: http://localhost:3000 (admin/admin)
   - Consumer metrics: http://localhost:8001-8005/metrics

### Local Development

1. **Install dependencies**:

   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment**:

   ```bash
   cp .env.example .env
   # Edit .env
   ```

3. **Run consumer**:
   ```bash
   python consumer.py
   ```

## Configuration

### Environment Variables

#### Kafka Configuration

- `KAFKA_BOOTSTRAP_SERVERS`: Kafka broker addresses (default: `localhost:9092`)
- `KAFKA_TOPIC`: Topic to consume from (default: `simulation-events`)
- `KAFKA_CONSUMER_GROUP`: Consumer group ID (default: `simulation-consumer-group`)

#### Consumer Configuration

- `CONCURRENT_CONVERSATIONS`: Max concurrent conversations per instance (default: `20`)
- `LLM_RATE_LIMIT_RPS`: Rate limit for LLM API calls per instance (default: `10`)
- `MAX_ITERATIONS`: Maximum conversation iterations (default: `10`)
- `CONVERSATION_TIMEOUT`: Timeout for entire conversation in seconds (default: `300`)

#### LLM Client Configuration

- `LLM_BACKEND_URL`: LiteLLM backend URL (optional, LiteLLM auto-routes by model)
- `LLM_TIMEOUT`: API call timeout in seconds (default: `30`)
- `LLM_RETRY_ATTEMPTS`: Number of retry attempts (default: `3`)
- `LLM_CONNECTION_POOL_SIZE`: HTTP connection pool size (default: `50`)
- `LLM_API_KEY`: API key for LLM provider (required)

#### Metrics Configuration

- `METRICS_PORT`: Metrics endpoint port (default: `8000`)

### Scaling Configuration

To handle higher throughput, adjust these parameters:

```bash
# For 500 RPS (10x scale)
CONCURRENT_CONVERSATIONS=200
LLM_RATE_LIMIT_RPS=100
# Deploy 5 instances = 1000 concurrent, 500 RPS
```

## Event Schema

### Input (Kafka Message)

```json
{
  "id": "simulation-uuid",
  "persona": {
    "name": "Technical Manager",
    "description": "An experienced engineering manager focused on team productivity",
    "traits": ["analytical", "direct", "efficiency-focused"]
  },
  "intent": "I need help optimizing our CI/CD pipeline",
  "max_iterations": 10,
  "callback_url": "http://api.example.com/simulations/summary",
  "model": "gpt-4"
}
```

### Output (Summary POST)

```json
{
  "simulation_id": "simulation-uuid",
  "conversation_history": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "I need help optimizing our CI/CD pipeline"},
    {"role": "assistant", "content": "I'd be happy to help..."},
    ...
  ],
  "total_iterations": 7,
  "end_reason": "completed",
  "duration_ms": 12500
}
```

## Model Support

Thanks to LiteLLM, you can use any supported model by specifying it in the event:

```json
{
  "model": "gpt-4",              // OpenAI
  "model": "claude-3-opus",      // Anthropic
  "model": "bedrock/anthropic.claude-v2",  // AWS Bedrock
  "model": "azure/gpt-4",        // Azure OpenAI
  ...
}
```

See [LiteLLM docs](https://docs.litellm.ai/docs/providers) for full provider list.

## Monitoring

**Conversation Metrics**:

- `conversations_active`: Current active conversations
- `conversations_completed`: Total completed
- `conversations_failed`: Total failed (by reason)
- `conversation_duration_seconds`: Duration histogram
- `iterations_per_conversation`: Iterations histogram

**LLM API Metrics**:

- `llm_api_calls`: Total API calls
- `llm_api_latency_seconds`: Latency histogram
- `llm_api_errors`: Errors by type

**Kafka Metrics**:

- `kafka_consumer_lag`: Current consumer lag
- `kafka_messages_consumed`: Total messages consumed
- `kafka_commits_succeeded/failed`: Commit statistics

**Progress Metrics**:

- `remaining_simulations`: Simulations remaining
- `total_simulations`: Total in batch

### Grafana Dashboards

Access Grafana at http://localhost:3000 and create dashboards using the metrics above.

Example queries:

```promql
# Throughput
rate(conversations_completed[5m])

# Success rate
rate(conversations_completed[5m]) / (rate(conversations_completed[5m]) + rate(conversations_failed[5m]))

# Average conversation duration
rate(conversation_duration_seconds_sum[5m]) / rate(conversation_duration_seconds_count[5m])

# LLM API P95 latency
histogram_quantile(0.95, rate(llm_api_latency_seconds_bucket[5m]))
```

## Error Handling

### LLM Backend Errors

- **Timeout**: Retries 3x with exponential backoff
- **Rate Limit (429)**: Exponential backoff up to 16 seconds
- **Server Error (5xx)**: Retries with circuit breaker
- **Circuit Breaker**: Opens after 5 consecutive failures, resets after 60s

### Kafka Errors

- **Rebalance**: Completes in-flight tasks before releasing partition
- **Deserialization**: Logs error and commits offset (skips bad message)
- **Processing Failure**: Retries message (doesn't commit offset)

### Conversation Timeouts

If a conversation exceeds `CONVERSATION_TIMEOUT`:

- Conversation ends with `end_reason: "timeout"`
- Partial conversation history is POSTed
- Kafka offset is committed

## Testing

### Producer Script

Create test events:

```python
from kafka import KafkaProducer
import json

producer = KafkaProducer(
    bootstrap_servers='localhost:9094',
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)

event = {
    "id": "test-001",
    "persona": {
        "name": "Test User",
        "description": "A test persona",
        "traits": ["curious"]
    },
    "intent": "Hello, how are you?",
    "max_iterations": 5,
    "callback_url": "http://httpbin.org/post",
    "model": "gpt-3.5-turbo"
}

producer.send('simulation-events', event)
producer.flush()
```

### Load Testing

Send 1000 test events:

```bash
python scripts/load_test.py --count 1000 --topic simulation-events
```

## Troubleshooting

### Consumer not processing messages

1. Check consumer group status:

   ```bash
   docker-compose exec kafka kafka-consumer-groups \
     --bootstrap-server localhost:9092 \
     --describe --group simulation-consumer-group
   ```

2. Check consumer logs:
   ```bash
   docker-compose logs -f consumer-1
   ```

### LLM API errors

1. Verify API key in `.env`
2. Check LiteLLM backend health
3. Review circuit breaker status in logs
4. Check `llm_api_errors` metric

### High latency

1. Check `llm_api_latency_seconds` metric
2. Verify rate limits aren't being hit
3. Consider increasing `CONCURRENT_CONVERSATIONS`
4. Scale up consumer instances

### Consumer lag growing

1. Increase `CONCURRENT_CONVERSATIONS`
2. Increase `LLM_RATE_LIMIT_RPS`
3. Add more consumer instances
4. Check for slow callback URLs

## Development

### Project Structure

```
consumer/
├── consumer.py              # Main Kafka consumer loop
├── worker.py                # Conversation worker with rate limiting
├── llm_client.py            # LiteLLM client with retry logic
├── config.py                # Configuration management
├── progress.py              # Batch progress tracking
├── requirements.txt         # Python dependencies
├── Dockerfile               # Container image
├── docker-compose.yml       # Multi-container setup
└── README.md               # This file
```

### Adding New Features

1. **Custom end detection**: Modify `_should_end_conversation()` in [worker.py](worker.py)
2. **Additional metrics**: Add to [metrics.py](metrics.py)
3. **New LLM providers**: LiteLLM handles this automatically
4. **Custom conversation logic**: Modify `_run_conversation()` in [worker.py](worker.py)

## License

MIT

## Support

For issues and questions:

- GitHub Issues: [Your repo]
- Documentation: [Your docs]
