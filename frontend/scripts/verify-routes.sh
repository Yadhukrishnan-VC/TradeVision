#!/bin/bash
# End-to-end SPA verification across multiple routes.
set +e
cd /home/z/my-project

npm run dev > /tmp/vite.log 2>&1 &
VITE_PID=$!
echo "Started vite PID=$VITE_PID"

for i in $(seq 1 60); do
  if curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/ 2>/dev/null | grep -q "200"; then
    echo "Vite ready after ${i}s"
    break
  fi
  sleep 0.5
done

# 1. Login page
echo "=== 1. Login page ==="
agent-browser open http://localhost:3000/login 2>&1 | tail -2
sleep 1
agent-browser snapshot -i 2>&1 | head -10

# 2. Try to access /research/backtests while unauthenticated → should redirect to /login
echo ""
echo "=== 2. Unauthenticated /research/backtests (expect redirect to /login) ==="
agent-browser open http://localhost:3000/research/backtests 2>&1 | tail -2
sleep 2
agent-browser get url 2>&1 | tail -2
agent-browser snapshot -i 2>&1 | head -10

# 3. Try /rules → should redirect to /login
echo ""
echo "=== 3. Unauthenticated /rules (expect redirect to /login) ==="
agent-browser open http://localhost:3000/rules 2>&1 | tail -2
sleep 1
agent-browser get url 2>&1 | tail -2

# 4. Inject fake tokens to simulate a logged-in state, then visit /research/backtests
echo ""
echo "=== 4. Inject fake refresh token + visit /research/backtests ==="
agent-browser storage local set __tv_refresh "fake.refresh.token" 2>&1 | tail -2
agent-browser open http://localhost:3000/research/backtests 2>&1 | tail -2
sleep 3
agent-browser get url 2>&1 | tail -2
agent-browser snapshot -i 2>&1 | head -30

echo ""
echo "=== Errors ==="
agent-browser errors 2>&1 | head -10

echo ""
echo "=== Console ==="
agent-browser console 2>&1 | head -10

# 5. Screenshot for record
echo ""
echo "=== Screenshot ==="
agent-browser screenshot /home/z/my-project/download/research-backtests-page.png 2>&1 | tail -2

# Cleanup
agent-browser storage local clear 2>&1 | tail -2
kill $VITE_PID 2>/dev/null
wait $VITE_PID 2>/dev/null
echo ""
echo "Vite stopped"
