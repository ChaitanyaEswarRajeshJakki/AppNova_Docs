# Deploy to Azure VM (Ubuntu) — Zero-Regression Production Runbook

_Target: Azure Linux VM (Ubuntu 22.04 LTS) + Azure SQL Database (= `dw` in your source input). Stack: .NET 8 backend + React frontend. Every command is copy-paste ready. Every section ends with a **"did it work?"** check. If any check fails, do **not** move on._

---

## Conventions used below

Replace these placeholders with your real values exactly once and reuse:

| Placeholder | Example | Where to get it |
|---|---|---|
| `<vm-ip>` | `20.120.55.142` | Azure Portal → your VM → Overview → Public IP address |
| `<vm-user>` | `azureuser` | The admin username you set when creating the VM |
| `<domain>` | `aries.example.com` | Your DNS A-record pointing at `<vm-ip>` |
| `<app-name>` | `aries` | Short kebab-case name; used for paths and systemd unit |
| `<dotnet-dll>` | `ARIES.Api.dll` | Filename of your published .NET entry assembly |
| `<sql-server>` | `sql-aries-prod.database.windows.net` | Azure Portal → your SQL server → Server name |
| `<sql-db>` | `aries-prod` | Azure Portal → your SQL DB → Database name |
| `<sql-user>` | `sqladmin` | SQL admin login from when the server was created |
| `<sql-password>` | `…` | Paste only into the env file, never into commands |
| `<vault-name>` | `kv-aries-prod` | Azure Portal → your Key Vault → Overview |

Do this once at the top of your terminal to avoid typos later:

```bash
export APP_NAME=aries
export VM_USER=azureuser
export VM_IP=20.120.55.142
export DOMAIN=aries.example.com
export SQL_SERVER=sql-aries-prod.database.windows.net
export SQL_DB=aries-prod
export SQL_USER=sqladmin
export VAULT_NAME=kv-aries-prod
```

---

## Stage 0 — Pre-flight from your laptop (~5 min)

These run on **your laptop**, not on the VM. They prove the ground is safe before you touch production.

### 0.1 — Confirm you can reach the VM

```bash
ping -c 3 $VM_IP            # should reply
ssh $VM_USER@$VM_IP 'hostname && uname -a'
```

✅ **Did it work?** You got the VM's hostname and kernel version.

### 0.2 — Confirm Azure SQL accepts connections from the VM

From your laptop (first), to prove the server is up at all:

```bash
# Install sqlcmd if not present — Ubuntu-on-WSL / macOS / Linux:
curl https://packages.microsoft.com/keys/microsoft.asc | sudo apt-key add -
curl https://packages.microsoft.com/config/ubuntu/22.04/prod.list | sudo tee /etc/apt/sources.list.d/mssql.list
sudo apt update && sudo ACCEPT_EULA=Y apt install -y mssql-tools18 unixodbc-dev

sqlcmd -S "$SQL_SERVER" -d "$SQL_DB" -U "$SQL_USER" -G -Q "SELECT @@VERSION"
# -G = use Azure AD auth; drop -G and add -P "$SQL_PASSWORD" for SQL auth
```

✅ **Did it work?** SQL Server version string printed.

**If it timed out**: Azure SQL firewall is blocking you. Add a firewall rule:

```bash
az sql server firewall-rule create \
  --resource-group rg-$APP_NAME-prod \
  --server $(echo $SQL_SERVER | cut -d. -f1) \
  --name "allow-my-laptop" \
  --start-ip-address $(curl -sf4 ifconfig.me) \
  --end-ip-address   $(curl -sf4 ifconfig.me)
```

Then also whitelist the VM's outbound IP (see 0.3).

### 0.3 — Whitelist the VM's IP on Azure SQL

```bash
# Get the VM's outbound IP — this is what Azure SQL sees
VM_OUTBOUND=$(ssh $VM_USER@$VM_IP 'curl -sf4 ifconfig.me')
echo "VM outbound IP: $VM_OUTBOUND"

az sql server firewall-rule create \
  --resource-group rg-$APP_NAME-prod \
  --server $(echo $SQL_SERVER | cut -d. -f1) \
  --name "allow-vm-$APP_NAME" \
  --start-ip-address $VM_OUTBOUND \
  --end-ip-address $VM_OUTBOUND
```

Alternatively, enable **"Allow Azure services and resources to access this server"** in the Azure Portal → SQL Server → Networking. Slightly less secure but simpler for demos.

✅ **Did it work?** The firewall rule shows up in `az sql server firewall-rule list --resource-group rg-$APP_NAME-prod --server $(echo $SQL_SERVER | cut -d. -f1) -o table`.

### 0.4 — Run the AppNova audit gate on the release you're about to ship

**This is the critical zero-regression step.** Before you deploy, the release tarball must pass the six AppNova audits or you're shipping known-broken code.

From the converted project folder on your laptop:

```bash
# You should already have these files from the AppNova pipeline:
ls docs/FILE_COVERAGE.md      docs/API_CONTRACT.md
ls docs/UI_BINDING_AUDIT.md   docs/UI_FIDELITY_REPORT.md
ls docs/ROUTE_LINK_CONTRACT.md docs/SEED_COMPLETENESS.md
ls docs/CONTRACT_AUDIT.md
```

Grep for red findings — **every one of these must return zero**:

```bash
# No unmapped source files
grep -c '^| `.*` |.*unmapped' docs/FILE_COVERAGE.md || echo 0

# No missing backend routes (would 404 at runtime)
grep -A1 '^## ❌' docs/API_CONTRACT.md | grep -c '^| `/' || echo 0

# No orphan schema fields (backend columns with no UI)
grep -A3 '^## ❌ Orphan' docs/UI_BINDING_AUDIT.md | grep -c '^| `' || echo 0

# No unbound form controls
grep -A3 '^## ⚠️  Unbound' docs/UI_BINDING_AUDIT.md | grep -c '^| `' || echo 0

# No dead sidebar links
grep -A3 '^## ❌ Dead' docs/ROUTE_LINK_CONTRACT.md | grep -c '^| `' || echo 0

# No thin lookups (empty-dropdown risk)
grep -A3 '^## ❌ Thin' docs/SEED_COMPLETENESS.md | grep -c '^| `' || echo 0

# Contract audit verdict
grep -E 'Overall verdict\s+:\s+(PASS|PARTIAL|FAIL)' docs/CONTRACT_AUDIT.md
```

✅ **Did it work?** Every count above is `0` AND the contract-audit verdict is `PASS`. If `PARTIAL` or `FAIL`, fix those findings before continuing — that's your regression prevention.

### 0.5 — Build the release tarball

Still on your laptop:

```bash
# Clean build
dotnet publish -c Release -o ./publish src/ARIES.Api/ARIES.Api.csproj

# Frontend with production API base
(cd frontend/aries-react && VITE_API_BASE_URL="" npm ci && npm run build)

# Package — exclude dev-only folders
tar -czf $APP_NAME-$(date +%Y%m%d-%H%M%S).tgz \
    --exclude='mock-azure' \
    --exclude='sample-data' \
    --exclude='.env' \
    --exclude='.env.development' \
    --exclude='*.db' \
    publish/ \
    frontend/aries-react/dist/ \
    docs/ \
    README.md DATA_MIGRATION.md DEPLOYMENT.md

# Sanity check: nothing sensitive snuck in
tar -tzf $APP_NAME-*.tgz | grep -E '(\.env|mock-azure|\.db$|sample-data)' && \
    { echo "❌ sensitive files in tarball — fix before uploading"; exit 1; } || \
    echo "✅ tarball is clean"
```

✅ **Did it work?** `"✅ tarball is clean"` printed. File like `aries-20260422-143012.tgz` exists.

### 0.6 — Snapshot the current VM state (rollback point)

If anything goes wrong later, you need to know what was running before you touched it.

```bash
ssh $VM_USER@$VM_IP bash <<'EOF'
mkdir -p ~/snapshots
SNAP=~/snapshots/pre-deploy-$(date +%Y%m%d-%H%M%S).txt
{
  echo "# VM state snapshot $(date -Iseconds)"
  echo "## Disk"
  df -h /
  echo "## Memory"
  free -h
  echo "## Running systemd services"
  systemctl list-units --type=service --state=running | head -40
  echo "## Listening ports"
  ss -tlnp 2>/dev/null
  echo "## nginx config"
  nginx -v 2>&1 || echo "(nginx not installed)"
} > "$SNAP"
echo "Snapshot saved to $SNAP"
EOF
```

✅ **Did it work?** A snapshot file was written under `~/snapshots/` on the VM.

---

## Stage 1 — VM prereqs (first deploy only, ~10 min)

SSH into the VM and run these once. Skip if the VM is already prepared.

```bash
ssh $VM_USER@$VM_IP
```

### 1.1 — Base packages

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y curl ca-certificates gnupg lsb-release \
                    software-properties-common unzip \
                    nginx sqlite3 ufw
```

### 1.2 — .NET 8 runtime (production only — no SDK needed on server)

```bash
wget https://packages.microsoft.com/config/ubuntu/22.04/packages-microsoft-prod.deb \
  -O /tmp/packages-microsoft-prod.deb
sudo dpkg -i /tmp/packages-microsoft-prod.deb
sudo apt update
sudo apt install -y aspnetcore-runtime-8.0

# Verify
dotnet --list-runtimes | grep -q 'Microsoft.AspNetCore.App 8' && echo "✅ ASP.NET 8 runtime OK"
```

**Note on migrations:** the app will run schema migrations on startup via `EnsureCreatedAsync` in dev mode only. For Azure SQL you'll run them explicitly in Stage 3. If you want `dotnet ef database update` on the VM itself, install the SDK too: `sudo apt install -y dotnet-sdk-8.0`. Otherwise keep the VM runtime-only.

### 1.3 — ODBC driver for Azure SQL

```bash
# Microsoft ODBC 18
curl https://packages.microsoft.com/keys/microsoft.asc | \
  sudo gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg
curl https://packages.microsoft.com/config/ubuntu/22.04/prod.list | \
  sudo tee /etc/apt/sources.list.d/mssql-release.list
sudo apt update
sudo ACCEPT_EULA=Y apt install -y msodbcsql18 mssql-tools18

# Path
echo 'export PATH=$PATH:/opt/mssql-tools18/bin' | sudo tee /etc/profile.d/mssql.sh
source /etc/profile.d/mssql.sh
```

### 1.4 — Create the deploy user + layout

```bash
sudo useradd -r -m -d /home/deploy -s /bin/bash deploy || true

sudo mkdir -p /opt/$APP_NAME
sudo chown -R deploy:deploy /opt/$APP_NAME

sudo mkdir -p /var/www/$APP_NAME
sudo chown -R www-data:www-data /var/www/$APP_NAME

sudo mkdir -p /etc/$APP_NAME
sudo chmod 750 /etc/$APP_NAME
sudo chown root:deploy /etc/$APP_NAME
```

### 1.5 — Certbot for TLS

```bash
sudo snap install --classic certbot
sudo ln -sf /snap/bin/certbot /usr/bin/certbot
```

### 1.6 — UFW firewall (don't enable yet — wait until nginx is up)

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
# Enable in Stage 4 AFTER nginx config is verified
```

✅ **Stage 1 did it work?** `dotnet --list-runtimes` shows ASP.NET 8, `sqlcmd -?` prints help, `nginx -v` prints a version, `/opt/$APP_NAME` exists with `deploy:deploy` ownership.

---

## Stage 2 — Upload the release (~2 min)

Run this from **your laptop**, where the tarball was built in Stage 0.5:

```bash
TARBALL=$(ls -t $APP_NAME-*.tgz | head -1)
echo "Uploading $TARBALL ..."
scp "$TARBALL" $VM_USER@$VM_IP:/tmp/
```

Back on the VM:

```bash
ssh $VM_USER@$VM_IP

# Unpack as the deploy user
TARBALL=$(ls -t /tmp/$APP_NAME-*.tgz | head -1)
sudo mv "$TARBALL" /opt/$APP_NAME/release.tgz
sudo chown deploy:deploy /opt/$APP_NAME/release.tgz

sudo -u deploy bash -c "cd /opt/$APP_NAME && tar -xzf release.tgz"

# Move frontend static assets to nginx root
sudo rsync -a --delete /opt/$APP_NAME/frontend/aries-react/dist/ /var/www/$APP_NAME/
sudo chown -R www-data:www-data /var/www/$APP_NAME
```

✅ **Did it work?** `ls /opt/$APP_NAME/publish/` shows the .NET DLLs. `ls /var/www/$APP_NAME/` shows `index.html` and `assets/`.

---

## Stage 3 — Production config + database migrations (~10 min)

### 3.1 — Create the environment file

Decide: **Option A** (plain env file, simpler) or **Option B** (env file points at Azure Key Vault, better rotation story). Pick **B** unless you have a reason not to.

**Option A — plain env file (secrets in the file):**

```bash
sudo tee /etc/$APP_NAME/app.env >/dev/null <<EOF
ASPNETCORE_ENVIRONMENT=Production
ASPNETCORE_URLS=http://127.0.0.1:5051
DOTNETCORE_URLS=http://127.0.0.1:5051
# Connection string — paste the SQL admin password here
ConnectionStrings__DefaultConnection=Server=tcp:$SQL_SERVER,1433;Database=$SQL_DB;User ID=$SQL_USER;Password=REPLACE_WITH_REAL_PASSWORD;Encrypt=True;TrustServerCertificate=False;Connection Timeout=30;
# JWT — generate once, never rotate by editing this file (see Stage 6.3)
Jwt__Key=$(openssl rand -base64 64 | tr -d '\n')
Jwt__Issuer=https://$DOMAIN
Jwt__Audience=https://$DOMAIN
# Seed data runs in dev only — MUST be false in prod
SeedDatabaseOnStartup=false
EOF

sudo chmod 640 /etc/$APP_NAME/app.env
sudo chown root:deploy /etc/$APP_NAME/app.env
```

Now edit `REPLACE_WITH_REAL_PASSWORD`:

```bash
sudo nano /etc/$APP_NAME/app.env
# Paste the real Azure SQL admin password, save, exit.
```

**Option B — Key Vault (preferred for rotation):**

```bash
sudo tee /etc/$APP_NAME/app.env >/dev/null <<EOF
ASPNETCORE_ENVIRONMENT=Production
ASPNETCORE_URLS=http://127.0.0.1:5051
AZURE_KEY_VAULT_URI=https://$VAULT_NAME.vault.azure.net
# Either Managed Identity (preferred — see 3.2 below) OR service principal:
# AZURE_TENANT_ID=...
# AZURE_CLIENT_ID=...
# AZURE_CLIENT_SECRET=...
SeedDatabaseOnStartup=false
EOF

sudo chmod 640 /etc/$APP_NAME/app.env
sudo chown root:deploy /etc/$APP_NAME/app.env
```

See [docs/AZURE_KEYVAULT_GUIDE.md](docs/AZURE_KEYVAULT_GUIDE.md) for the step-by-step walkthrough of adding every secret from `docs/SECRETS_MAPPING.md` into the vault.

### 3.2 — Give the VM a badge (system-assigned managed identity)

Only if you picked **Option B**. Run from your laptop:

```bash
# Turn on system-assigned identity on the VM
az vm identity assign \
  --resource-group rg-$APP_NAME-prod \
  --name <vm-name>

# Grab its principal ID
VM_PID=$(az vm identity show \
  --resource-group rg-$APP_NAME-prod \
  --name <vm-name> \
  --query principalId -o tsv)

# Grant get + list on the Key Vault
az keyvault set-policy \
  --name $VAULT_NAME \
  --object-id $VM_PID \
  --secret-permissions get list
```

### 3.3 — Apply database schema migrations

If your VM has the .NET SDK installed (see 1.2 note):

```bash
cd /opt/$APP_NAME/publish
sudo -u deploy bash -c "
  export ConnectionStrings__DefaultConnection='Server=tcp:$SQL_SERVER,1433;Database=$SQL_DB;User ID=$SQL_USER;Password=$(sudo grep Password= /etc/$APP_NAME/app.env | cut -d= -f2- | cut -d\; -f1 | sed 's/Password=//');Encrypt=True;TrustServerCertificate=False;'
  dotnet ef database update \
    --project ./ARIES.Infrastructure.dll \
    --startup-project ./ARIES.Api.dll
"
```

If the VM is runtime-only, run this **from your laptop** instead, against the same Azure SQL DB:

```bash
# On laptop, inside the source project:
export ConnectionStrings__DefaultConnection="Server=tcp:$SQL_SERVER,1433;Database=$SQL_DB;User ID=$SQL_USER;Password=<REAL>;Encrypt=True;"
dotnet ef database update --project src/ARIES.Infrastructure --startup-project src/ARIES.Api
```

✅ **Did it work?** Run this from the VM:

```bash
sqlcmd -S "$SQL_SERVER" -d "$SQL_DB" -U "$SQL_USER" -P "<paste password>" \
  -Q "SELECT COUNT(*) FROM sys.tables" -C
```

The count should match the expected number of entities (usually 20–40 for ARIES-class apps). If it's zero, migrations didn't run.

### 3.4 — Seed production lookup data

**Do NOT run `DevSeeder` on production.** That seeder inserts demo users and sample bookings.

Instead, load the real lookup data that `docs/SEED_COMPLETENESS.md` identified as the demo-safe reference data (genders, races, charge-types, offense-codes, counties, cities, etc. — everything in the **Healthy Lookups** table of that report).

```bash
# If you exported the seed data as SQL:
sqlcmd -S "$SQL_SERVER" -d "$SQL_DB" -U "$SQL_USER" -P "<paste password>" \
  -i /opt/$APP_NAME/publish/Migrations/ProdLookupSeed.sql -C

# Or run a dedicated Program.ProductionSeed path if the app ships one:
cd /opt/$APP_NAME/publish
sudo -u deploy bash -c "EnvironmentName=Production dotnet $APP_NAME.Api.dll --seed-prod-lookups"
```

✅ **Did it work?** Every lookup table has ≥ 3 rows:

```bash
for TABLE in Genders Races HairColors EyeColors Counties Cities ChargeTypes OffenseCodes WorkflowSteps; do
  COUNT=$(sqlcmd -S "$SQL_SERVER" -d "$SQL_DB" -U "$SQL_USER" -P "<paste password>" \
    -Q "SET NOCOUNT ON; SELECT COUNT(*) FROM $TABLE" -h -1 -C | tr -d ' \r\n')
  echo "$TABLE: $COUNT rows"
done
```

Every row should read ≥ 3. If any is 0 or 1, that dropdown will be empty in the UI — your demo is broken.

---

## Stage 4 — systemd + nginx + TLS (~10 min)

### 4.1 — systemd unit

```bash
sudo tee /etc/systemd/system/$APP_NAME-api.service >/dev/null <<EOF
[Unit]
Description=$APP_NAME API (.NET 8 Kestrel)
After=network.target

[Service]
Type=simple
User=deploy
Group=deploy
WorkingDirectory=/opt/$APP_NAME/publish
ExecStart=/usr/bin/dotnet /opt/$APP_NAME/publish/<dotnet-dll>
EnvironmentFile=/etc/$APP_NAME/app.env
Restart=on-failure
RestartSec=10
KillSignal=SIGINT
TimeoutStopSec=30
SyslogIdentifier=$APP_NAME
# Ensure .NET caches are writable
Environment=DOTNET_PRINT_TELEMETRY_MESSAGE=false
Environment=ASPNETCORE_FORWARDEDHEADERS_ENABLED=true

[Install]
WantedBy=multi-user.target
EOF

# !!! edit <dotnet-dll> to your actual DLL name, e.g. ARIES.Api.dll !!!
sudo nano /etc/systemd/system/$APP_NAME-api.service

sudo systemctl daemon-reload
sudo systemctl enable --now $APP_NAME-api.service
```

✅ **Did it work?**

```bash
sudo systemctl status $APP_NAME-api.service
# Active: active (running)
curl -sSf http://127.0.0.1:5051/health
# {"status":"ok",...} or similar
```

If `status` shows `failed`, read the log and fix before moving on:

```bash
sudo journalctl -u $APP_NAME-api.service -n 100 --no-pager
```

### 4.2 — nginx vhost

```bash
sudo tee /etc/nginx/sites-available/$APP_NAME >/dev/null <<EOF
server {
    listen 80;
    server_name $DOMAIN;

    root /var/www/$APP_NAME;
    index index.html;

    # Real-IP forwarding so app logs the client, not the proxy
    set_real_ip_from 127.0.0.1;
    real_ip_header X-Forwarded-For;

    # API — reverse proxy to Kestrel
    location /api/ {
        proxy_pass http://127.0.0.1:5051;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300s;
        proxy_buffering off;   # stream SSE/websockets if any
    }

    # Health check passthrough
    location = /health {
        proxy_pass http://127.0.0.1:5051/health;
    }

    # SPA fallback — React Router client-side routing
    location / {
        try_files \$uri \$uri/ /index.html;
    }

    # Static asset caching
    location /assets/ {
        alias /var/www/$APP_NAME/assets/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # Security headers (adjust CSP as your app needs)
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "no-referrer-when-downgrade" always;
}
EOF

sudo ln -sf /etc/nginx/sites-available/$APP_NAME /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

✅ **Did it work?**

```bash
curl -sSf http://$DOMAIN/health
curl -sSfI http://$DOMAIN/ | head -5          # 200 OK
```

### 4.3 — Let's Encrypt TLS

```bash
sudo certbot --nginx -d $DOMAIN --non-interactive --agree-tos -m ops@$DOMAIN
```

Certbot auto-edits the nginx vhost to add `listen 443 ssl`, points at `/etc/letsencrypt/live/$DOMAIN/`, and installs a renewal timer. Verify:

```bash
sudo systemctl list-timers | grep certbot
sudo certbot certificates
```

### 4.4 — Enable UFW

```bash
sudo ufw --force enable
sudo ufw status verbose
# Active; OpenSSH allowed; Nginx Full allowed
```

✅ **Stage 4 did it work?**

```bash
# From your laptop, not the VM:
curl -sSf https://$DOMAIN/health
curl -sSI https://$DOMAIN/ | head -3          # HTTP/2 200
```

---

## Stage 5 — Smoke test (the real zero-regression gate) — ~5 min

**Do not declare deploy complete until every one of these returns the expected result.** This is the gate that stops silent regressions from reaching users.

Run from your laptop:

```bash
BASE="https://$DOMAIN"

# 5.1 — Health
curl -sSf $BASE/health && echo " ✅" || echo " ❌ FAIL"

# 5.2 — Auth — login returns a JWT (use a real seeded user from your prod lookup seed)
TOKEN=$(curl -sS -X POST $BASE/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@'$DOMAIN'","password":"<real-admin-password>"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["token"])')
echo "token length: ${#TOKEN} (expect >500)"

# 5.3 — Every lookup endpoint returns ≥ 3 rows
for EP in genders races hair-colors eye-colors counties cities \
          charge-types offense-codes arrest-case-types; do
  N=$(curl -sSf -H "Authorization: Bearer $TOKEN" $BASE/api/lookups/$EP | python3 -c 'import sys,json; print(len(json.load(sys.stdin)))')
  [ "$N" -ge 3 ] && echo "$EP: $N rows ✅" || echo "$EP: $N rows ❌ FAIL"
done

# 5.4 — Every frontend fetch call resolves (uses docs/API_CONTRACT.md)
#      If the API_CONTRACT report claims any missing endpoint, this must be zero:
if [ -f docs/API_CONTRACT.md ]; then
  MISSING=$(grep -c '^| `/api' docs/API_CONTRACT.md | head -1)
  grep -A99 '^## ❌' docs/API_CONTRACT.md | grep '^| `/api' | awk -F'`' '{print $2}' | while read PATH; do
    [ -z "$PATH" ] && continue
    CODE=$(curl -sS -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $TOKEN" "$BASE$PATH")
    [ "$CODE" = "404" ] && echo "$PATH: 404 ❌ REGRESSION" || echo "$PATH: $CODE ✅"
  done
fi

# 5.5 — CRUD round-trip on the primary entity (adapt to your app)
# Create
BOOKING_ID=$(curl -sSf -X POST $BASE/api/total-booking \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"lastName":"SmokeTest","firstName":"Prod","dob":"1985-01-01","sexId":1,"raceId":1,"arrestCaseNumber":"SMOKE-1"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')
echo "created booking id=$BOOKING_ID"

# Read
curl -sSf -H "Authorization: Bearer $TOKEN" $BASE/api/total-booking/$BOOKING_ID > /dev/null && echo "read ✅" || echo "read ❌"

# Delete (soft delete expected)
curl -sSf -X DELETE -H "Authorization: Bearer $TOKEN" $BASE/api/total-booking/$BOOKING_ID > /dev/null && echo "delete ✅" || echo "delete ❌"

# 5.6 — TLS certificate is valid (not just self-signed)
echo | openssl s_client -connect $DOMAIN:443 -servername $DOMAIN 2>/dev/null | \
  openssl x509 -noout -issuer -dates

# 5.7 — Security headers present
curl -sSI $BASE/ | grep -iE '(x-frame-options|x-content-type|strict-transport-security)'

# 5.8 — No accidental demo routes exposed
for DEMO in /api/test /api/debug /mock-azure /sample-data; do
  CODE=$(curl -sS -o /dev/null -w '%{http_code}' $BASE$DEMO)
  [ "$CODE" = "404" ] && echo "$DEMO: 404 ✅ (demo route blocked)" || echo "$DEMO: $CODE ❌ LEAKED"
done

# 5.9 — Journal has no ERROR lines from the last 2 minutes
ssh $VM_USER@$VM_IP "sudo journalctl -u $APP_NAME-api.service --since '2 minutes ago' | grep -c -iE '\\b(error|fail|exception)\\b' | head -1"
# Expect: 0

# 5.10 — Seeded lookups match the docs/SEED_COMPLETENESS.md expectations
# If SEED_COMPLETENESS says offense-codes should have 20 rows and the live API returns 3, that's a regression
```

✅ **Did it work?** Every line above printed `✅`, zero `❌`. Any red and you run Stage 7 (rollback) immediately.

---

## Stage 6 — Day-2 operations

### 6.1 — Monitor live logs

```bash
sudo journalctl -u $APP_NAME-api.service -f
# Ctrl+C to stop
```

### 6.2 — Restart after config change

```bash
sudo systemctl restart $APP_NAME-api.service
sudo systemctl status $APP_NAME-api.service
```

### 6.3 — Rotate a Key Vault secret (option B deploy only)

1. Azure Portal → your Key Vault → Secrets → click the secret → **+ New Version** → paste new value → **Create**.
2. On the VM: `sudo systemctl restart $APP_NAME-api.service`
3. Smoke test (Stage 5).

No code change. No redeploy. ~30s of downtime.

### 6.4 — Apply a hotfix

```bash
# Laptop: rebuild + repackage
./stage-0.5-rebuild.sh        # your local equivalent
scp $APP_NAME-$(date +%Y%m%d-%H%M%S).tgz $VM_USER@$VM_IP:/tmp/

# VM:
ssh $VM_USER@$VM_IP

# Keep the current release as fallback
sudo mv /opt/$APP_NAME/publish /opt/$APP_NAME/publish.prev
sudo mv /opt/$APP_NAME/frontend /opt/$APP_NAME/frontend.prev

# Extract the new
sudo mv /tmp/$APP_NAME-*.tgz /opt/$APP_NAME/release.tgz
sudo -u deploy bash -c "cd /opt/$APP_NAME && tar -xzf release.tgz"
sudo rsync -a --delete /opt/$APP_NAME/frontend/aries-react/dist/ /var/www/$APP_NAME/

sudo systemctl restart $APP_NAME-api.service

# Run Stage 5 again. If any ❌, run Stage 7 (rollback).
```

### 6.5 — Database backups

Azure SQL handles PITR (point-in-time restore) automatically — 7 days retention by default, extendable in the Portal. Verify:

```bash
az sql db show \
  --resource-group rg-$APP_NAME-prod \
  --server $(echo $SQL_SERVER | cut -d. -f1) \
  --name $SQL_DB \
  --query "earliestRestoreDate"
```

For additional safety, schedule a nightly `bacpac` export:

```bash
ssh $VM_USER@$VM_IP bash <<'EOF'
sudo tee /usr/local/bin/aries-bacpac-backup.sh >/dev/null <<'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail
TS=$(date +%Y%m%d-%H%M%S)
az sql db export \
  --resource-group rg-aries-prod \
  --server sql-aries-prod \
  --name aries-prod \
  --admin-user sqladmin \
  --admin-password "$(cat /etc/aries/sql-pw)" \
  --storage-key-type StorageAccessKey \
  --storage-key "$(cat /etc/aries/storage-key)" \
  --storage-uri "https://ariesbackups.blob.core.windows.net/bacpacs/aries-prod-$TS.bacpac"
SCRIPT
sudo chmod 700 /usr/local/bin/aries-bacpac-backup.sh
(crontab -l 2>/dev/null; echo "30 2 * * * /usr/local/bin/aries-bacpac-backup.sh") | crontab -
EOF
```

---

## Stage 7 — Rollback (emergency)

If Stage 5 smoke fails after a deploy:

```bash
ssh $VM_USER@$VM_IP

# Stop the broken version
sudo systemctl stop $APP_NAME-api.service

# Swap to the previous release (created in Stage 6.4)
sudo rm -rf /opt/$APP_NAME/publish /opt/$APP_NAME/frontend
sudo mv /opt/$APP_NAME/publish.prev /opt/$APP_NAME/publish
sudo mv /opt/$APP_NAME/frontend.prev /opt/$APP_NAME/frontend
sudo rsync -a --delete /opt/$APP_NAME/frontend/aries-react/dist/ /var/www/$APP_NAME/

# Start
sudo systemctl start $APP_NAME-api.service

# Re-run smoke from your laptop (Stage 5)
```

If the smoke still fails, the database schema was changed and `ef migrations` made the previous build incompatible. Either:

1. Roll the schema back (`dotnet ef migrations script` → target the prior migration name → apply).
2. Restore Azure SQL via PITR to 15 min before the deploy (Azure Portal → DB → **Restore**).

Then restart and re-smoke.

---

## Stage 8 — What's running where (reference)

```text
Your users
    │  HTTPS to https://<domain>
    ▼
┌──────────────────────────────────────────────────┐
│  Azure VM (Ubuntu 22.04 LTS)                     │
│  ┌────────────────────────────────────────────┐  │
│  │  nginx :443 (TLS) + :80 (redirect)         │  │
│  │    ├─ /          → /var/www/<app> static   │  │
│  │    ├─ /assets/   → immutable 30d cache     │  │
│  │    └─ /api/*     → 127.0.0.1:5051          │  │
│  └────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────┐  │
│  │  systemd: <app>-api.service                │  │
│  │    └─ dotnet /opt/<app>/publish/<dll>       │  │
│  │       reads /etc/<app>/app.env              │  │
│  │       binds 127.0.0.1:5051 (loopback only) │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
│  Outbound: 1433 → Azure SQL                      │
│  Outbound: 443  → Azure Key Vault (option B)     │
│                                                  │
│  UFW: only 22 / 80 / 443 inbound                 │
└──────────────────────────────────────────────────┘
         │                       │
         ▼                       ▼
 ┌───────────────┐       ┌───────────────────┐
 │  Azure SQL    │       │  Azure Key Vault  │
 │  (your dw)    │       │  (option B)       │
 └───────────────┘       └───────────────────┘
```

---

## Appendix A — Troubleshooting by symptom

| What you see | Likely cause | Fix |
|---|---|---|
| `502 Bad Gateway` from nginx | systemd service crashed | `sudo journalctl -u $APP_NAME-api.service -n 100` → read the tail |
| `Login failed for user 'sqladmin'` | Wrong password or SQL firewall | Re-check Stage 3.1; confirm VM IP is in the firewall (Stage 0.3) |
| Lookup endpoints return 200 with `[]` | Prod seed not applied | Stage 3.4 |
| Frontend loads but `/api/*` returns 404 | Routing mismatch | Check `docs/API_CONTRACT.md` red findings; did you deploy the right build? |
| `Forbidden: access denied to vault` | Managed identity policy missing | Stage 3.2 — check `az keyvault show --name $VAULT_NAME --query properties.accessPolicies` |
| JWT rejects valid tokens after deploy | `Jwt__Key` changed between builds | Expected on rotation — users re-login. If unintentional, set the prior `Jwt__Key` back |
| `certbot renew` fails | port 80 blocked or DNS changed | `sudo ufw status` → port 80 allowed? `dig $DOMAIN` → A record still points at $VM_IP? |
| SPA client-side routes 404 | nginx SPA fallback missing | Stage 4.2 `try_files` line must be present |
| `permission denied` reading `/etc/$APP_NAME/app.env` | Wrong owner/mode | `sudo chown root:deploy /etc/$APP_NAME/app.env && sudo chmod 640 …` |
| Empty dropdowns in the UI | Prod lookup seed skipped / missing | Compare Azure SQL `SELECT COUNT(*)` against `docs/SEED_COMPLETENESS.md` expected counts |

---

## Appendix B — Full command reference (copy-paste order)

If you want the "no prose, just commands" version, here it is in deploy order.
Scroll back to the relevant stage if anything fails — each of these is explained above.

```bash
# Stage 0 — laptop
export APP_NAME=aries VM_USER=azureuser VM_IP=… DOMAIN=… SQL_SERVER=… SQL_DB=… SQL_USER=…
ssh $VM_USER@$VM_IP 'hostname && uname -a'
sqlcmd -S "$SQL_SERVER" -d "$SQL_DB" -U "$SQL_USER" -G -Q "SELECT @@VERSION"
az sql server firewall-rule create --resource-group rg-$APP_NAME-prod --server $(echo $SQL_SERVER | cut -d. -f1) --name "allow-vm-$APP_NAME" --start-ip-address $(ssh $VM_USER@$VM_IP 'curl -sf4 ifconfig.me') --end-ip-address $(ssh $VM_USER@$VM_IP 'curl -sf4 ifconfig.me')
dotnet publish -c Release -o ./publish src/ARIES.Api/ARIES.Api.csproj
(cd frontend/aries-react && VITE_API_BASE_URL="" npm ci && npm run build)
tar -czf $APP_NAME-$(date +%Y%m%d-%H%M%S).tgz --exclude='mock-azure' --exclude='sample-data' --exclude='.env*' --exclude='*.db' publish/ frontend/aries-react/dist/ docs/ README.md
scp $APP_NAME-*.tgz $VM_USER@$VM_IP:/tmp/

# Stage 1 — VM (once)
ssh $VM_USER@$VM_IP
sudo apt update && sudo apt upgrade -y
sudo apt install -y curl ca-certificates gnupg lsb-release nginx sqlite3 ufw
wget https://packages.microsoft.com/config/ubuntu/22.04/packages-microsoft-prod.deb -O /tmp/ms.deb && sudo dpkg -i /tmp/ms.deb && sudo apt update && sudo apt install -y aspnetcore-runtime-8.0 msodbcsql18 mssql-tools18
sudo useradd -r -m -d /home/deploy -s /bin/bash deploy || true
sudo mkdir -p /opt/$APP_NAME /var/www/$APP_NAME /etc/$APP_NAME
sudo chown -R deploy:deploy /opt/$APP_NAME
sudo chown -R www-data:www-data /var/www/$APP_NAME
sudo chmod 750 /etc/$APP_NAME && sudo chown root:deploy /etc/$APP_NAME
sudo snap install --classic certbot && sudo ln -sf /snap/bin/certbot /usr/bin/certbot
sudo ufw allow OpenSSH && sudo ufw allow 'Nginx Full'

# Stage 2 — VM
sudo mv /tmp/$APP_NAME-*.tgz /opt/$APP_NAME/release.tgz
sudo chown deploy:deploy /opt/$APP_NAME/release.tgz
sudo -u deploy bash -c "cd /opt/$APP_NAME && tar -xzf release.tgz"
sudo rsync -a --delete /opt/$APP_NAME/frontend/aries-react/dist/ /var/www/$APP_NAME/

# Stage 3 — VM
sudo nano /etc/$APP_NAME/app.env       # paste env — see 3.1
sudo chmod 640 /etc/$APP_NAME/app.env && sudo chown root:deploy /etc/$APP_NAME/app.env
# Migrations — run from laptop OR from VM if SDK installed

# Stage 4 — VM
sudo nano /etc/systemd/system/$APP_NAME-api.service    # paste unit — see 4.1
sudo systemctl daemon-reload && sudo systemctl enable --now $APP_NAME-api.service
sudo nano /etc/nginx/sites-available/$APP_NAME         # paste vhost — see 4.2
sudo ln -sf /etc/nginx/sites-available/$APP_NAME /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default && sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d $DOMAIN --non-interactive --agree-tos -m ops@$DOMAIN
sudo ufw --force enable

# Stage 5 — laptop — SMOKE TEST (must all be ✅)
curl -sSf https://$DOMAIN/health
# … see full smoke in §5
```

---

## What to tell the team after deploy

Copy-paste this Slack/Teams message with the real values filled in:

> 🚀 **{app-name} deployed to production** — {domain}
>
> - Version: {git-sha-or-tag}
> - Database: Azure SQL `{sql-server}/{sql-db}`
> - Secrets: Azure Key Vault `{vault-name}` (managed identity)
> - Smoke test: ✅ all 10 checks green
> - Previous release kept at `/opt/{app-name}/publish.prev` for fast rollback
> - Full runbook: [DEPLOY_AZURE_VM_UBUNTU.md](DEPLOY_AZURE_VM_UBUNTU.md)
> - Per-secret mapping: [docs/SECRETS_MAPPING.md](docs/SECRETS_MAPPING.md)
> - Rollback procedure: Stage 7 of the runbook (< 2 min)
