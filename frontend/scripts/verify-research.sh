#!/bin/bash
# Start Vite + run Agent Browser against the SPA.
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

echo "=== Open login page ==="
agent-browser open http://localhost:3000/login 2>&1 | tail -3
sleep 1
agent-browser snapshot -i 2>&1 | head -20

echo ""
echo "=== Try submitting empty form (should show validation errors) ==="
agent-browser snapshot -i 2>&1 | grep -E "textbox|button" | head -5

echo ""
echo "=== Fill the form with bogus creds ==="
agent-browser fill @e3 "fakeuser" 2>&1 | tail -2
agent-browser fill @e4 "fakepass" 2>&1 | tail -2
agent-browser click @e5 2>&1 | tail -2
sleep 3

echo ""
echo "=== Snapshot after submit (expect network error alert) ==="
agent-browser snapshot 2>&1 | head -50

echo ""
echo "=== Errors ==="
agent-browser errors 2>&1 | head -10

echo ""
echo "=== Screenshot ==="
agent-browser screenshot /home/z/my-project/download/login-error-state.png 2>&1 | tail -3

echo ""
echo "=== Navigate to /research/backtests (should redirect to /login) ==="
agent-browser open http://localhost:3000/research/backtests 2>&1 | tail -3
sleep 2
agent-browser snapshot -i 2>&1 | head -10
agent-browser get url 2>&1 | tail -2

# Kill vite
kill $VITE_PID 2>/dev/null
wait $VITE_PID 2>/dev/null
echo ""
echo "Vite stopped"
