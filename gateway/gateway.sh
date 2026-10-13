#!/bin/sh
# Egress gateway for the bot. The app container sits on an internal-only network, so
# this proxy is its only way out. It forwards everything to lanepool through one
# sticky session (one exit IP) and switches to a fresh session when that exit dies.
# It also relays the bot's web UI (file selector) from Traefik to the app.

: "${LANEPOOL_URL:=lanepool:8080}"
: "${LANEPOOL_USER:?LANEPOOL_USER is required}"
: "${LANEPOOL_PASS:?LANEPOOL_PASS is required}"
: "${LANEPOOL_COUNTRY:=}"
: "${SESSION_TTL_MIN:=1440}"
: "${CHECK_INTERVAL:=30}"
: "${MAX_FAILURES:=3}"
: "${WEB_TARGET:=app:80}"

socat TCP-LISTEN:80,fork,reuseaddr "TCP:${WEB_TARGET}" &

glider_pid=""

start_session() {
    session="mltb$(tr -dc 'a-z0-9' </dev/urandom | head -c 10)"
    user="${LANEPOOL_USER}"
    [ -n "$LANEPOOL_COUNTRY" ] && user="${user}-country-${LANEPOOL_COUNTRY}"
    user="${user}-session-${session}-sessttl-${SESSION_TTL_MIN}"
    [ -n "$glider_pid" ] && kill "$glider_pid" 2>/dev/null && wait "$glider_pid" 2>/dev/null
    glider -listen "mixed://:1080" -forward "http://${user}:${LANEPOOL_PASS}@${LANEPOOL_URL}" &
    glider_pid=$!
    sleep 2
    ip=$(curl -s -m 20 -x socks5h://127.0.0.1:1080 https://api.ipify.org)
    echo "[gateway] session ${session} -> exit IP ${ip:-unknown}"
}

start_session
failures=0
while true; do
    sleep "$CHECK_INTERVAL"
    if ! kill -0 "$glider_pid" 2>/dev/null; then
        echo "[gateway] glider exited, starting a new session"
        start_session; failures=0; continue
    fi
    if curl -s -m 20 -o /dev/null -x socks5h://127.0.0.1:1080 https://api.ipify.org; then
        failures=0
    else
        failures=$((failures + 1))
        echo "[gateway] exit check failed (${failures}/${MAX_FAILURES})"
        if [ "$failures" -ge "$MAX_FAILURES" ]; then
            echo "[gateway] exit is dead, switching to a new session"
            start_session; failures=0
        fi
    fi
done
