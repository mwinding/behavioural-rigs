#!/usr/bin/env bash
set -euo pipefail

# pi_wifi_hardening.sh
#
# Same behavior as before but supports a -pw PASSWORD flag to run non-interactively.
# SECURITY: passing passwords on the command line is insecure. Prefer SSH keys.

USER="pi"
PORT=22
BSSID="74:9e:75:29:b6:00"
FORCED_GW=""
PASSWORD=""
USE_SSHPASS=0
IPS=()

# Your SSID and precomputed (hex) PSK
SSID="CrickRig2023"
PSK_HEX="96f0f8f595d0767b19feb325d1c2c8b3d1f28d7cb9edb2f1a3dcc9f23a6f593e"

usage() {
  cat <<USG >&2
Usage: $0 [-u USER] [-p PORT] [-b BSSID] [-g GATEWAY] [-pw PASSWORD] -ip IP[,IP2...] [-ip IP3 ...]
  -u USER    SSH user (default: pi)
  -p PORT    SSH port (default: 22)
  -b BSSID   BSSID to lock the network block to (default provided)
  -g GATEWAY Force gateway IP for keepalive (optional)
  -pw PASS   Password to use for SSH and sudo (insecure; prefer SSH keys)
  -ip IP     One or more IPs/hostnames (repeatable or comma-separated)
USG
  exit 1
}

# Parse args
while [[ $# -gt 0 ]]; do
  case "$1" in
    -u) USER="$2"; shift 2 ;;
    -p) PORT="$2"; shift 2 ;;
    -b) BSSID="$2"; shift 2 ;;
    -g) FORCED_GW="$2"; shift 2 ;;
    -pw) PASSWORD="$2"; USE_SSHPASS=1; shift 2 ;;
    -ip)
      IFS=',' read -r -a more <<< "$2"
      IPS+=("${more[@]}")
      shift 2
      ;;
    -h|--help) usage ;;
    *) echo "Unknown option: $1" >&2; usage ;;
  esac
done
[[ ${#IPS[@]} -eq 0 ]] && usage

# If password supplied, require sshpass binary on local machine
if [[ $USE_SSHPASS -eq 1 ]]; then
  if ! command -v sshpass >/dev/null 2>&1; then
    echo "ERROR: sshpass not found. Install it (e.g. 'brew install hudochenkov/sshpass/sshpass' on macOS or 'sudo apt install sshpass' on Linux)" >&2
    exit 1
  fi
fi

# Helper: run scp (with or without sshpass)
scp_to_host() {
  local src="$1" dst_user="$2" dst_host="$3" dst_path="$4"
  if [[ $USE_SSHPASS -eq 1 ]]; then
    sshpass -p "$PASSWORD" scp -o StrictHostKeyChecking=no -P "$PORT" "$src" "${dst_user}@${dst_host}:${dst_path}"
  else
    scp -P "$PORT" "$src" "${dst_user}@${dst_host}:${dst_path}"
  fi
}

# Helper: run ssh with either sshpass or direct ssh, passing PASSWORD in env if set
ssh_run_host() {
  local user="$1" host="$2" remote_cmd="$3"
  if [[ $USE_SSHPASS -eq 1 ]]; then
    # pass PASSWORD env var to remote shell so remote can pipe it into sudo -S
    sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no -p "$PORT" "${user}@${host}" "PASSWORD='\$PASSWORD' bash -s" <<'REMOTE'
# This placeholder will be replaced by the caller's remote payload via heredoc injection.
REMOTE
    # Note: we never call this helper directly with a command string; we call sshpass/ssh inline below to avoid quoting complexity.
  else
    ssh -p "$PORT" "${user}@${host}" "$remote_cmd"
  fi
}

# Build local wpa_supplicant.conf file
TMPCONF="$(mktemp)"
trap 'rm -f "$TMPCONF"' EXIT
cat > "$TMPCONF" <<EOF
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=GB

network={
        ssid="${SSID}"
        bssid=${BSSID}
        psk=${PSK_HEX}
        scan_ssid=1
        bgscan=""
}
EOF

# Iterate hosts
for IP in "${IPS[@]}"; do
  echo "==== ${USER}@${IP} ===="

  # Upload config
  if [[ $USE_SSHPASS -eq 1 ]]; then
    sshpass -p "$PASSWORD" scp -o StrictHostKeyChecking=no -P "$PORT" "$TMPCONF" "${USER}@${IP}:/tmp/wpa_supplicant.conf"
  else
    scp -P "$PORT" "$TMPCONF" "${USER}@${IP}:/tmp/wpa_supplicant.conf"
  fi

  # Run the remote payload. We'll send PASSWORD as an env var when using sshpass (so remote can use it).
  if [[ $USE_SSHPASS -eq 1 ]]; then
    # Use sshpass+ssh: pass PASSWORD in the remote environment for sudo -S usage.
    sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no -p "$PORT" "${USER}@${IP}" \
      "PASSWORD='${PASSWORD}' bash -s" <<'REMOTE_PAYLOAD'
set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# Install the wpa_supplicant.conf as root (use sudo -S fed by PASSWORD)
if [ -n "${PASSWORD:-}" ]; then
  printf "%s\n" "$PASSWORD" | sudo -S install -m 600 /tmp/wpa_supplicant.conf /etc/wpa_supplicant/wpa_supplicant.conf
else
  sudo install -m 600 /tmp/wpa_supplicant.conf /etc/wpa_supplicant/wpa_supplicant.conf
fi

# Detect wifi interface
WIFACE="$(iw dev 2>/dev/null | awk '/Interface/ {print $2; exit}')"
if [ -z "$WIFACE" ]; then
  WIFACE="$(for i in /sys/class/net/*; do [ -d "$i/wireless" ] && basename "$i"; done | head -n1)"
fi
[ -z "$WIFACE" ] && { echo "  [ERR] No wireless interface found."; exit 1; }
echo "  [INFO] Wireless interface: $WIFACE"

# Reconfigure wpa_supplicant
if command -v wpa_cli >/dev/null 2>&1; then
  if [ -n "${PASSWORD:-}" ]; then
    printf "%s\n" "$PASSWORD" | sudo -S wpa_cli -i "$WIFACE" reconfigure || true
  else
    sudo wpa_cli -i "$WIFACE" reconfigure || true
  fi
fi
sleep 4
iw dev "$WIFACE" link || true

# Choose gateway (FORCED_GW may be empty)
GW="${FORCED_GW:-}"
if [ -z "$GW" ]; then
  for _ in $(seq 1 20); do
    GW="$(ip route | awk -v i="$WIFACE" '/^default/ && $0 ~ i {print $3; exit}')"
    [ -n "$GW" ] && break
    sleep 1
  done
fi

echo "  [INFO] Wi-Fi gateway candidate: ${GW:-<none>}"
if [ -n "$GW" ]; then
  TMPCRON="$(mktemp)"
  crontab -l 2>/dev/null > "$TMPCRON" || true
  sed -i '/ping -c 1 -W 1 .* > \/dev\/null 2>&1/d' "$TMPCRON"
  echo "*/5 * * * * ping -c 1 -W 1 $GW > /dev/null 2>&1" >> "$TMPCRON"
  crontab "$TMPCRON"
  rm -f "$TMPCRON"
  echo "  [OK] Keepalive cron installed for $GW"
else
  echo "  [WARN] No Wi-Fi default route yet; cron skipped."
fi

# Create a temporary systemd unit then install it with sudo -S if needed
cat > /tmp/wifi-powersave-off.service <<'UNIT'
[Unit]
Description=Disable WiFi power saving
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/sbin/iw dev __WIFACE__ set power_save off

[Install]
WantedBy=multi-user.target
UNIT

# Replace placeholder with actual iface
sed -i "s/__WIFACE__/$WIFACE/g" /tmp/wifi-powersave-off.service

if [ -n "${PASSWORD:-}" ]; then
  printf "%s\n" "$PASSWORD" | sudo -S install -m 644 /tmp/wifi-powersave-off.service /etc/systemd/system/wifi-powersave-off.service
  printf "%s\n" "$PASSWORD" | sudo -S systemctl daemon-reload
  printf "%s\n" "$PASSWORD" | sudo -S systemctl enable --now wifi-powersave-off.service || true
else
  sudo install -m 644 /tmp/wifi-powersave-off.service /etc/systemd/system/wifi-powersave-off.service
  sudo systemctl daemon-reload
  sudo systemctl enable --now wifi-powersave-off.service || true
fi

# Report current power save state (non-root)
iw "$WIFACE" get power_save || true
REMOTE_PAYLOAD

  else
    # No password: normal scp + ssh, assumes SSH keys or interactive password entry (user may be prompted)
    scp -P "$PORT" "$TMPCONF" "${USER}@${IP}:/tmp/wpa_supplicant.conf"
    ssh -p "$PORT" "${USER}@${IP}" bash -s <<'REMOTE_PAYLOAD_NO_PW'
set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

sudo install -m 600 /tmp/wpa_supplicant.conf /etc/wpa_supplicant/wpa_supplicant.conf

WIFACE="$(iw dev 2>/dev/null | awk '/Interface/ {print $2; exit}')"
if [ -z "$WIFACE" ]; then
  WIFACE="$(for i in /sys/class/net/*; do [ -d "$i/wireless" ] && basename "$i"; done | head -n1)"
fi
[ -z "$WIFACE" ] && { echo "  [ERR] No wireless interface found."; exit 1; }
echo "  [INFO] Wireless interface: $WIFACE"

if command -v wpa_cli >/dev/null 2>&1; then
  sudo wpa_cli -i "$WIFACE" reconfigure || true
fi
sleep 4
iw dev "$WIFACE" link || true

GW="${FORCED_GW:-}"
if [ -z "$GW" ]; then
  for _ in $(seq 1 20); do
    GW="$(ip route | awk -v i="$WIFACE" '/^default/ && $0 ~ i {print $3; exit}')"
    [ -n "$GW" ] && break
    sleep 1
  done
fi

echo "  [INFO] Wi-Fi gateway candidate: ${GW:-<none>}"
if [ -n "$GW" ]; then
  TMPCRON="$(mktemp)"
  crontab -l 2>/dev/null > "$TMPCRON" || true
  sed -i '/ping -c 1 -W 1 .* > \/dev\/null 2>&1/d' "$TMPCRON"
  echo "*/5 * * * * ping -c 1 -W 1 $GW > /dev/null 2>&1" >> "$TMPCRON"
  crontab "$TMPCRON"
  rm -f "$TMPCRON"
  echo "  [OK] Keepalive cron installed for $GW"
else
  echo "  [WARN] No Wi-Fi default route yet; cron skipped."
fi

cat > /tmp/wifi-powersave-off.service <<'UNIT'
[Unit]
Description=Disable WiFi power saving
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/sbin/iw dev __WIFACE__ set power_save off

[Install]
WantedBy=multi-user.target
UNIT

sed -i "s/__WIFACE__/$WIFACE/g" /tmp/wifi-powersave-off.service
sudo install -m 644 /tmp/wifi-powersave-off.service /etc/systemd/system/wifi-powersave-off.service
sudo systemctl daemon-reload
sudo systemctl enable --now wifi-powersave-off.service || true

iw "$WIFACE" get power_save || true
REMOTE_PAYLOAD_NO_PW
  fi

done

echo "All targets processed."
