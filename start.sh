if [ -n "$VPN_INTERFACE" ]; then
    echo "Waiting for VPN interface $VPN_INTERFACE..."
    for i in $(seq 1 60); do
        [ -e "/sys/class/net/$VPN_INTERFACE" ] && break
        sleep 1
    done
    if [ ! -e "/sys/class/net/$VPN_INTERFACE" ]; then
        echo "VPN interface $VPN_INTERFACE not found, refusing to start without VPN!"
        exit 1
    fi
fi
if [ -n "$RCLONE_CONF_B64" ]; then
    echo "$RCLONE_CONF_B64" | base64 -d > rclone.conf
fi
source mltbenv/bin/activate
python3 update.py
python3 -m bot
