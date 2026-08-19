# Bambu Lab Print Management System

An automated system for managing Bambu Lab 3D printers that tracks print jobs, enforces usage policies, and provides a web dashboard for monitoring and management.

## Table of Contents

- [System Overview](#system-overview)
- [Architecture](#architecture)
- [How It Works](#how-it-works)
- [Components](#components)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)

## System Overview

This system provides automated management for Bambu Lab 3D printers with the following features:
- **Print Job Tracking**: Automatically tracks prints from Bambu Cloud and matches them with user form submissions
- **Usage Limits**: Enforces per-quarter weight limits with exemption support
- **Policy Enforcement**: Ban lists, concurrency limits, and automated print cancellation
- **Real-time Monitoring**: MQTT connection to printers for live status updates
- **Web Dashboard**: Comprehensive interface for monitoring printers, prints, users, and inventory
- **Email Notifications**: Automatic notifications when prints are canceled

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      PRINTING WORKFLOW                       │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. User fills Start Form (Google Form)                     │
│     ↓                                                        │
│  2. User sends print via Bambu Studio → Bambu Cloud         │
│     ↓                                                        │
│  3. Manager polls Cloud API & Google Sheets                 │
│     ↓                                                        │
│  4. Manager matches form + print (by name & timestamp)      │
│     ↓                                                        │
│  5. Manager validates policy (limits, bans, concurrent)     │
│     ↓                                                        │
│  6. Print starts OR gets canceled (with notification)       │
│     ↓                                                        │
│  7. Manager monitors print status via MQTT                  │
│     ↓                                                        │
│  8. Dashboard displays real-time status & history           │
│                                                              │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    COMPONENT ARCHITECTURE                    │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌───────────────┐      ┌─────────────────┐                │
│  │ Google Forms  │─────▶│     Manager     │                │
│  │  Start Form   │ poll │  (Bambu Bot)    │                │
│  └───────────────┘      └────────┬────────┘                │
│                                   │ MQTT + REST API         │
│  ┌───────────────┐                ▼                         │
│  │ Bambu Cloud   │◀───────┌──────────────┐                 │
│  │     API       │  poll  │   Printers   │                 │
│  └───────────────┘        │   (MQTT)     │                 │
│                           └──────────────┘                 │
│                                   │                         │
│                                   ▼                         │
│                           ┌──────────────┐                 │
│                           │  Dashboard   │                 │
│                           │   (Flask)    │                 │
│                           └──────────────┘                 │
│                                   │                         │
│                                   ▼                         │
│                        ┌─────────────────────┐             │
│                        │  SQLite Databases   │             │
│                        │  - Prints & Forms   │             │
│                        │  - User Usage       │             │
│                        │  - Filament Inv.    │             │
│                        └─────────────────────┘             │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## How It Works

### Print Job Workflow

1. **User Submits Start Form**
   - User fills out a Google Form with their CruzID and intended printer name
   - Form is submitted to a Google Sheet (`Form Responses 1`)
   - Timestamp is recorded automatically

2. **User Starts Print Job**
   - User sends their 3D model file to a Bambu printer via Bambu Studio
   - Print job is created in the Bambu Cloud
   - Cloud assigns a unique task ID to the print
   - Print appears in user's Bambu Lab account

3. **Manager Polling Loop** (runs every 10 seconds)
   - Polls Google Sheets API for new form submissions
   - Polls Bambu Cloud REST API for new print tasks
   - Stores unmatched forms and prints in SQLite database
   - Each iteration processes all unmatched items

4. **Form-to-Print Matching Algorithm**
   - Matches forms to prints based on two criteria:
     - **Printer name**: Must match exactly (case-sensitive)
     - **Timestamp proximity**: Within 10 minutes of each other
   - Matching logic:
     - Most recent form for each printer takes priority
     - Old forms/prints matched if timestamps are close
     - Prevents duplicate matches
   - Once matched, form and print are linked in database

5. **Policy Validation**
   - **Ban Check**: Rejects if user CruzID is in `ban.json`
   - **Concurrency Check**: Rejects if user has another print currently running
   - **Weight Limit Check**: 
     - Default: 1000g per quarter per user
     - Exempted users: No per-print weight limit
     - Calculates remaining quota from usage history
     - Checks if current print fits within quota
   - **Exemption Logic**: Users in `bambu_limit_exempt.json` bypass standard limits

6. **Print Execution Decision**
   - **If Approved**: 
     - Form-to-print link saved to database
     - Print marked as "matched" and allowed to proceed
     - Printer continues normally
     - Status begins real-time monitoring
   - **If Rejected**:
     - Print canceled via Bambu Cloud API
     - Email notification sent to user with rejection reason
     - Form marked as "expired" in database
     - Print marked with failure reason

7. **Real-Time Status Monitoring**
   - Manager maintains persistent MQTT connection to `us.mqtt.bambulab.com`
   - Each printer sends status updates every few seconds
   - Monitored data:
     - **Temperatures**: Nozzle and bed (current + target)
     - **Print Progress**: Current layer, total layers, percentage complete
     - **Time Estimates**: Remaining time, start time
     - **Print State**: Idle, running, paused, finished, failed
     - **Filament**: Active spool, colors, weights per color
     - **Fan Speed**: Current fan percentage
   - Printers marked offline after 15 minutes without updates

8. **Completion & Usage Tracking**
   - **Successful completion**:
     - Print marked as succeeded in database
     - Weight deducted from user's quarterly quota
     - Print logged to status sheet (Google Sheets)
     - Usage logged to usage sheet
     - Cover photo downloaded and saved from Cloud API
   - **Failed prints**:
     - Print marked as failed
     - No weight deducted from quota
     - Failure reason recorded
   - **Canceled prints**:
     - Print marked as canceled
     - Reason logged (policy violation or manual cancel)

### Dashboard Real-Time Updates

The web dashboard provides live monitoring without page refresh:

1. **Printer Status View**
   - Shows all configured printers
   - Real-time state: offline, idle, printing
   - Current temperatures (nozzle/bed)
   - Print progress bars
   - Ability to cancel running prints

2. **Print History**
   - All completed prints with cover photos
   - Filter by date range, user, or printer
   - Shows duration, weight, colors used
   - Links to high-resolution photos

3. **User Management**
   - View all users and their quarterly usage
   - See remaining quota per user
   - Manually add/remove exemptions or bans
   - Adjust individual user limits

4. **Filament Inventory**
   - Track available spools by color and type
   - Monitor remaining weight per spool
   - Log when spools are added or depleted
   - Associate usage with specific prints

## Components

### 1. Bambu Printer Manager (`src/bambu_printers/manager.py`)

The autonomous bot that orchestrates the entire print workflow.

**Core Responsibilities:**
- Poll Google Sheets for new print request forms
- Poll Bambu Cloud API for new print jobs
- Match forms to prints based on printer name and timestamp
- Validate prints against policy rules (bans, limits, concurrency)
- Cancel or approve prints automatically
- Monitor printer status via MQTT connections
- Track user usage and enforce quarterly limits
- Send notification emails for canceled prints

**Key Modules:**

- **`manager.py`**: Main control loop that runs every 10 seconds
  ```python
  while not stopped:
      1. Get new forms from Google Sheets
      2. Get new prints from Bambu Cloud API
      3. Match forms to prints by name/timestamp
      4. Validate each match against policies
      5. Cancel invalid prints or approve valid ones
      6. Update printer statuses from MQTT
      7. Log completed prints to sheets
      8. Sleep for BAMBU_DELAY (10 seconds)
  ```

- **`bambu_printer.py`**: MQTT interface to individual printers
  - Connects to `us.mqtt.bambulab.com:8883`
  - Subscribes to printer status messages
  - Parses real-time updates (temp, progress, state)
  - Maintains connection health

- **`bambu_account.py`**: Bambu Cloud REST API client
  - Authenticates with username/password
  - Fetches print task list from cloud
  - Issues cancel commands
  - Downloads cover photos

- **`bambu_db.py`**: SQLite database manager
  - **Tables**:
    - `forms`: Start form submissions
    - `prints`: Cloud print tasks
    - `form_to_print`: Matching relationships
    - `printers`: Printer info and current status
    - `user_usage`: Quarterly weight tracking per user
    - `filament_inventory`: Spool tracking
  - **Operations**: Add/query/update records for all entities

- **`start_form.py`**: Google Sheets API client
  - Connects to print request form responses
  - Fetches new rows since last check
  - Parses columns: timestamp, CruzID, printer name

- **`status_sheet.py`**: Print history logger
  - Writes completed prints to Google Sheet
  - Records: user, printer, duration, weight, outcome

- **`usage_sheet.py`**: User usage tracker
  - Logs per-user weight consumption
  - Tracks quarterly totals for limit enforcement

- **`gmail.py`**: Email notification sender
  - Sends cancellation notices to users
  - Includes rejection reason in message body
  - Uses Gmail SMTP

**Database Schema:**

```sql
-- Form submissions from Google Sheets
forms (form_row, timestamp, printer_name, cruzid)

-- Prints from Bambu Cloud
prints (print_id, printer_name, title, cover_url, start_time, 
        end_time, weight, color0-3, weight0-3)

-- Form-to-print matches
form_to_print (form_row, print_id)

-- Printer status
printers (name, data, last_update, offline, state, 
          current_print_id, current_form_row, current_cruzid)

-- User quarterly usage
user_usage (cruzid, quarter, year, total_weight)

-- Filament inventory
filament_inventory (spool_id, color, type, weight_remaining, 
                    date_added, notes)
```

**Matching Algorithm:**

Forms and prints are matched if:
1. Printer names are identical (exact string match)
2. Timestamps are within `BAMBU_TIMEOUT` (10 minutes) of each other
3. Neither has been previously matched

Priority: Most recent form per printer is used first.

**Policy Validation Flow:**

```
For each matched (form, print) pair:
  1. Check ban list → Cancel if banned
  2. Check concurrency → Cancel if user has active print
  3. Check weight limit:
     - Get user's quarterly usage
     - Calculate remaining quota
     - If print weight > remaining → Cancel
     - Exempted users skip this check
  4. If all checks pass → Approve and link
```

**Constants (from `src/constants.py`):**

- `BAMBU_TIMEOUT = 10 * 60` - Max seconds between form and print
- `BAMBU_DEFAULT_LIMIT = 1000` - Quarterly weight limit in grams
- `BAMBU_EXEMPT_LIMIT = float('inf')` - No limit for exempted users
- `BAMBU_DELAY = 10` - Manager loop interval in seconds
- `BAMBU_OFFLINE_TIMEOUT = 15 * 60` - Seconds before marking printer offline

**Printer States:**

- `PRINTER_OFFLINE (0)`: No updates for 15+ minutes
- `PRINTER_IDLE (1)`: Online but not printing
- `PRINTER_UNMATCHED (2)`: Printing but no form match yet
- `PRINTER_MATCHED (3)`: Printing a matched/approved job

**Print States:**

- `GCODE_IDLE (0)`: Not printing
- `GCODE_RUNNING (1)`: Actively printing
- `GCODE_FINISH (2)`: Print completed successfully
- `GCODE_PAUSE (3)`: Print paused
- `GCODE_FAILED (4)`: Print failed
- `GCODE_UNKNOWN (5)`: State unclear

### 2. Dashboard (`src/bambu_printers/dashboard.py`)

Flask web application for monitoring and management.

**Features:**

- **Home Page** (`/dashboard`): System overview
  - Total prints today/week/month
  - Active printers count
  - Recent activity feed

- **Printers Page** (`/dashboard/printers`): Live printer control
  - Real-time status for each printer
  - Current temperatures (nozzle/bed)
  - Print progress bars
  - Stop button to cancel running prints
  - Offline/online indicators

- **Prints Page** (`/dashboard/prints`): Historical view
  - Gallery of all prints with cover photos
  - Filter by date range, user, or printer
  - Shows: user, printer, weight, colors, duration, outcome
  - Click to view full-resolution photo

- **Users Page** (`/dashboard/users`): User management
  - List all users with quarterly usage
  - Show remaining quota per user
  - Add/remove users from exemption list
  - Add/remove users from ban list
  - Manually adjust user limits

- **Inventory Page** (`/dashboard/inventory`): Filament tracking
  - List all spools with remaining weight
  - Add new spools (color, type, initial weight)
  - Mark spools as depleted
  - View usage history per spool

**Authentication:**

- Google OAuth 2.0 integration
- Email-based allowlist (configured in `dashboard_auth.json`)
- Session cookies with secure flags
- Middleware checks authentication on all routes

**API Endpoints:**

- `GET /dashboard/api/printers` - Get all printer statuses (JSON)
- `POST /dashboard/api/cancel_print` - Cancel a running print
- `GET /dashboard/api/prints` - Get print history (filtered)
- `POST /dashboard/api/add_exemption` - Add user to exemption list
- `POST /dashboard/api/remove_exemption` - Remove from exemption list
- `POST /dashboard/api/add_ban` - Add user to ban list
- `POST /dashboard/api/remove_ban` - Remove from ban list
- `GET /dashboard/api/inventory` - Get filament inventory
- `POST /dashboard/api/add_spool` - Add new filament spool
- `POST /dashboard/api/use_spool` - Record filament usage

**Photo Storage:**

- Print cover photos downloaded from Bambu Cloud
- Stored locally in `/data/prints/`
- Served via Flask static file handler
- Cached for performance

**Templates** (`src/bambu_printers/templates/`):

- `base.html`: Common layout with navigation
- `dashboard_home.html`: Overview/stats page
- `dashboard_printers.html`: Live printer monitoring
- `dashboard_prints.html`: Print history gallery
- `dashboard_users.html`: User management interface
- `dashboard_inventory.html`: Filament inventory
- `error.html`: Error message page

## Installation

### System Requirements

- Python 3.8+
- SQLite3
- Linux or macOS (for production deployment)

### Setup

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd slugworks-automations
   ```

2. **Create virtual environment:**
   ```bash
   sudo apt install --upgrade python3-pip python3-venv
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   # For Bambu Manager
   pip install -r src/bambu_printers/requirements.txt
   
   # Dependencies include:
   # - pybambu: Bambu Lab API client
   # - google-auth, google-api-python-client: Google Sheets/OAuth
   # - flask, authlib: Dashboard web server
   # - paho-mqtt: MQTT client for printers
   ```

4. **Create configuration directory:**
   ```bash
   mkdir common
   ```

5. **Configure the system** (see Configuration section below)

## Configuration

All configuration files should be stored in the `common/` directory at the repository root.

### Required Configuration Files

#### 1. Bambu Account Credentials (`creds.py`)

Place in repository root (not in `common/`):

```python
username = "your_bambu_cloud_username"
password = "your_bambu_cloud_password"
```

This is your Bambu Lab account login used to access the Cloud API.

#### 2. Start Form OAuth Token (`common/start_form_token.json`)

Automatically generated on first run. You'll need `common/credentials.json` from Google Cloud Console with Sheets API enabled.

**First-time setup:**
1. Go to Google Cloud Console
2. Create a project and enable Google Sheets API
3. Create OAuth 2.0 credentials (Desktop app)
4. Download as `credentials.json` and place in `common/`
5. Run the manager - it will prompt you to authenticate
6. Complete OAuth flow in browser
7. Token will be saved automatically

**Manual token generation:**
```bash
cd src/bambu_printers
python start_form.py
```

#### 3. Start Form Configuration

The Start Form Google Sheet ID is hardcoded in `start_form.py`:
```python
START_FORM_SHEET_ID = "1zIMn7G5pq1A7pqQSPIGTQvbvSztVy_QlmRi4wA1HDzA"
```

Update this to match your form's response sheet ID.

#### 4. Dashboard Authentication (`common/dashboard_auth.json`)

```json
{
    "allowed_emails": [
        "admin@example.com",
        "staff@example.com"
    ],
    "secret_key": "your-random-secret-key-here",
    "client_id": "your-google-oauth-client-id.apps.googleusercontent.com",
    "client_secret": "your-google-oauth-client-secret",
    "redirect_uri": "https://yourdomain.com/dashboard/callback",
    "cookie_secure": true
}
```

**Field descriptions:**
- `allowed_emails`: List of email addresses allowed to access dashboard
- `secret_key`: Random string for session encryption (generate with `os.urandom(32).hex()`)
- `client_id`: Google OAuth 2.0 client ID
- `client_secret`: Google OAuth 2.0 client secret
- `redirect_uri`: OAuth callback URL (must match Google Console config)
- `cookie_secure`: Set to `true` if using HTTPS, `false` for local development

**To create OAuth credentials:**
1. Go to Google Cloud Console → APIs & Services → Credentials
2. Create OAuth 2.0 Client ID (Web application type)
3. Add authorized redirect URI: `https://yourdomain.com/dashboard/callback`
4. Copy client ID and secret to config file

#### 5. Gmail SMTP Configuration

For email notifications, configure in `src/bambu_printers/gmail.py`:

```python
# Update these variables:
SENDER_EMAIL = "your-email@gmail.com"
SENDER_PASSWORD = "your-app-password"
```

**Gmail App Password:**
1. Enable 2-factor authentication on your Google account
2. Go to Account Settings → Security → App Passwords
3. Generate an app password for "Mail"
4. Use this password in the config (not your regular password)

### Optional Configuration Files

#### Policy Lists

**Exemptions** (`common/bambu_limit_exempt.json` or `common/exemption.json`):

Users who bypass weight limits:
```json
["staffuser1", "adminuser2", "specialuser3"]
```

**Bans** (`common/ban.json`):

Users who cannot submit prints:
```json
["banneduser1", "violator2"]
```

Both files are optional. If not present, no exemptions/bans are applied.

### Logging Configuration

Logs are written to the repository root:
- `bambu.log` - All Bambu manager and printer activity
- Additional logs created by `src/log.py` setup

Configure log level in each module:
```python
logger = log.setup_logs("module_name", log.INFO)
```

Levels: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`

## Usage

### Starting the Bambu Manager

The manager runs continuously, polling for forms and prints every 10 seconds.

```bash
./start_bambu
```

This script:
1. Activates the virtual environment
2. Clears any stop flag
3. Starts the manager in the background
4. Records the process ID to `pid_bambu_printers`
5. Performs health check after 10 seconds
6. Verifies logs are fresh (within 5 minutes)

**What the manager does:**
- Polls Google Sheets and Bambu Cloud API
- Matches forms to prints
- Validates against policies
- Cancels or approves prints
- Monitors printers via MQTT
- Logs completed prints

**Manual start (for debugging):**
```bash
source venv/bin/activate
python -m src.bambu_printers.manager
```

### Stopping the Bambu Manager

Graceful shutdown that allows current operations to complete:

```bash
./stop_bambu
```

This script:
1. Creates stop file (`common/SPECIAL_BAMBU_STOP`)
2. Manager detects file and begins shutdown
3. Closes MQTT connections cleanly
4. Waits up to 60 seconds for graceful exit
5. Force kills if necessary
6. Removes PID file

**Manual stop:**
```bash
# Find the PID
cat pid_bambu_printers

# Send SIGTERM
kill <PID>

# Or force kill
kill -9 <PID>
```

### Starting the Dashboard

The dashboard web interface runs on port 5001 by default.

```bash
./start_dashboard
```

Access at: `http://localhost:5001/dashboard`

**Manual start:**
```bash
source venv/bin/activate
cd src/bambu_printers
python -c "from dashboard import get_dashboard; app = get_dashboard().app; app.run(host='0.0.0.0', port=5001)"
```

**Production deployment:**
Use gunicorn for better performance:
```bash
source venv/bin/activate
cd src/bambu_printers
gunicorn -w 4 -b 0.0.0.0:5001 "dashboard:get_dashboard().app"
```

### Monitoring and Health Checks

#### Check Manager Status

```bash
# Check if process is running
ps -p $(cat pid_bambu_printers) || echo "Not running"

# Check recent log activity
./detect_bambu_restart
```

The `detect_bambu_restart` script checks if logs are fresh (written within last 5 minutes). Exit code 0 means healthy, 1 means stale logs.

#### View Logs

```bash
# Real-time manager logs
tail -f bambu.log

# Show last 100 lines
tail -n 100 bambu.log

# Search for specific user
grep "username" bambu.log

# Filter by log level
grep "ERROR" bambu.log
```

#### Monitor Printer Connections

```bash
# Check MQTT connection status in logs
grep "MQTT" bambu.log | tail -n 20

# See recent printer updates
grep "on_update" bambu.log | tail -n 20
```

### Database Inspection

The manager uses SQLite databases in `src/bambu_printers/`:

```bash
# Open the main database
sqlite3 src/bambu_printers/bambu.db

# Example queries:
sqlite> .tables
sqlite> SELECT * FROM printers;
sqlite> SELECT * FROM forms WHERE printer_name='PrinterA';
sqlite> SELECT * FROM user_usage;
sqlite> .quit
```

### Maintenance Tasks

#### Update Policy Lists

Edit exemption or ban lists:
```bash
nano common/bambu_limit_exempt.json
nano common/ban.json
```

Changes take effect on next manager loop (within 10 seconds).

#### Pull Latest Code

```bash
./pullme.sh
```

Or manually:
```bash
git pull
```

Restart the manager after pulling updates:
```bash
./stop_bambu
./start_bambu
```

#### Format Code

```bash
./format
```

Uses Black to format all Python files.

#### Clear Old Data

```bash
# Backup database first
cp src/bambu_printers/bambu.db src/bambu_printers/bambu.db.backup

# Open database and clear old records
sqlite3 src/bambu_printers/bambu.db
sqlite> DELETE FROM prints WHERE end_time < strftime('%s', 'now', '-90 days');
sqlite> VACUUM;
sqlite> .quit
```

### Troubleshooting

#### Manager Won't Start

1. Check if already running:
   ```bash
   ps aux | grep manager.py
   ```

2. Check for stop flag:
   ```bash
   rm -f common/SPECIAL_BAMBU_STOP
   ```

3. Check logs for errors:
   ```bash
   tail -n 50 bambu.log
   ```

4. Verify credentials:
   ```bash
   # Test Bambu login
   python -c "from src.bambu_printers.bambu_account import BambuAccount; BambuAccount()"
   ```

#### Prints Not Being Matched

1. Check form submissions in Google Sheet
2. Verify printer names match exactly (case-sensitive)
3. Check timestamp alignment (within 10 minutes)
4. Look for matching logs:
   ```bash
   grep "Matching print" bambu.log
   ```

#### MQTT Connection Issues

1. Check internet connectivity
2. Verify Bambu Cloud credentials
3. Check firewall rules (port 8883)
4. Look for MQTT errors:
   ```bash
   grep "mqtt" bambu.log | grep -i error
   ```

#### Dashboard Authentication Failed

1. Verify Google OAuth credentials
2. Check allowed_emails in `common/dashboard_auth.json`
3. Clear browser cookies
4. Check redirect URI matches Google Console config

### Utility Scripts

- `./monitor_bambu.py` - Continuous monitoring script
- `./detect_bambu_restart` - Health check for supervisor integration
- `./helpme.py` - Diagnostic information gathering

### Integration with Supervisord

For automatic restarts on failure:

```ini
[program:bambu_manager]
command=/path/to/slugworks-automations/start_bambu
directory=/path/to/slugworks-automations
autostart=true
autorestart=true
startretries=3
user=youruser
redirect_stderr=true
stdout_logfile=/var/log/bambu_manager.log
```

---

# Walkthrough Check-Offs

Canvas automation for the maker-space safety walkthroughs. Students complete an
in-person walkthrough or machine training, staff record it, and these tools push
the 1-point completion into Canvas. The access-control sync
(`src/server/canvas.py`) then reads that module completion and unlocks lab
access, so the two halves meet in Canvas.

## Commands

```
./checkoff <command>          # or: python -m src.checkoff <command>
```

| Command | What it does |
| --- | --- |
| `grade` | Read the staff Google Form responses and grade the check-off assignment |
| `staff` | Refresh the cached staff list from Canvas enrollments |
| `transfer` | Copy completions from last year's assignments to this year's |
| `report` | Export a CSV of who completed what, inside a date window |
| `assignments` | List a course's assignments and their IDs |
| `modules` | List a course's modules and the assignments inside them |

## Configuration

Everything lives in `common/canvas.json`, the same file the access-control sync
already reads for `auth_token`. Copy `common.example/canvas.json` and fill it in.
The check-off settings sit in their own `checkoff`, `sheet`, `transfer`, and
`report` sections, so adding them does not disturb the sync.

`CANVAS_TOKEN`, `CANVAS_URL`, and `CHECKOFF_CONFIG` override the token, API URL,
and config path.

Google access uses the credentials already in `common/`, shared with every other
Google module here:

- `common/credentials.json` — the OAuth client (also used by gmail, start_form, sheet)
- `common/token.json` — cached token for the spreadsheets scope, shared with `src/sheet.py`

That token is already at the scope this needs, so normally nothing extra has to
be authorized. Override with `sheet.credentials_file` / `sheet.token_file` if
this ever needs its own.

If the token is missing or can no longer be refreshed, `grade` run from a
terminal prints a `http://localhost:8080` URL to authorize — open it on your own
machine, forwarding the port if you are over SSH. Run non-interactively (from
the scheduler) it raises instead, rather than blocking forever on a browser
round trip nobody is there to complete.

## Identity matching

All Canvas identity resolution lives in `src/canvas_util.py` and is shared by the
check-off tools and the access-control sync, so both agree on who someone is.

A CruzID is derived by falling back through the keys Canvas may be missing:

1. a `login_id` at `ucsc.edu`
2. a bare `login_id` with no domain
3. a `ucsc.edu` email
4. `sis_user_id` — **only when it does not look like a student number**

That last guard matters: UCSC student numbers are all digits, so a numeric
`sis_user_id` is a student number rather than a CruzID and is refused
(`looks_like_cruzid`). Letting one through would insert a number as a CruzID and
key someone's door access off it.

For cross-course work, `transfer` matches people by Canvas user id, then
`login_id`, then `sis_user_id`, and the per-pair log records which key matched
how many people.

Note that `sis_user_id` is only returned by Canvas when the API token has
permission to read SIS data. Without it the field is simply absent and the
fallback never fires — nothing breaks, it just does not help.

## Scheduled runs

`./start_bambu` starts the check-off scheduler alongside the Bambu manager, and
`./stop_bambu` stops both. It runs as its own process rather than inside the
manager loop, because a Canvas roster scan takes far longer than the manager's
10-second cycle and would stall print matching. It writes `pid_checkoff` and
watches the same `common/SPECIAL_BAMBU_STOP` flag the manager does, so it also
exits on its own within a cycle if the pid file goes missing.

| Job | Interval | What it does |
| --- | --- | --- |
| `grade` | hourly | New form responses to Canvas grades |
| `transfer` | hourly | Carry completions between course offerings |
| `staff` | daily | Refresh the staff allow-list |
| `digest` | weekly | Email a summary of everything that changed |

Intervals, the report day and hour, and the default recipient are in
`src/constants.py` under `CHECKOFF_*`. The recipient can be overridden per
deployment with `schedule.report_recipient` in `common/canvas.json`, and
`schedule.transfer_apply: false` makes the hourly transfer a dry run.

The weekly report goes out through `src/bambu_printers/gmail.py` — the same
sender the print notifications use, from the same `slugwork@ucsc.edu` address.
It lists who was newly checked off and by whom, anything that needs attention
(unknown CruzIDs, Canvas errors), what the transfers moved, staff added or
removed, and any job failures.

Scheduler state lives in `checkoff_schedule.json` at the repository root: the
last run time of each job and the events the weekly report has not yet sent. A
restart therefore does not re-fire every job or lose the week's accumulated
changes, and the week is only cleared once the email has actually gone out.

A job that throws is logged, recorded for the report, and retried on the next
cycle — one failing job never stops the others or the loop.

### About the hourly transfer

`transfer` skips anyone whose target grade is already correct, using one
paginated read of the target assignment rather than a request per student. This
matters for running it hourly: re-posting an identical grade would move Canvas's
`graded_at`, and the `report` command's date window reads that field, so an
unguarded hourly transfer would eventually make every student look like they
completed everything in the current week. Set `transfer.force_regrade: true` to
post regardless, which is only useful for a one-off repair.

Even with the skip, each hourly pass still reads every source submission and the
full target roster. If the API volume becomes a problem, raise
`CHECKOFF_TRANSFER_INTERVAL` — transfers are normally a start-of-year migration,
so daily is usually plenty.

## grade

The response sheet is both the queue and the audit log. Columns are
`timestamp | submitter email | CruzIDs | status`; rows with an empty status are
processed and the result written back, so the next run skips them. The CruzID
cell is free text and may hold several IDs separated by commas, spaces,
semicolons, or newlines.

Only staff may submit. The allow-list comes from the access-control database
(`server.is_staff`) when it is reachable, since `src/server/canvas.py` already
keeps it current; otherwise it falls back to a Canvas query cached in
`common/staff.txt`. Force a source with `--staff-source db|canvas|file`.

```bash
./checkoff grade --dry-run    # report only, sheet untouched
./checkoff grade
```

Per-student outcomes: `Done`, `Already done`, `Staff`, `User not found`, or
`Error (…)` with the Canvas message. Everything is also written to the `checkoff`
logger, so it lands in `$LOGS_DIR/checkoff/` with the rest of the system's logs.

## transfer

Canvas issues new course and assignment IDs each offering, so completions have to
be carried across.

**Transfers are dry-run by default; `--apply` is what actually writes grades.**

```bash
./checkoff transfer                            # preview the configured pairs
./checkoff transfer --apply                    # write them
./checkoff transfer --pair 606455:747459 --apply
./checkoff transfer --pairs-csv pairs.csv
./checkoff transfer --interactive              # pick modules, match by name
```

Pairs come from `--pair` and `--pairs-csv` when given, otherwise
`transfer.pairs` in the config. Each pair writes a log and the run writes a
`summary.csv`, both under `log_dir`. Failures are almost always a student missing
from the target assignment's "Assign to" list.

## report

```bash
./checkoff report                                      # config windows
./checkoff report --course 87464 --start 2025-09-19 --end 2025-11-03
./checkoff report --course 87464 --start … --end … --modules soldering sewing
```

Scans the explicit assignment IDs in `report.courses[].assignments` when present,
otherwise every assignment in a module whose name matches `report.module_terms`.
A submission counts as complete if it has a score above zero or is graded, and
its `graded_at` (falling back to `submitted_at`, then `updated_at`) must land in
the window.
