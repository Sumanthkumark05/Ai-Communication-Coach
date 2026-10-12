#!/bin/bash

# Ensure local binaries (node, npm, uv) are in PATH
export PATH="$HOME/.local/bin:$PATH"

# Port definitions
FRONTEND_PORT=3000
BACKEND_PORT=8000

echo "=== JAM AI Analyzer Startup Script ==="

# 1. Kill any existing processes on ports 3000 or 8000
echo "Checking port availability..."

# Detect old next/node processes
echo "Cleaning up any stale node or next development processes..."
pkill -f "next-dev" 2>/dev/null
pkill -f "next-server" 2>/dev/null
pkill -f "node dev-server.js" 2>/dev/null

echo "Checking for processes on port $FRONTEND_PORT..."
FRONTEND_PID=$(lsof -t -i :$FRONTEND_PORT 2>/dev/null)
if [ ! -z "$FRONTEND_PID" ]; then
    echo "Port $FRONTEND_PORT occupied."
    echo "Found process:"
    lsof -i :$FRONTEND_PORT
    echo "Attempting to clean up stale process (PID: $FRONTEND_PID)..."
    kill -9 $FRONTEND_PID 2>/dev/null
    sleep 1
    # Check if port is still occupied
    STILL_FRONTEND_PID=$(lsof -t -i :$FRONTEND_PORT 2>/dev/null)
    if [ ! -z "$STILL_FRONTEND_PID" ]; then
        echo "Warning: Port $FRONTEND_PORT remains occupied (PID: $STILL_FRONTEND_PID). Switching to available fallback port."
    else
        echo "Stale process cleaned up successfully on port $FRONTEND_PORT."
    fi
else
    echo "Port $FRONTEND_PORT is free."
fi

echo "Checking for processes on port $BACKEND_PORT..."
BACKEND_PID=$(lsof -t -i :$BACKEND_PORT 2>/dev/null)
if [ ! -z "$BACKEND_PID" ]; then
    echo "Port $BACKEND_PORT occupied."
    echo "Found process:"
    lsof -i :$BACKEND_PORT
    echo "Killing process(es) $BACKEND_PID on port $BACKEND_PORT..."
    kill -9 $BACKEND_PID 2>/dev/null
else
    echo "Port $BACKEND_PORT is free."
fi

# 2. Check for port 3001 (fallback port) just in case
echo "Checking for processes on port 3001..."
PORT_3001_PID=$(lsof -t -i :3001 2>/dev/null)
if [ ! -z "$PORT_3001_PID" ]; then
    echo "Killing process(es) $PORT_3001_PID on port 3001..."
    kill -9 $PORT_3001_PID 2>/dev/null
fi

# 3. Start Backend
echo "Starting Backend server (FastAPI)..."
# Make sure virtual environment exists and is used
if [ -d "backend/venv" ]; then
    cd backend
    PYTHONPATH=. ./venv/bin/uvicorn main:app --host 0.0.0.0 --port $BACKEND_PORT > uvicorn.log 2>&1 &
    BACKEND_STARTED_PID=$!
    echo "Backend started in background (PID: $BACKEND_STARTED_PID). Log at backend/uvicorn.log"
    cd ..
else
    echo "ERROR: Virtual environment not found in backend/venv."
    exit 1
fi

# 4. Start Frontend
echo "Starting Frontend server (Next.js)..."
if [ -d "frontend" ]; then
    cd frontend
    npm run dev > next-dev.log 2>&1 &
    FRONTEND_STARTED_PID=$!
    echo "Frontend started in background (PID: $FRONTEND_STARTED_PID). Log at frontend/next-dev.log"
    cd ..
else
    echo "ERROR: frontend directory not found."
    exit 1
fi

# 5. Health Check Wait
echo "Waiting 5 seconds for services to boot up..."
sleep 5

# Check if processes are still running
if ps -p $BACKEND_STARTED_PID > /dev/null 2>&1; then
    echo "Backend (PID: $BACKEND_STARTED_PID) is running on port $BACKEND_PORT."
else
    echo "Backend failed to start. Last log entries from backend/uvicorn.log:"
    tail -n 15 backend/uvicorn.log
fi

if ps -p $FRONTEND_STARTED_PID > /dev/null 2>&1; then
    echo "Frontend (PID: $FRONTEND_STARTED_PID) is running on port $FRONTEND_PORT."
else
    echo "Frontend failed to start. Last log entries from frontend/next-dev.log:"
    tail -n 15 frontend/next-dev.log
fi

echo "Startup complete!"
