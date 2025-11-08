# LangGraph Computer Use Agent - Deployment Guide

This guide helps you deploy your Computer Use Agent using LangGraph Platform.

## Prerequisites

1. **LangGraph CLI**: Install the LangGraph CLI
   ```bash
   pip install langgraph-cli
   ```

2. **Docker**: Ensure Docker is installed and running
   ```bash
   docker --version
   ```

3. **API Keys**: Set up your environment variables

## Environment Setup

Create a `.env` file in the project root:

```bash
# API Keys for LangChain + CUA Integration
ANTHROPIC_API_KEY=your-anthropic-api-key-here
OPENAI_API_KEY=your-openai-api-key-here

# CUA Server Configuration (if running remotely)
CUA_HOST=localhost
CUA_PORT=8001

# OmniParser Configuration (if running remotely)  
OMNIPARSER_URL=http://localhost:8003
```

## Configuration File

The `langgraph.json` file contains:

- **Dependencies**: All required Python packages
- **Graphs**: Entry points for your agent (`cua_agent` and `cua_react_agent`)
- **Docker Configuration**: System dependencies for GUI interaction
- **Storage & TTL**: Data persistence and cleanup policies
- **HTTP Settings**: CORS and header configuration

## Deployment Commands

### 1. Development Mode (Recommended for testing)

```bash
# Install development dependencies
pip install -U "langgraph-cli[inmem]"

# Run in development mode with hot reload
langgraph dev
```

This starts the server at `http://localhost:2024` with:
- Hot reloading on file changes
- Local persistence
- No Docker required

### 2. Production Mode

```bash
# Build the Docker image
langgraph build -t cua-agent

# Start the production server  
langgraph up
```

This starts the server at `http://localhost:8123` with:
- Full Docker environment
- GUI support (X11, VNC)
- Production-grade persistence

### 3. Custom Docker Deployment

```bash
# Generate Dockerfile for custom builds
langgraph dockerfile Dockerfile

# Build and run manually
docker build -t cua-agent .
docker run -p 8123:8000 cua-agent
```

## Testing Your Deployment

Once running, test your agent:

```bash
# Test the API
curl -X POST http://localhost:2024/runs/stream \
  -H "Content-Type: application/json" \
  -d '{
    "assistant_id": "cua_agent",
    "input": {"messages": [{"role": "user", "content": "Take a screenshot and describe what you see"}]},
    "stream_mode": "values"
  }'
```

## Configuration Details

### Graph Definitions

- `cua_agent`: Direct graph export for platform use
- `cua_react_agent`: Function that creates agent (for dynamic configuration)

### Docker Features

The deployment includes:
- **X11 Virtual Display**: For GUI applications
- **VNC Server**: For remote desktop access
- **Firefox**: Pre-installed browser
- **System Tools**: Required for computer control

### Storage & TTL

- **Store TTL**: 24 hours (1440 minutes) for temporary data
- **Checkpoint TTL**: 48 hours (2880 minutes) for conversation state
- **Auto-cleanup**: Every 30-60 minutes

### Security

- **CORS**: Configured for development (allow all origins)
- **Headers**: Supports custom CUA and OmniParser configuration
- **Environment**: Sensitive data in `.env` file only

## Production Considerations

1. **API Keys**: Use secure secret management
2. **CORS**: Restrict origins for production
3. **Monitoring**: Add logging and health checks
4. **Scaling**: Consider load balancing for multiple instances
5. **Security**: Run in isolated containers/VMs

## Troubleshooting

### Common Issues

1. **Docker Build Fails**: Check system dependencies in `dockerfile_lines`
2. **Agent Not Found**: Verify graph exports in `langgraph_cua_agent.py`
3. **Tools Missing**: Ensure all dependencies are in `requirements_langchain.txt`
4. **GUI Issues**: Check X11 and VNC configuration

### Debug Mode

Run with additional debugging:

```bash
# Development with debug port
langgraph dev --debug-port 5678 --wait-for-client

# Production with verbose logging
langgraph up --verbose
```

## Integration Examples

### Frontend Integration

```javascript
// Connect to your deployed agent
const response = await fetch('http://localhost:2024/runs/stream', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    assistant_id: 'cua_agent',
    input: { 
      messages: [{ 
        role: 'user', 
        content: 'Navigate to Twitter and like the first post you see' 
      }]
    },
    stream_mode: 'values'
  })
});
```

### Python Client

```python
from langchain_core.messages import HumanMessage
import requests

# Send task to deployed agent
response = requests.post('http://localhost:2024/runs/stream', json={
    'assistant_id': 'cua_agent',
    'input': {
        'messages': [HumanMessage(content='Take a screenshot')]
    },
    'stream_mode': 'values'
})
```

Your Computer Use Agent is now production-ready with LangGraph Platform! 🚀
