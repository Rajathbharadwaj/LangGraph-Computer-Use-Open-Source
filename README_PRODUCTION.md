# X Growth Automation - Production Ready System

🚀 **Scalable, secure, and production-ready X (Twitter) growth automation platform.**

## ✨ What's New in Production Version

### 🔐 Security
- ✅ **Clerk Authentication** - Secure user login and management
- ✅ **Encrypted Cookie Storage** - Fernet encryption for X cookies
- ✅ **Environment Variables** - No hardcoded secrets
- ✅ **Rate Limiting** - Redis-based API throttling
- ✅ **Per-User Isolation** - Separate Docker containers per user

### 📊 Scalability
- ✅ **PostgreSQL Database** - Persistent user data
- ✅ **Redis Cache** - Fast session and rate limit storage
- ✅ **Docker Compose** - Easy multi-service deployment
- ✅ **Horizontal Scaling** - Load balancer ready
- ✅ **Per-User Containers** - Isolated browser sessions

### 🛠️ Developer Experience
- ✅ **Makefile Commands** - Simple deployment commands
- ✅ **Environment Templates** - Easy configuration
- ✅ **Comprehensive Docs** - Deployment guides
- ✅ **Monitoring Ready** - Sentry integration

## 🏗️ Architecture

```
User Browser (Chrome Extension)
         ↓
    Dashboard (Next.js + Clerk Auth)
         ↓
    Backend API (FastAPI)
         ↓
    ┌────┴────┬─────────┬──────────┐
    ↓         ↓         ↓          ↓
PostgreSQL  Redis   LangGraph  OmniParser
    ↓
Per-User Docker Containers
```

## 🚀 Quick Start

### Development Mode

```bash
# Start all services
make start

# Check status
make status

# View logs
make logs

# Stop all
make stop
```

### Production Mode

```bash
# Setup production
make prod-setup

# Configure .env file
cp .env.example .env
# Edit .env with your values

# Start production services
make prod-up

# Check status
make prod-status

# View logs
make prod-logs
```

## 📋 Prerequisites

### Development
- Python 3.12+
- Node.js 20+
- Docker & Docker Compose
- PostgreSQL (via Docker)
- Redis (via Docker)

### Production
- Ubuntu 22.04 LTS
- 4+ CPU cores, 8GB+ RAM
- Docker & Docker Compose
- Domain name + SSL certificate
- Clerk account
- API keys (Anthropic, OpenAI)

## 🔧 Configuration

### 1. Backend (.env)

```bash
# Database
DATABASE_URL=postgresql://postgres:password@localhost:5432/xgrowth

# Redis
REDIS_URL=redis://localhost:6379

# Encryption
COOKIE_ENCRYPTION_KEY=<generate-with-make-prod-setup>

# Clerk
CLERK_SECRET_KEY=sk_live_...

# API Keys
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...

# Rate Limiting
RATE_LIMIT_PER_HOUR=100
RATE_LIMIT_PER_DAY=1000
```

### 2. Frontend (.env.local)

```bash
# Clerk
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_live_...
CLERK_SECRET_KEY=sk_live_...

# API URLs
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_EXTENSION_API_URL=http://localhost:8001
NEXT_PUBLIC_LANGGRAPH_API_URL=http://localhost:8124
NEXT_PUBLIC_OMNIPARSER_URL=http://localhost:8003
```

## 📦 Database Schema

### Users Table
```sql
CREATE TABLE users (
    id VARCHAR PRIMARY KEY,  -- Clerk user ID
    email VARCHAR UNIQUE NOT NULL,
    plan VARCHAR DEFAULT 'free',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

### X Accounts Table
```sql
CREATE TABLE x_accounts (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR REFERENCES users(id),
    username VARCHAR NOT NULL,
    display_name VARCHAR,
    is_connected BOOLEAN DEFAULT TRUE,
    last_synced_at TIMESTAMP,
    created_at TIMESTAMP
);
```

### User Cookies Table
```sql
CREATE TABLE user_cookies (
    id SERIAL PRIMARY KEY,
    x_account_id INTEGER REFERENCES x_accounts(id),
    encrypted_cookies TEXT NOT NULL,
    captured_at TIMESTAMP,
    expires_at TIMESTAMP
);
```

## 🔒 Security Features

### Cookie Encryption
```python
from services import cookie_encryption

# Encrypt cookies before storing
encrypted = cookie_encryption.encrypt_cookies(cookies)

# Decrypt when needed
cookies = cookie_encryption.decrypt_cookies(encrypted)
```

### Rate Limiting
```python
from services import rate_limiter

# Check rate limit
is_allowed, retry_after = await rate_limiter.check_rate_limit(
    user_id="user_123",
    endpoint="/api/scrape-posts"
)

if not is_allowed:
    return {"error": "Rate limit exceeded", "retry_after": retry_after}
```

### Per-User Docker Containers
```python
from services import docker_manager

# Start container for user
container_info = docker_manager.start_container(user_id="user_123")

# Get browser port
browser_port = container_info["browser_port"]  # Random port per user
```

## 📊 Monitoring

### Sentry Integration
```python
from monitoring import init_monitoring, capture_exception

# Initialize on startup
init_monitoring()

# Capture errors
try:
    # Your code
    pass
except Exception as e:
    capture_exception(e, context={"user_id": user_id})
```

### Health Checks
```bash
# Backend
curl http://localhost:8000/health

# Database
make prod-status

# Redis
docker exec xgrowth-redis redis-cli ping
```

## 🔄 Deployment

### Docker Compose
```bash
# Build images
docker-compose -f docker-compose.prod.yml build

# Start services
docker-compose -f docker-compose.prod.yml up -d

# View logs
docker-compose -f docker-compose.prod.yml logs -f

# Stop services
docker-compose -f docker-compose.prod.yml down
```

### Makefile Commands
```bash
make prod-setup      # Setup production environment
make prod-up         # Start production services
make prod-down       # Stop production services
make prod-logs       # View logs
make prod-status     # Check service status
make prod-restart    # Restart services
make prod-clean      # Clean all data (WARNING!)
```

## 📈 Scaling

### Horizontal Scaling
```bash
# Scale backend to 3 instances
docker-compose -f docker-compose.prod.yml up -d --scale backend=3
```

### Load Balancer (Nginx)
```nginx
upstream backend {
    server localhost:8000;
    server localhost:8001;
    server localhost:8002;
}

server {
    location /api/ {
        proxy_pass http://backend;
    }
}
```

## 💰 Cost Estimates

### Small (< 100 users)
- **Infrastructure:** $50-100/month
  - 1x VPS (4GB RAM)
  - Managed PostgreSQL
  - Managed Redis

### Medium (100-1000 users)
- **Infrastructure:** $200-500/month
  - 2x VPS (8GB RAM)
  - Managed PostgreSQL (HA)
  - Managed Redis (HA)
  - Load Balancer

### Large (1000+ users)
- **Infrastructure:** $1000+/month
  - Kubernetes cluster
  - Managed services
  - CDN
  - Monitoring

## 🐛 Troubleshooting

### Database Connection Failed
```bash
# Check PostgreSQL
docker exec xgrowth-postgres pg_isready

# Check connection string
echo $DATABASE_URL
```

### Redis Connection Failed
```bash
# Check Redis
docker exec xgrowth-redis redis-cli ping

# Should return: PONG
```

### Docker Container Issues
```bash
# List containers
docker ps -a

# Check logs
docker logs xgrowth-backend

# Restart container
docker restart xgrowth-backend
```

## 📚 Documentation

- [Production Deployment Guide](./PRODUCTION_DEPLOYMENT.md)
- [Environment Variables](/.env.example)
- [Database Models](./database/models.py)
- [API Documentation](http://localhost:8000/docs)

## 🎯 Roadmap

- [x] Clerk authentication
- [x] PostgreSQL database
- [x] Redis caching
- [x] Encrypted cookie storage
- [x] Rate limiting
- [x] Per-user Docker containers
- [x] Docker Compose deployment
- [ ] Kubernetes deployment
- [ ] Monitoring dashboard
- [ ] Automated backups
- [ ] Multi-region support

## 📞 Support

For issues or questions:
- Check logs: `make logs` or `make prod-logs`
- Review documentation
- Check GitHub issues

## 📄 License

[Your License Here]

---

Built with ❤️ for X growth automation

