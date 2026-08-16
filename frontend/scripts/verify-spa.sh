#!/bin/bash
# Start Vite, wait for ready, run agent-browser checks, then kill.
set +e

cd /home/z/my-project

# Start Vite in background
npm run dev > /tmp/vite.log 2>&1 &
VITE_PID=$!
echo "Started vite PID=$VITE_PID"

# Wait up to 30s for vite to be ready
for i in $(seq 1 60); do
  if curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/ 2>/dev/null | grep -q "200"; then
    echo "Vite ready after ${i}s"
    break
  fi
  sleep 0.5
done

# Snapshot
echo "=== Agent Browser snapshot ==="
agent-browser open http://localhost:3000/ 2>&1 | tail -3
sleep 1
agent-browser snapshot -i 2>&1 | head -60

echo "=== Errors ==="
agent-browser errors 2>&1 | head -20

echo "=== Console ==="
agent-browser console 2>&1 | head -20

# Screenshot to download dir
echo "=== Screenshot ==="
agent-browser screenshot /home/z/my-project/download/login-page.png 2>&1 | tail -3

# Kill Vite
kill $VITE_PID 2>/dev/null
wait $VITE_PID 2>/dev/null
echo "Vite stopped"
