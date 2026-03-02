#!/bin/bash

# ------------------------------
# Update Static Sitemap (append new URLs)
# ------------------------------
REMOTE_USER="root"
REMOTE_HOST="23.95.208.117"
REMOTE_PASS="admin123Pw"
REMOTE_PATH="/home/paycc.store/public_html"
SITEMAP_FILE="sitemap.xml"
DATE=$(date "+%Y-%m-%d %H:%M:%S")
LOG_FILE="$HOME/update_sitemap.log"

# Accept URLs as arguments
NEW_URLS=("$@")

echo "[$DATE] Starting sitemap update..." | tee -a "$LOG_FILE"

# Prepare URLs to send line by line
URL_LINES=$(printf "%s\n" "${NEW_URLS[@]}")

sshpass -p "$REMOTE_PASS" ssh -o StrictHostKeyChecking=no "${REMOTE_USER}@${REMOTE_HOST}" bash << EOF
cd "$REMOTE_PATH" || { echo "Directory $REMOTE_PATH not found"; exit 1; }

# Read existing URLs from sitemap
EXISTING_URLS=()
if [ -f "$SITEMAP_FILE" ]; then
    EXISTING_URLS=(\$(grep -oP '(?<=<loc>).*?(?=</loc>)' "$SITEMAP_FILE"))
fi

# Read new URLs safely line by line
while IFS= read -r url; do
    if [[ ! " \${EXISTING_URLS[@]} " =~ " \$url " ]]; then
        EXISTING_URLS+=("\$url")
    fi
done << 'URL_INPUT'
$URL_LINES
URL_INPUT

# Rebuild sitemap with all URLs
echo '<?xml version="1.0" encoding="UTF-8"?>' > "$SITEMAP_FILE"
echo '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' >> "$SITEMAP_FILE"

for url in "\${EXISTING_URLS[@]}"; do
    echo "  <url><loc>\$url</loc><lastmod>\$(date +%Y-%m-%d)</lastmod></url>" >> "$SITEMAP_FILE"
done

echo '</urlset>' >> "$SITEMAP_FILE"
EOF

echo "[$DATE] Sitemap update finished." | tee -a "$LOG_FILE"
