#!/usr/bin/env bash
set -euo pipefail

# pi_wifi_hardening.sh — CSV + batch retries + timestamped failures + rig_number passthrough
#
# - Reads IPs/hosts from -csv FILE (must include header 'IP_address'; case-insensitive)
# - Also reads optional 'rig_number' and preserves it in failures CSV
# - Accepts -ip IP[,IP2...] (repeatable) and positional IPs; all merged and deduped
# - Runs in rounds: 1 full pass; then retries only failures up to --retries N
# - Writes failures to a TIMESTAMPED CSV derived from -out (default base: failures.csv)
#   -> e.g. -out failed_rounds.csv => failed_rounds-YYYYmmdd-HHMMSS.csv
#   Columns: rig_number,IP_address,error
# - Supports -pw PASSWORD via sshpass (insecure). Prefer SSH keys if possible.
# - Generates wpa_supplicant.conf WITHOUT a bssid line unless -b is provided.
# - Installs: (1) cron keepalive ping, (2) power-save-off systemd service,
#             (3) Wi-Fi watchdog script + cron (every 2 minutes).

USER="pi"
PORT=22
BSSID=""              # leave empty by default; only used if -b is supplied
FORCED_GW=""
PASSWORD=""
USE_SSHPASS=0
IPS=()

CSV_IN=""
CSV_OUT="failures.csv"   # base name; timestamp is appended automatically
RETRIES=0

SSID="CrickRig2023"
PSK_HEX="96f0f8f595d0767b19feb325d1c2c8b3d1f28d7cb9edb2f1a3dcc9f23a6f593e"

usage() {
  cat <<USG >&2
Usage: $0 [flags] [-csv FILE] [-ip IP[,IP2...]]... [IP ...]
Flags:
  -u USER       SSH user (default: pi)
  -p PORT       SSH port (default: 22)
  -b BSSID      BSSID to lock onto (optional; if omitted, no lock is written)
  -g GATEWAY    Force keepalive gateway IP (optional)
  -pw PASS      Password for SSH and sudo (uses sshpass; insecure)
  -csv FILE     CSV with header 'IP_address' (case-insensitive); optional 'rig_number'
  -out FILE     Base name for failures CSV (timestamp appended; default: failures.csv)
  --retries N   After first full pass, retry failures up to N more rounds (default: 0)
  -ip IP        One or more IPs/hosts (repeatable or comma-separated)
Notes:
  You may also supply bare IPs/hosts as positional args.
USG
  exit 1
}

# Parse flags (stop on first non-option to allow positional IPs)
while [[ $# -gt 0 ]]; do
  case "$1" in
    -u) USER="$2"; shift 2 ;;
    -p) PORT="$2"; shift 2 ;;
    -b) BSSID="$2"; shift 2 ;;
    -g) FORCED_GW="$2"; shift 2 ;;
    -pw) PASSWORD="$2"; USE_SSHPASS=1; shift 2 ;;
    -csv) CSV_IN="$2"; shift 2 ;;
    -out) CSV_OUT="$2"; shift 2 ;;
    --retries) RETRIES="${2:-}"; [[ -z "$RETRIES" ]] && usage; shift 2 ;;
    -ip)
      [[ -z "${2:-}" ]] && { echo "Missing arg for -ip" >&2; usage; }
      IFS=',' read -r -a more <<< "$2"
      IPS+=("${more[@]}")
      shift 2
      ;;
    -h|--help) usage ;;
    --) shift; break ;;
    -*) echo "Unknown option: $1" >&2; usage ;;
    *) break ;;
  esac
done

# Remaining positional IPs
if [[ $# -gt 0 ]]; then
  for a in "$@"; do IPS+=("$a"); done
fi

# Validate retries as integer >=0
if ! [[ "$RETRIES" =~ ^[0-9]+$ ]]; then
  echo "ERROR: --retries must be a non-negative integer" >&2
  exit 1
fi

# Mapping from IP -> rig_number (blank if unknown)
declare -A RIG_BY_IP

# If -csv, extract IPs and rig_numbers using Python csv (robust header handling)
if [[ -n "$CSV_IN" ]]; then
  [[ -f "$CSV_IN" ]] || { echo "ERROR: CSV not found: $CSV_IN" >&2; exit 1; }
  # Output lines as: IP<TAB>RIG
  mapfile -t csv_pairs < <(python3 - "$CSV_IN" <<'PY'
import sys, csv
fn = sys.argv[1]
want_ip = "ip_address"
opt_rig = "rig_number"
with open(fn, newline='') as f:
    r = csv.reader(f)
    try:
        header = next(r)
    except StopIteration:
        sys.exit(0)
    heads = [h.strip().lower() for h in header]
    if want_ip not in heads:
        sys.stderr.write("CSV headers: {}\n".format(", ".join(header)))
        sys.stderr.write("ERROR: missing 'IP_address' column (case-insensitive)\n")
        sys.exit(2)
    idx_ip = heads.index(want_ip)
    idx_rig = heads.index(opt_rig) if opt_rig in heads else None
    for row in r:
        ip = row[idx_ip].strip() if idx_ip < len(row) else ""
        if not ip or ip.startswith("#"):
            continue
        rig = row[idx_rig].strip() if (idx_rig is not None and idx_rig < len(row)) else ""
        print(ip + "\t" + rig)
PY
)
  pyrc=$?
  if [[ $pyrc -eq 2 ]]; then
    echo "ERROR: CSV missing 'IP_address' column (see headers above)" >&2
    exit 1
  elif [[ $pyrc -ne 0 ]]; then
    echo "ERROR: failed to parse CSV (python exit $pyrc)" >&2
    exit 1
  fi

  # Fill IPS and RIG_BY_IP from csv_pairs
  for line in "${csv_pairs[@]:-}"; do
    ip="${line%%$'\t'*}"
    rig="${line#*$'\t'}"
    IPS+=("$ip")
    RIG_BY_IP["$ip"]="$rig"
  done
fi

# Deduplicate IPs
declare -A seen
unique=()
for ip in "${IPS[@]:-}"; do
  t="$(echo "$ip" | tr -d $'\r' | xargs)" # trim
  [[ -z "$t" ]] && continue
  if [[ -z "${seen[$t]:-}" ]]; then unique+=("$t"); seen[$t]=1; fi
done
IPS=("${unique[@]}")
[[ ${#IPS[@]} -eq 0 ]] && { echo "ERROR: no hosts to process" >&2; usage; }

# If -pw is used, ensure sshpass exists
if [[ $USE_SSHPASS -eq 1 ]]; then
  command -v sshpass >/dev/null 2>&1 || { echo "ERROR: sshpass not found (install it to use -pw)" >&2; exit 1; }
fi

# Build local wpa_supplicant.conf once (conditionally include bssid line)
TMPCONF="$(mktemp)"
trap 'rm -f "$TMPCONF"' EXIT
cat > "$TMPCONF" <<EOF
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=GB

network={
        ssid="${SSID}"
$( [[ -n "${BSSID}" ]] && echo "        bssid=${BSSID}" )
        psk=${PSK_HEX}
        scan_ssid=1
        bgscan=""
}
EOF

# Remote payload as a single heredoc string
REMOTE_PAYLOAD='
set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# Install config
if [ -n "${PASSWORD:-}" ]; then
  printf "%s\n" "$PASSWORD" | sudo -S install -m 600 /tmp/wpa_supplicant.conf /etc/wpa_supplicant/wpa_supplicant.conf
else
  sudo install -m 600 /tmp/wpa_supplicant.conf /etc/wpa_supplicant/wpa_supplicant.conf
fi

# Detect Wi-Fi iface
WIFACE="$(iw dev 2>/dev/null | awk '\''/Interface/ {print $2; exit}'\'')"
if [ -z "$WIFACE" ]; then
  WIFACE="$(for i in /sys/class/net/*; do [ -d "$i/wireless" ] && basename "$i"; done | head -n1)"
fi
[ -z "$WIFACE" ] && { echo "NO_WIFI_IFACE"; exit 2; }
echo "  [INFO] Wireless interface: $WIFACE"

# Reconfigure
if command -v wpa_cli >/dev/null 2>&1; then
  if [ -n "${PASSWORD:-}" ]; then
    printf "%s\n" "$PASSWORD" | sudo -S wpa_cli -i "$WIFACE" reconfigure || true
  else
    sudo wpa_cli -i "$WIFACE" reconfigure || true
  fi
fi
sleep 4
iw dev "$WIFACE" link || true

# Determine gateway
GW="${FORCED_GW:-}"
if [ -z "$GW" ]; then
  for _ in $(seq 1 20); do
    GW="$(ip route | awk -v i="$WIFACE" '\''/^default/ && $0 ~ i {print $3; exit}'\'')"
    [ -n "$GW" ] && break
    sleep 1
  done
fi
[ -z "$GW" ] && { echo "NO_GATEWAY"; exit 3; }

# Install cron keepalive ping (dedupe)
TMPCRON="$(mktemp)"
crontab -l 2>/dev/null > "$TMPCRON" || true
sed -i '\''/ping -c 1 -W 1 .* > \/dev\/null 2>&1/d'\'' "$TMPCRON"
echo "*/5 * * * * ping -c 1 -W 1 $GW > /dev/null 2>&1" >> "$TMPCRON"
crontab "$TMPCRON"
rm -f "$TMPCRON"

# Systemd service to disable power save
cat > /tmp/wifi-powersave-off.service <<UNIT
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

if [ -n "${PASSWORD:-}" ]; then
  printf "%s\n" "$PASSWORD" | sudo -S install -m 644 /tmp/wifi-powersave-off.service /etc/systemd/system/wifi-powersave-off.service
  printf "%s\n" "$PASSWORD" | sudo -S systemctl daemon-reload
  printf "%s\n" "$PASSWORD" | sudo -S systemctl enable --now wifi-powersave-off.service || true
else
  sudo install -m 644 /tmp/wifi-powersave-off.service /etc/systemd/system/wifi-powersave-off.service
  sudo systemctl daemon-reload
  sudo systemctl enable --now wifi-powersave-off.service || true
fi

# Wi-Fi watchdog script (avoids fragile cron one-liners with pipes)
cat > /tmp/wifi-watchdog.sh <<'"'"'WSH'"'"'
#!/bin/sh
set -eu
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
IFACE="$(iw dev 2>/dev/null | awk "/Interface/ {print \$2; exit}")"
[ -z "${IFACE:-}" ] && exit 0
if ! iw dev "$IFACE" link | grep -q "Connected"; then
  if command -v systemctl >/dev/null 2>&1; then
    systemctl restart wpa_supplicant || true
  else
    # Fallback for very old systems
    if pidof wpa_supplicant >/dev/null 2>&1; then
      killall wpa_supplicant || true
    fi
    nohup wpa_supplicant -B -i "$IFACE" -c /etc/wpa_supplicant/wpa_supplicant.conf >/dev/null 2>&1 || true
  fi
fi
WSH

if [ -n "${PASSWORD:-}" ]; then
  printf "%s\n" "$PASSWORD" | sudo -S install -m 755 /tmp/wifi-watchdog.sh /usr/local/sbin/wifi-watchdog.sh
else
  sudo install -m 755 /tmp/wifi-watchdog.sh /usr/local/sbin/wifi-watchdog.sh
fi
rm -f /tmp/wifi-watchdog.sh

# Add/refresh watchdog cron entry (dedupe)
TMPCRON="$(mktemp)"
crontab -l 2>/dev/null > "$TMPCRON" || true
sed -i '\''/\/usr\/local\/sbin\/wifi-watchdog\.sh/d'\'' "$TMPCRON"
echo "*/2 * * * * /usr/local/sbin/wifi-watchdog.sh" >> "$TMPCRON"
crontab "$TMPCRON"
rm -f "$TMPCRON"

iw "$WIFACE" get power_save || true
echo "OK_DONE"
'

# Helpers
upload_conf() {
  local ip="$1"
  if [[ $USE_SSHPASS -eq 1 ]]; then
    sshpass -p "$PASSWORD" scp -o StrictHostKeyChecking=no -P "$PORT" "$TMPCONF" "${USER}@${ip}:/tmp/wpa_supplicant.conf"
  else
    scp -P "$PORT" "$TMPCONF" "${USER}@${ip}:/tmp/wpa_supplicant.conf"
  fi
}

run_remote() {
  local ip="$1"
  if [[ $USE_SSHPASS -eq 1 ]]; then
    sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no -p "$PORT" "${USER}@${ip}" \
      "PASSWORD='${PASSWORD}' FORCED_GW='${FORCED_GW}' bash -s" <<< "$REMOTE_PAYLOAD"
  else
    ssh -p "$PORT" "${USER}@${ip}" "FORCED_GW='${FORCED_GW}' bash -s" <<< "$REMOTE_PAYLOAD"
  fi
}

# Process a single host; echo a status token we can parse: "OK" or an ERROR CODE string
process_host() {
  local ip="$1"
  # Upload
  if ! upload_conf "$ip" >/dev/null 2>&1; then
    echo "SCP_ERROR"
    return
  fi
  # Run remote and capture output
  local out rc
  out="$(run_remote "$ip" 2>&1)" ; rc=$?
  if [[ $rc -ne 0 ]]; then
    if grep -q "NO_WIFI_IFACE" <<<"$out"; then
      echo "NO_WIFI_INTERFACE"
    elif grep -q "NO_GATEWAY" <<<"$out"; then
      echo "NO_WIFI_GATEWAY"
    else
      # Return last lines to help debugging
      echo "REMOTE_FAIL:$(echo "$out" | tail -n 5 | tr $'\n' ' ' | sed 's/\"/\"\"/g')"
    fi
  else
    if grep -q "OK_DONE" <<<"$out"; then
      echo "OK"
    else
      echo "REMOTE_UNKNOWN"
    fi
  fi
}

# Batch runner with retries-after-full-pass
declare -A last_error
rounds=$((RETRIES + 1))
to_process=( "${IPS[@]}" )

for (( round=1; round<=rounds; round++ )); do
  [[ ${#to_process[@]} -eq 0 ]] && break
  echo ""
  echo "===== ROUND ${round}/${rounds} ====="
  next_fail=()

  for ip in "${to_process[@]}"; do
    echo "---- ${USER}@${ip} ----"
    status="$(process_host "$ip")"
    if [[ "$status" == "OK" ]]; then
      echo "  [PASS]"
      unset 'last_error["$ip"]' || true
    else
      echo "  [FAIL] ${status}"
      last_error["$ip"]="$status"
      next_fail+=( "$ip" )
    fi
  done

  # Prepare for next round: retry only failures
  to_process=( "${next_fail[@]}" )
done

# Build final failures list from last_error map
fail_ips=()
for ip in "${!last_error[@]}"; do fail_ips+=( "$ip" ); done

# Compose timestamped output path from CSV_OUT base
TS="$(date +%Y%m%d-%H%M%S)"
# If CSV_OUT has extension, insert timestamp before it; else append .csv
base="${CSV_OUT%.*}"
ext="${CSV_OUT##*.}"
if [[ "$base" == "$CSV_OUT" ]]; then
  # no extension
  OUT_PATH="${CSV_OUT}-${TS}.csv"
else
  OUT_PATH="${base}-${TS}.${ext}"
fi

if [[ ${#fail_ips[@]} -gt 0 ]]; then
  # Overwrite output file (timestamped)
  echo "rig_number,IP_address,error" > "$OUT_PATH"
  # Sort for stable order (if sort exists)
  if command -v sort >/dev/null 2>&1; then
    printf "%s\n" "${fail_ips[@]}" | sort | while read -r ip; do
      rig="${RIG_BY_IP[$ip]:-}"
      echo "${rig},${ip},${last_error[$ip]}"
    done >> "$OUT_PATH"
  else
    for ip in "${fail_ips[@]}"; do
      rig="${RIG_BY_IP[$ip]:-}"
      echo "${rig},${ip},${last_error[$ip]}" >> "$OUT_PATH"
    done
  fi
  echo ""
  echo "Done. ${#fail_ips[@]} host(s) failed after ${rounds} round(s)."
  echo "Failures written to: $OUT_PATH"
else
  echo ""
  echo "Done. All hosts succeeded in ${rounds} round(s)."
fi
