# Production Deployment Guide

This guide walks you through deploying the X Growth Automation system to production.

## 🎯 Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    LOAD BALANCER (Nginx)                │
│                  https://yourdomain.com                 │
└─────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
┌───────▼────────┐  ┌──────▼───────┐  ┌───────▼────────┐
│  Frontend      │  │  Backend API │  │  LangGraph     │
│  (Next.js)     │  │  (FastAPI)   │  │  Server        │
│  Port 3000     │  │  Port 8000   │  │  Port 8124     │
└────────┬───────┘  └──────┬───────┘  └───────┬────────┘
         │                 │                   │
         └─────────────────┼───────────────────┘
                           │
         ┌─────────────────┴─────────────────┐
         │                                   │
    ┌────▼─────┐                    ┌───────▼────────┐
    │  Redis   │                    │   PostgreSQL   │
    │ (Cache)  │                    │  (User Data)   │
    └──────────┘                    └────────────────┘
         │
         │
    ┌────▼──────────────────────────────────────┐
    │     Docker Containers (Per-User)          │
    │  ┌──────────┐  ┌──────────┐  ┌──────────┐│
    │  │ Browser  │  │ Browser  │  │ Browser  ││
    │  │ User 1   │  │ User 2   │  │ User 3   ││
    │  └──────────┘  └──────────┘  └──────────┘│
    └───────────────────────────────────────────┘
```

## 📋 Prerequisites

1. **Server Requirements:**
   - Ubuntu 22.04 LTS (or similar)
   - 4+ CPU cores
   - 8GB+ RAM
   - 50GB+ storage
   - Docker & Docker Compose installed

2. **External Services:**
   - Clerk account (for authentication)
   - Domain name (for production)
   - SSL certificate (Let's Encrypt recommended)

3. **API Keys:**
   - Anthropic API key
   - OpenAI API key (optional)

## 🚀 Quick Start

### Step 1: Clone and Setup

```bash
# Clone repository
git clone <your-repo>
cd cua

# Run production setup
make prod-setup

# This will:
# - Install dependencies
# - Generate encryption key
# - Create .env.prod.key file
```

### Step 2: Configure Environment

```bash
# Copy example env file
cp .env.example .env

# Edit .env with your values
nano .env
```

**Required Environment Variables:**

```bash
# Database
DATABASE_URL=postgresql://postgres:STRONG_PASSWORD@postgres:5432/xgrowth

# Redis
REDIS_URL=redis://redis:6379

# Encryption (use the generated key from .env.prod.key)
COOKIE_ENCRYPTION_KEY=<your-generated-key>

# Clerk Authentication
CLERK_SECRET_KEY=sk_live_...

# API Keys
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...

# Rate Limiting
RATE_LIMIT_PER_HOUR=100
RATE_LIMIT_PER_DAY=1000

# Docker
DOCKER_HOST=unix:///var/run/docker.sock
DOCKER_BROWSER_IMAGE=stealth-cua
DOCKER_NETWORK=xgrowth_network

# Environment
ENVIRONMENT=production
```

### Step 3: Setup Clerk

1. Go to https://clerk.com and create an account
2. Create a new application
3. Get your keys from the dashboard
4. Add to `.env`:
   ```bash
   CLERK_SECRET_KEY=sk_live_...
   ```

5. Add to `cua-frontend/.env.local`:
   ```bash
   NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_live_...
   CLERK_SECRET_KEY=sk_live_...
   ```

### Step 4: Build Docker Images

```bash
# Build all images
docker-compose -f docker-compose.prod.yml build

# Or use make command
make docker-build
```

### Step 5: Start Services

```bash
# Start all services
make prod-up

# Check status
make prod-status

# View logs
make prod-logs
```

### Step 6: Initialize Database

```bash
# Initialize database tables
make prod-db-init
```

### Step 7: Verify Deployment

```bash
# Check all services are running
make prod-status

# Test endpoints
curl http://localhost:8000/
curl http://localhost:3000/
```

## 🔒 Security Checklist

- [ ] Change default PostgreSQL password
- [ ] Use strong encryption key (generated, not example)
- [ ] Enable HTTPS with SSL certificate
- [ ] Configure firewall (UFW)
- [ ] Set up fail2ban
- [ ] Enable Docker security scanning
- [ ] Rotate API keys regularly
- [ ] Set up monitoring and alerts
- [ ] Configure backup strategy
- [ ] Review and limit CORS origins

## 📊 Monitoring

### Health Checks

```bash
# Backend health
curl http://localhost:8000/health

# Database health
docker exec xgrowth-postgres pg_isready

# Redis health
docker exec xgrowth-redis redis-cli ping
```

### Logs

```bash
# View all logs
make prod-logs

# View specific service
docker-compose -f docker-compose.prod.yml logs -f backend

# View last 100 lines
docker-compose -f docker-compose.prod.yml logs --tail=100
```

## 🔄 Updates and Maintenance

### Update Application

```bash
# Pull latest code
git pull

# Rebuild and restart
make prod-restart
```

### Database Backup

```bash
# Backup database
docker exec xgrowth-postgres pg_dump -U postgres xgrowth > backup_$(date +%Y%m%d).sql

# Restore database
cat backup_20250101.sql | docker exec -i xgrowth-postgres psql -U postgres xgrowth
```

### Clean Old Data

```bash
# Remove old containers
docker system prune -a

# Clean logs
make clean
```

## 🌐 Domain and SSL Setup

### Using Nginx

```nginx
server {
    listen 80;
    server_name yourdomain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    # Frontend
    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    # Backend API
    location /api/ {
        proxy_pass http://localhost:8000/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }
}
```

### Get SSL Certificate

```bash
# Install certbot
sudo apt install certbot python3-certbot-nginx

# Get certificate
sudo certbot --nginx -d yourdomain.com

# Auto-renewal
sudo certbot renew --dry-run
```

## 🐛 Troubleshooting

### Services Won't Start

```bash
# Check Docker
docker ps -a

# Check logs
make prod-logs

# Restart services
make prod-restart
```

### Database Connection Issues

```bash
# Check PostgreSQL is running
docker exec xgrowth-postgres pg_isready

# Check connection string in .env
cat .env | grep DATABASE_URL
```

### Redis Connection Issues

```bash
# Check Redis
docker exec xgrowth-redis redis-cli ping

# Should return: PONG
```

## 📈 Scaling

### Horizontal Scaling

For high traffic, deploy multiple backend instances behind a load balancer:

```bash
# Scale backend to 3 instances
docker-compose -f docker-compose.prod.yml up -d --scale backend=3
```

### Database Scaling

- Use PostgreSQL replication for read replicas
- Consider managed database (AWS RDS, Google Cloud SQL)

### Redis Scaling

- Use Redis Cluster for high availability
- Consider managed Redis (AWS ElastiCache, Redis Cloud)

## 💰 Cost Optimization

**Estimated Monthly Costs:**

- **Small (< 100 users):** $50-100/month
  - 1x VPS (4GB RAM)
  - Managed PostgreSQL
  - Managed Redis

- **Medium (100-1000 users):** $200-500/month
  - 2x VPS (8GB RAM)
  - Managed PostgreSQL (HA)
  - Managed Redis (HA)
  - Load Balancer

- **Large (1000+ users):** $1000+/month
  - Kubernetes cluster
  - Managed services
  - CDN
  - Monitoring

## 📞 Support

For issues or questions:
- Check logs: `make prod-logs`
- Review this guide
- Check GitHub issues

## 🎉 Success!

Your X Growth Automation system is now running in production!

**Next Steps:**
1. Configure your domain and SSL
2. Test the full user flow
3. Set up monitoring and alerts
4. Configure backups
5. Invite beta users!

