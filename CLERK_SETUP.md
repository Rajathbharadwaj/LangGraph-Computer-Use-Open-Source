# Clerk Authentication Setup Guide

## 🔐 What is Clerk?

Clerk provides drop-in authentication for your application. It handles:
- User sign-up and sign-in
- Session management
- User profiles
- Multi-factor authentication
- OAuth providers (Google, GitHub, etc.)

## 🚀 Setup Steps

### 1. Create Clerk Account

1. Go to https://clerk.com
2. Click "Start building for free"
3. Sign up with your email or GitHub

### 2. Create Application

1. After signing in, click "Create Application"
2. Name it "X Growth Automation" (or your preferred name)
3. Choose authentication methods:
   - ✅ Email
   - ✅ Google (optional)
   - ✅ GitHub (optional)
4. Click "Create Application"

### 3. Get API Keys

1. In your Clerk dashboard, go to "API Keys"
2. You'll see two types of keys:

**Publishable Key** (starts with `pk_test_` or `pk_live_`)
- Used in frontend (public, safe to expose)
- Example: `pk_test_Y2xlcmsuaW5jbHVkZWQua2l3aS03NC5sY2wuZGV2JA`

**Secret Key** (starts with `sk_test_` or `sk_live_`)
- Used in backend (private, keep secret!)
- Example: `sk_test_abcd1234efgh5678ijkl9012mnop3456`

### 4. Configure Frontend

Create `/home/rajathdb/cua-frontend/.env.local`:

```bash
# Clerk Keys
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_your_key_here
CLERK_SECRET_KEY=sk_test_your_key_here

# Clerk URLs
NEXT_PUBLIC_CLERK_SIGN_IN_URL=/sign-in
NEXT_PUBLIC_CLERK_SIGN_UP_URL=/sign-up
NEXT_PUBLIC_CLERK_AFTER_SIGN_IN_URL=/
NEXT_PUBLIC_CLERK_AFTER_SIGN_UP_URL=/

# API URLs
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_EXTENSION_API_URL=http://localhost:8001
NEXT_PUBLIC_LANGGRAPH_API_URL=http://localhost:8124
NEXT_PUBLIC_OMNIPARSER_URL=http://localhost:8003
```

### 5. Configure Backend

Add to `/home/rajathdb/cua/.env`:

```bash
# Clerk
CLERK_SECRET_KEY=sk_test_your_key_here
```

### 6. Test Authentication

1. Start the frontend:
   ```bash
   cd /home/rajathdb/cua-frontend
   npm run dev
   ```

2. Open http://localhost:3000

3. You should see a login page!

4. Click "Sign Up" and create an account

5. After signing in, you'll be redirected to the dashboard

## 🎨 Customization

### Change Theme

1. In Clerk dashboard, go to "Customization"
2. Choose "Dark" theme to match your dashboard
3. Customize colors, logo, etc.

### Add OAuth Providers

1. In Clerk dashboard, go to "User & Authentication" → "Social Connections"
2. Enable Google, GitHub, etc.
3. Follow the setup instructions for each provider

### Email Templates

1. Go to "Emails" in Clerk dashboard
2. Customize welcome emails, password reset, etc.

## 🔒 Security Best Practices

### Development vs Production

**Development (test keys):**
- Use `pk_test_...` and `sk_test_...`
- Can be reset anytime
- Free unlimited users

**Production (live keys):**
- Use `pk_live_...` and `sk_live_...`
- Never commit to git!
- Use environment variables only

### Environment Variables

**✅ DO:**
- Store keys in `.env.local` (frontend)
- Store keys in `.env` (backend)
- Add `.env*` to `.gitignore`
- Use different keys for dev/prod

**❌ DON'T:**
- Commit keys to git
- Share keys publicly
- Use production keys in development
- Hardcode keys in source code

## 🧪 Testing

### Test User Flow

1. **Sign Up:**
   - Go to http://localhost:3000
   - Click "Sign Up"
   - Enter email and password
   - Verify email (check inbox)

2. **Sign In:**
   - Go to http://localhost:3000
   - Click "Sign In"
   - Enter credentials
   - Should redirect to dashboard

3. **User Profile:**
   - Check if user ID is consistent
   - Verify user data is stored in database

### Verify Integration

```bash
# Check if Clerk is working
curl http://localhost:3000/api/auth/me

# Should return user data if logged in
```

## 🐛 Troubleshooting

### "Clerk: Missing publishable key"

**Problem:** Frontend can't find Clerk key

**Solution:**
1. Check `.env.local` exists in `cua-frontend/`
2. Verify key starts with `NEXT_PUBLIC_`
3. Restart Next.js dev server

### "Invalid API key"

**Problem:** Wrong or expired key

**Solution:**
1. Go to Clerk dashboard → API Keys
2. Copy fresh keys
3. Update `.env.local` and `.env`
4. Restart servers

### "User not found in database"

**Problem:** Clerk user not synced to PostgreSQL

**Solution:**
1. Check backend logs: `make logs-backend`
2. Verify database is running: `make prod-status`
3. Check database connection in `.env`

## 📚 Resources

- [Clerk Documentation](https://clerk.com/docs)
- [Next.js Integration](https://clerk.com/docs/quickstarts/nextjs)
- [API Reference](https://clerk.com/docs/reference/backend-api)

## ✅ Checklist

Before going to production:

- [ ] Created Clerk account
- [ ] Created application
- [ ] Got API keys
- [ ] Configured frontend `.env.local`
- [ ] Configured backend `.env`
- [ ] Tested sign up flow
- [ ] Tested sign in flow
- [ ] Verified user data in database
- [ ] Customized theme
- [ ] Set up production keys
- [ ] Configured domain in Clerk dashboard

## 🎉 Done!

Your authentication is now set up! Users can:
- Sign up with email
- Sign in securely
- Have persistent sessions
- Connect their X accounts

Next step: Test the full flow from login → connect X account → import posts!

