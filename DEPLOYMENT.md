# 🚀 TwinAI Deployment Guide

This guide walks you through deploying TwinAI to production using **Vercel** for the Next.js Frontend and **Render** (or **Railway**) for the FastAPI Backend.

---

## 📋 Architecture Overview

- **Frontend**: Next.js 16 + React 19 deployed on **Vercel** (Global Edge CDN, automatic HTTPS).
- **Backend**: FastAPI + Python 3.11 containerized with Docker (includes FFmpeg and audio processing) deployed on **Render** or **Railway**.
- **AI Services**: Groq API (Whisper STT & LLM evaluations).

---

## 🛠️ Step 1: Deploy Backend to Render (or Railway)

### Option A: Render (Recommended - Free Tier Available)

1. **Sign Up / Log In**:
   - Go to [render.com](https://render.com) and log in with your GitHub account.

2. **Create New Web Service**:
   - Click **New +** > **Web Service**.
   - Select **Build and deploy from a Git repository**.
   - Connect your GitHub repository: `Sumanthkumark05/Ai-Communication-Coach`.

3. **Configure Service**:
   - **Name**: `ai-communication-coach-backend`
   - **Root Directory**: `backend`
   - **Runtime**: **Docker** (Render will automatically detect `backend/Dockerfile`)
   - **Instance Type**: **Free** (or Starter)

4. **Add Environment Variables**:
   Click **Advanced** > **Add Environment Variable** and add:
   | Key | Value / Note |
   |-----|--------------|
   | `GROQ_API_KEY` | *Your Groq API Key (`gsk_...`)* |
   | `GROQ_MODEL` | `llama-3.3-70b-versatile` |
   | `TOPIC_GENERATOR_MODEL` | `llama-3.3-70b-versatile` |
   | `SECRET_KEY` | *(Click "Generate" or enter a secure 32+ character random string)* |
   | `DATABASE_URL` | `sqlite:///./jam_analyzer.db` (or a PostgreSQL URL like Supabase/Neon) |
   | `ALLOWED_ORIGINS` | `https://*.vercel.app` |

5. **Deploy**:
   - Click **Create Web Service**.
   - Wait 2–3 minutes for the Docker image to build.
   - Once deployed, copy your backend URL (e.g., `https://ai-communication-coach-backend.onrender.com`).
   - Test it by opening `https://<YOUR-RENDER-BACKEND-URL>/health` in your browser. You should see `{"status":"ok"}`.

---

### Option B: Railway

1. Go to [railway.app](https://railway.app) and sign in with GitHub.
2. Click **New Project** > **Deploy from GitHub repo** > choose `Ai-Communication-Coach`.
3. In service settings:
   - Set **Root Directory** to `/backend`.
   - Under **Variables**, add:
     - `GROQ_API_KEY`: *Your Groq API key*
     - `GROQ_MODEL`: `llama-3.3-70b-versatile`
     - `SECRET_KEY`: *Random secure string*
     - `ALLOWED_ORIGINS`: `https://*.vercel.app`
4. Under **Networking**, click **Generate Domain** to get your public backend URL.

---

## 🌐 Step 2: Deploy Frontend to Vercel

1. **Sign Up / Log In**:
   - Go to [vercel.com](https://vercel.com) and sign in with your GitHub account.

2. **Import Project**:
   - Click **Add New...** > **Project**.
   - Select your repository: `Sumanthkumark05/Ai-Communication-Coach`.

3. **Configure Project Settings**:
   - **Framework Preset**: **Next.js**
   - **Root Directory**: Click **Edit** and select `frontend` (Important!).
   - **Build Command**: `npm run build` (default)
   - **Output Directory**: `.next` (default)

4. **Set Environment Variables**:
   Add the following environment variable:
   | Key | Value |
   |-----|-------|
   | `NEXT_PUBLIC_API_URL` | `https://<YOUR-RENDER-BACKEND-URL>` (e.g., `https://ai-communication-coach-backend.onrender.com`) |

   > **Note**: Do not include a trailing slash in the URL.

5. **Deploy**:
   - Click **Deploy**.
   - In ~60 seconds, your site will be live at `https://<your-project>.vercel.app`!

---

## 🔒 Step 3: Verify CORS & Link Frontend to Backend

1. In your **Render** (or Railway) backend settings:
   - Check `ALLOWED_ORIGINS`.
   - It is already pre-configured to allow any `https://*.vercel.app` domain automatically.
   - If you add a custom domain (e.g. `https://mycoachingapp.com`), add it to `ALLOWED_ORIGINS` in Render.

2. Open your live Vercel URL in your browser:
   - Try registering a test user.
   - Test the **JAM Analyzer**, **Document Analyzer**, **Interview Simulator**, or **Debate Arena**.
   - Inspect the browser console (`F12`) to confirm requests are reaching your backend smoothly.

---

## 🐳 Optional: Self-Hosting with Docker Compose

If you have your own VPS (Ubuntu, Debian, DigitalOcean Droplet, AWS EC2):

```bash
# 1. Clone repository
git clone https://github.com/Sumanthkumark05/Ai-Communication-Coach.git
cd Ai-Communication-Coach

# 2. Set environment variables in .env
echo "GROQ_API_KEY=your_key_here" >> .env
echo "SECRET_KEY=$(openssl rand -hex 32)" >> .env

# 3. Build and launch services
docker compose up -d --build
```
The services will be accessible at:
- Frontend: `http://<your-server-ip>:3000`
- Backend API: `http://<your-server-ip>:8000`
- API Docs: `http://<your-server-ip>:8000/docs`
