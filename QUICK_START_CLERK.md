# 🚀 Quick Start: Clerk Integration

## ✅ What's Done

- Backend webhook endpoint created
- Database integration ready  
- Authentication middleware prepared
- All code deployed and running

## 🎯 Next Steps (5 minutes)

### 1. Start ngrok (for local testing)
```bash
# Install if needed
brew install ngrok   # or: npm install -g ngrok

# Start tunnel
ngrok http 8002
```

You'll get a URL like: `https://abc123.ngrok.io`

### 2. Configure Clerk Webhook

1. Go to: https://dashboard.clerk.com
2. Select your app
3. Go to **Webhooks** → **Add Endpoint**
4. Enter URL: `https://abc123.ngrok.io/api/webhooks/clerk`
5. Select events:
   - ✅ user.created
   - ✅ user.updated  
   - ✅ user.deleted
6. Click **Create**
7. **Copy the webhook secret** (starts with `whsec_`)

### 3. Update .env

```bash
# Edit .env and replace this line:
CLERK_WEBHOOK_SECRET=whsec_your_actual_secret_here
```

### 4. Restart Backend

```bash
make stop
make start
```

### 5. Test It!

1. Go to http://localhost:3000
2. Sign up with a new account
3. Check it worked:

```bash
# Check logs
tail -f logs/backend.log | grep "Clerk webhook"

# Check database
PGPASSWORD=password psql -U postgres -h localhost -d xgrowth \
  -c "SELECT id, email, created_at FROM users ORDER BY created_at DESC LIMIT 5;"
```

You should see: `✅ Created user: user_xxxxx`

## 🎉 Done!

Now when users sign up through Clerk:
- ✅ They're auto-created in your database
- ✅ You can link them to X accounts
- ✅ Their posts are stored properly
- ✅ Everything syncs automatically

## 🔐 For Production

See `CLERK_PRODUCTION_SETUP.md` for:
- JWT token verification
- Production security
- Deployment checklist

---

**Need Help?** Check the full guides:
- `CLERK_INTEGRATION_SUMMARY.md` - Overview
- `CLERK_PRODUCTION_SETUP.md` - Complete setup guide
