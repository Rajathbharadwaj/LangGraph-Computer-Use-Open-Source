#!/bin/bash

echo "🚀 Production Deployment Setup"
echo "================================"
echo ""
echo "This script will help you set up your X Automation SaaS for production"
echo ""

# Check if running as root
if [ "$EUID" -eq 0 ]; then 
   echo "⚠️  Please don't run as root"
   exit 1
fi

# Function to prompt for input
prompt() {
    read -p "$1: " value
    echo $value
}

# Function to generate random key
generate_key() {
    python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
}

echo "📋 Step 1: Environment Configuration"
echo "======================================"
echo ""

# Create .env file
if [ -f ".env.production" ]; then
    echo "⚠️  .env.production already exists. Backup created as .env.production.backup"
    cp .env.production .env.production.backup
fi

echo "Creating .env.production file..."
cat > .env.production << EOF
# Database
DATABASE_URL=postgresql://saas_user:CHANGE_ME@postgres:5432/saas_db
DB_PASSWORD=CHANGE_ME

# Redis
REDIS_URL=redis://redis:6379

# Encryption
COOKIE_ENCRYPTION_KEY=$(generate_key)

# JWT
JWT_SECRET=$(openssl rand -hex 32)

# Stripe
STRIPE_SECRET_KEY=sk_test_CHANGE_ME
STRIPE_PUBLISHABLE_KEY=pk_test_CHANGE_ME
STRIPE_WEBHOOK_SECRET=whsec_CHANGE_ME

# Email (SendGrid)
SENDGRID_API_KEY=CHANGE_ME
FROM_EMAIL=noreply@your-saas.com

# Monitoring
SENTRY_DSN=CHANGE_ME

# MinIO (S3-compatible storage)
MINIO_ACCESS_KEY=$(openssl rand -hex 16)
MINIO_SECRET_KEY=$(openssl rand -hex 32)

# Domain
DOMAIN=your-saas.com
FRONTEND_URL=https://your-saas.com
BACKEND_URL=https://api.your-saas.com

# Browser Pool
BROWSER_POOL_SIZE=5
BROWSER_POOL_MAX=20
EOF

echo "✅ .env.production created"
echo ""
echo "⚠️  IMPORTANT: Edit .env.production and replace all CHANGE_ME values!"
echo ""

echo "📋 Step 2: Docker Setup"
echo "======================="
echo ""

# Create docker-compose.prod.yml
cat > docker-compose.prod.yml << 'EOF'
version: '3.8'

services:
  # Nginx reverse proxy
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/ssl:/etc/nginx/ssl:ro
      - ./nginx/logs:/var/log/nginx
    depends_on:
      - backend
    restart: unless-stopped
    networks:
      - saas-network

  # Backend API
  backend:
    build:
      context: .
      dockerfile: Dockerfile.backend
    env_file:
      - .env.production
    depends_on:
      - postgres
      - redis
    restart: unless-stopped
    networks:
      - saas-network
    deploy:
      replicas: 2

  # Celery workers
  worker:
    build:
      context: .
      dockerfile: Dockerfile.backend
    command: celery -A automation worker --loglevel=info --concurrency=4
    env_file:
      - .env.production
    depends_on:
      - postgres
      - redis
    restart: unless-stopped
    networks:
      - saas-network
    deploy:
      replicas: 3

  # Browser pool
  browser-1:
    image: cua-stealth
    shm_size: '2gb'
    restart: unless-stopped
    networks:
      - saas-network

  browser-2:
    image: cua-stealth
    shm_size: '2gb'
    restart: unless-stopped
    networks:
      - saas-network

  browser-3:
    image: cua-stealth
    shm_size: '2gb'
    restart: unless-stopped
    networks:
      - saas-network

  # PostgreSQL
  postgres:
    image: postgres:15
    env_file:
      - .env.production
    environment:
      - POSTGRES_DB=saas_db
      - POSTGRES_USER=saas_user
    volumes:
      - postgres-data:/var/lib/postgresql/data
      - ./backups:/backups
    restart: unless-stopped
    networks:
      - saas-network

  # Redis
  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes
    volumes:
      - redis-data:/data
    restart: unless-stopped
    networks:
      - saas-network

  # MinIO (S3-compatible storage)
  minio:
    image: minio/minio
    command: server /data --console-address ":9001"
    env_file:
      - .env.production
    volumes:
      - minio-data:/data
    restart: unless-stopped
    networks:
      - saas-network

volumes:
  postgres-data:
  redis-data:
  minio-data:

networks:
  saas-network:
    driver: bridge
EOF

echo "✅ docker-compose.prod.yml created"
echo ""

echo "📋 Step 3: Nginx Configuration"
echo "==============================="
echo ""

mkdir -p nginx/ssl nginx/logs

cat > nginx/nginx.conf << 'EOF'
events {
    worker_connections 1024;
}

http {
    upstream backend {
        server backend:8000;
    }

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;
    limit_req_zone $binary_remote_addr zone=login_limit:10m rate=5r/m;

    server {
        listen 80;
        server_name your-saas.com api.your-saas.com;
        
        # Redirect to HTTPS
        return 301 https://$server_name$request_uri;
    }

    server {
        listen 443 ssl http2;
        server_name api.your-saas.com;

        ssl_certificate /etc/nginx/ssl/fullchain.pem;
        ssl_certificate_key /etc/nginx/ssl/privkey.pem;

        # Security headers
        add_header X-Frame-Options "SAMEORIGIN" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header X-XSS-Protection "1; mode=block" always;

        # API endpoints
        location /api/ {
            limit_req zone=api_limit burst=20 nodelay;
            
            proxy_pass http://backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        # WebSocket for VNC
        location /vnc/ {
            proxy_pass http://backend;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
            proxy_set_header Host $host;
        }

        # Health check
        location /health {
            access_log off;
            return 200 "healthy\n";
        }
    }
}
EOF

echo "✅ Nginx configuration created"
echo ""
echo "⚠️  Update nginx/nginx.conf with your actual domain"
echo ""

echo "📋 Step 4: Database Schema"
echo "=========================="
echo ""

cat > schema.sql << 'EOF'
-- Users table
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    stripe_customer_id VARCHAR(255),
    plan VARCHAR(50) NOT NULL DEFAULT 'starter',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- X Sessions table
CREATE TABLE x_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    encrypted_cookies TEXT NOT NULL,
    username VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP,
    last_used TIMESTAMP,
    is_valid BOOLEAN DEFAULT TRUE,
    UNIQUE(user_id)
);

-- Jobs table
CREATE TABLE jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    celery_job_id VARCHAR(255),
    type VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL,
    params JSONB,
    result JSONB,
    error TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);

-- Subscriptions table
CREATE TABLE subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    stripe_subscription_id VARCHAR(255),
    plan VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL,
    current_period_start TIMESTAMP,
    current_period_end TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id)
);

-- Indexes
CREATE INDEX idx_jobs_user_id ON jobs(user_id);
CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_jobs_created_at ON jobs(created_at DESC);
CREATE INDEX idx_x_sessions_user_id ON x_sessions(user_id);
CREATE INDEX idx_x_sessions_expires_at ON x_sessions(expires_at);
EOF

echo "✅ schema.sql created"
echo ""

echo "📋 Step 5: SSL Certificates"
echo "============================"
echo ""
echo "To get SSL certificates, run:"
echo ""
echo "  sudo apt install certbot"
echo "  sudo certbot certonly --standalone -d your-saas.com -d api.your-saas.com"
echo "  sudo cp /etc/letsencrypt/live/your-saas.com/fullchain.pem nginx/ssl/"
echo "  sudo cp /etc/letsencrypt/live/your-saas.com/privkey.pem nginx/ssl/"
echo ""

echo "📋 Step 6: Build & Deploy"
echo "========================="
echo ""
echo "To build and deploy:"
echo ""
echo "  # Build stealth browser"
echo "  docker build -f Dockerfile.stealth -t cua-stealth ."
echo ""
echo "  # Start all services"
echo "  docker-compose -f docker-compose.prod.yml up -d"
echo ""
echo "  # Initialize database"
echo "  docker-compose -f docker-compose.prod.yml exec postgres psql -U saas_user -d saas_db -f /backups/schema.sql"
echo ""
echo "  # Check logs"
echo "  docker-compose -f docker-compose.prod.yml logs -f"
echo ""

echo "✅ Setup Complete!"
echo ""
echo "📚 Next Steps:"
echo "=============="
echo "1. Edit .env.production (replace all CHANGE_ME values)"
echo "2. Update nginx/nginx.conf with your domain"
echo "3. Get SSL certificates"
echo "4. Build and deploy"
echo "5. Test all endpoints"
echo "6. Monitor logs"
echo ""
echo "📖 Full guide: cat PRODUCTION_SAAS_ARCHITECTURE.md"
echo ""

