# ShelterTherm

**Software Based Model Development for Design of Area Specific Shelter for Thermal Comfort Maintenance**  
*INT253 – Web Development in Python Using Django*

ShelterTherm is a Django web application that simulates 24-hour indoor temperatures, ISO 6946 U-values, IMAC adaptive thermal comfort bands, and cooling/heating loads for area-specific shelters before construction.

## Key Features
- **User Accounts**: Sign up, log in, log out, and keep saved shelter designs private.
- **Material Library**: 15 pre-loaded building materials (brick, AAC, RCC, adobe, thatch, GI sheet, EPS/XPS/PUF insulation, etc.) with search & category filters. Protected against deletion if used in a design.
- **Indian Climate Locations**: 12 pre-loaded Indian locations across Hot & Dry, Warm & Humid, Composite, Temperate, and Cold zones, with optional per-design overrides.
- **Multi-Layer Shelter Designer**: Configure dimensions, N/S/E/W windows, door, shading (SHGC), day/night ventilation (ACH), occupants, cool-roof finish, and custom wall/roof/floor layers.
- **Pure Python + NumPy Thermal Engine**: Decoupled 1D finite-volume transient heat-transfer engine (`core/simulation/engine.py`) simulating 10-minute intervals over warm-up + design days.
- **Side-by-Side Comparison & Advice**: Rank 2–4 designs on one chart and get plain-language engineering suggestions.
- **Exports**: Download 10-minute time-series as **CSV** or a formatted summary report as **PDF** (ReportLab).

## Quick Start in VS Code

```bash
# 1. Create and activate a virtual environment
python -m venv venv
# Windows (PowerShell):
venv\Scripts\Activate.ps1
# macOS / Linux:
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create database tables
python manage.py makemigrations
python manage.py migrate

# 4. Seed initial materials, Indian climate locations, and 5 demo designs
python manage.py seed_data

# 5. (Optional) Create an admin superuser
python manage.py createsuperuser

# 6. Run the development server
python manage.py runserver
```

Open **http://127.0.0.1:8000/** in your browser.  
You can log in right away with the seeded demo account: **Username:** `demo` | **Password:** `demo1234` (includes Options A–E from the project report).

## Running Automated Tests
```bash
python manage.py test
```

## Disclaimer
Results are early-stage engineering estimates from a simplified 1D single-zone design-day model and are not a certified building-energy calculation.
