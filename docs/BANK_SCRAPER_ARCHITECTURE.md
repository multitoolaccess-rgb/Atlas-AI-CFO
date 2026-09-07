# Web Scraper Architecture for Bank Connections

## Overview

A web scraper automates the process of logging into your bank's website, navigating to transaction history, and extracting data. It then converts that data into Atlas's import format.

## How It Works (High Level)

```
1. Store encrypted credentials → 2. Automated login → 3. Navigate to statements → 4. Extract transactions → 5. Convert to CSV/OFX → 6. Import into Atlas
```

## Architecture

### Components

```
┌─────────────────────────────────────────────────────────────────┐
│ Atlas Scraper Service (New)                                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ Credential Manager (Secure Storage)                      │    │
│  │ - Encrypt username/password                              │    │
│  │ - Store in local vault                                   │    │
│  └─────────────────────────────────────────────────────────┘    │
│                          ↓                                        │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ Bank-Specific Scrapers                                   │    │
│  │ ├─ Chase Scraper                                         │    │
│  │ ├─ Bank of America Scraper                              │    │
│  │ ├─ Citi Scraper                                         │    │
│  │ └─ Fidelity Scraper                                     │    │
│  │ (Each handles login flow, navigation, extraction)       │    │
│  └─────────────────────────────────────────────────────────┘    │
│                          ↓                                        │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ Data Normalizer                                          │    │
│  │ - Convert to standard transaction format                │    │
│  │ - Generate CSV/OFX output                               │    │
│  └─────────────────────────────────────────────────────────┘    │
│                          ↓                                        │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│ Existing Import Flow (Unchanged)                                │
│ - CSV/OFX parser                                                │
│ - Transaction deduplication                                     │
│ - Database storage                                              │
└─────────────────────────────────────────────────────────────────┘
```

## Technical Implementation

### 1. **Browser Automation (Selenium or Playwright)**

Instead of using APIs, the scraper:
- Opens a browser (headless for automation)
- Logs into the bank's website with your credentials
- Navigates to transaction history
- Extracts transaction data from HTML/tables
- Logs out

**Why this approach?**
- Works with any bank website
- No API integration needed
- Mimics a real user (less likely to be blocked)

### 2. **Data Extraction Strategy**

Each bank scraper identifies:
- HTML table selectors for transactions
- Login form selectors
- Date range pickers
- Download/export buttons

Example for Chase:
```python
# Chase transaction table structure
TRANSACTION_TABLE_SELECTOR = "table.transactions tbody tr"
AMOUNT_SELECTOR = "td.amount"
DATE_SELECTOR = "td.date"
DESCRIPTION_SELECTOR = "td.description"
```

### 3. **Credential Security**

**Local Storage (Single-User):**
```python
# Store credentials encrypted in local database
from cryptography.fernet import Fernet

cipher = Fernet(encryption_key)
encrypted_password = cipher.encrypt(password.encode())
# Store encrypted_password in SQLite
```

**Never transmit credentials to external services** - keep them local only.

### 4. **Failure Handling**

Banks are fragile targets:
- Website layouts change frequently
- 2FA/MFA may interrupt automation
- Session timeouts during scraping
- Rate limiting/blocking

**Resilience strategies:**
```python
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds between retries

try:
    transactions = scraper.fetch_transactions()
except BankWebsiteChangedException:
    # Alert user: "The bank changed their website, 
    # please update scraper or use CSV import"
    logger.error("Bank website layout changed")
except TwoFactorAuthRequired:
    # Manual intervention needed
    return {"status": "2fa_required", "next_action": "manual"}
```

## Implementation for Your Banks

### Chase

```python
class ChaseScraper:
    LOGIN_URL = "https://secure06c.chase.com/web/auth/dashboard"
    
    def login(self, username: str, password: str):
        # 1. Navigate to login page
        self.driver.get(self.LOGIN_URL)
        
        # 2. Enter credentials
        self.driver.find_element("id", "userId").send_keys(username)
        self.driver.find_element("id", "password").send_keys(password)
        self.driver.find_element("id", "signin_button").click()
        
        # 3. Wait for 2FA if needed
        try:
            # Assume 2FA complete when dashboard loads
            self.driver.wait_for_element("id", "account_summary")
        except:
            return {"status": "2fa_required"}
    
    def fetch_transactions(self, days_back: int = 90):
        # Navigate to transaction history
        self.driver.get("https://secure06c.chase.com/web/auth/dashboard#txnhist")
        
        # Set date range
        self.set_date_range(days_back)
        
        # Extract transaction table
        transactions = []
        rows = self.driver.find_elements("css selector", 
                                        "table.transactions tbody tr")
        for row in rows:
            date = row.find_element("css", "td.date").text
            description = row.find_element("css", "td.desc").text
            amount = row.find_element("css", "td.amount").text
            
            transactions.append({
                "date": date,
                "description": description,
                "amount": float(amount.replace("$", "")),
            })
        
        return transactions
```

### Bank of America

```python
class BankOfAmericaScraper:
    LOGIN_URL = "https://secure.bankofamerica.com/web/auth/login"
    
    # Similar structure to Chase but with BoA-specific selectors
    # BoA often requires extra security questions
```

### Fidelity (Investment Accounts)

```python
class FidelityScraper:
    # For brokerage/investment accounts
    # May have better HTML structure for data extraction
    
    def fetch_holdings(self):
        # Extract portfolio positions
        pass
    
    def fetch_transactions(self):
        # Extract trade history
        pass
```

## Integration with Atlas

### Step 1: Create Scraper Service

Create a new service file: `services/scraper-service/`

```
services/scraper-service/
├── app.py                  # FastAPI app
├── scrapers/
│   ├── base.py            # Base scraper class
│   ├── chase.py
│   ├── bofa.py
│   ├── citi.py
│   ├── fidelity.py
│   └── robinhood.py
├── models/
│   └── credentials.py     # Encrypted credential storage
├── normalizer.py          # Convert to standard format
└── requirements.txt       # selenium, playwright, cryptography
```

### Step 2: API Endpoints

```python
# services/scraper-service/app.py

from fastapi import FastAPI, HTTPException
from .scrapers import ChaseScraper, BankOfAmericaScraper
from .models import SavedCredential

app = FastAPI()

@app.post("/api/scrapers/credentials")
async def save_credential(
    bank: str,  # "chase", "bofa", etc.
    username: str,
    password: str,
):
    """Save encrypted bank credentials"""
    credential = SavedCredential(
        bank=bank,
        username=username,
        password=encrypt(password),
    )
    db.add(credential)
    db.commit()
    return {"status": "saved"}

@app.post("/api/scrapers/sync/{bank}")
async def sync_transactions(bank: str):
    """Trigger a scrape and import"""
    credential = db.query(SavedCredential).filter_by(bank=bank).first()
    
    if bank == "chase":
        scraper = ChaseScraper()
    elif bank == "bofa":
        scraper = BankOfAmericaScraper()
    else:
        raise HTTPException(400, f"Unknown bank: {bank}")
    
    try:
        scraper.login(credential.username, decrypt(credential.password))
        transactions = scraper.fetch_transactions()
        
        # Convert to CSV and import
        csv_data = convert_to_csv(transactions)
        
        # Call existing import API
        import_result = await rulesService.import_transactions(csv_data)
        
        return {"status": "success", "imported": len(transactions)}
    
    except TwoFactorRequired:
        return {"status": "2fa_required"}
    except BankWebsiteChanged:
        return {"status": "error", "message": "Bank website changed"}
```

### Step 3: Frontend UI

Add to `/data-connections`:

```tsx
// ui/app/data-connections/page.tsx

<div className="scraper-section">
  <h3>Direct Bank Connections</h3>
  
  {/* Chase */}
  <BankConnectionCard
    bank="Chase"
    connected={hasChaseCredential}
    onConnect={() => showLoginForm("chase")}
    onSync={() => syncBank("chase")}
  />
  
  {/* Bank of America */}
  <BankConnectionCard
    bank="Bank of America"
    connected={hasBoFACredential}
    onConnect={() => showLoginForm("bofa")}
    onSync={() => syncBank("bofa")}
  />
  
  {/* Citi */}
  <BankConnectionCard
    bank="Citi"
    connected={hasCitiCredential}
    onConnect={() => showLoginForm("citi")}
    onSync={() => syncBank("citi")}
  />
  
  {/* Fidelity */}
  <BankConnectionCard
    bank="Fidelity"
    connected={hasFidelityCredential}
    onConnect={() => showLoginForm("fidelity")}
    onSync={() => syncBank("fidelity")}
  />
</div>
```

## Challenges & Limitations

### 1. **Website Changes Break Scrapers**
- Banks redesign websites → selectors change
- You'll get: "Failed to find transaction table"
- **Solution:** Need to maintain scrapers, update selectors quarterly

### 2. **2FA/MFA Interrupts Automation**
- Many banks require SMS/app codes for login
- **Workaround:** Store session cookies after manual login once, reuse
- **Better:** Accept manual 2FA on first setup, then remember session

### 3. **Rate Limiting & IP Banning**
- Banks detect automated access
- They may block the scraper IP
- **Solution:** Add random delays, rotate IPs, respect rate limits

### 4. **Terms of Service Violation**
- Banks' ToS often forbid scraping
- **Reality:** Many personal finance apps do this anyway
- **Legal:** Personal use is grey area; commercial use is riskier

### 5. **Performance & Reliability**
- Scraping is slow (~10-30 seconds per bank)
- Network-dependent (fails if internet/bank is down)
- **Alternative:** Schedule scrapers during off-peak hours

## Practical Recommendation

### Phase 1: MVP (Current - No Code Yet)
- ✅ Keep CSV/OFX import (working now)
- Users manually export from banks monthly
- Zero infrastructure

### Phase 2: Add Single Scraper (Proof of Concept)
- Pick **Chase** (most standardized HTML)
- Build basic scraper with `selenium`
- Test locally on your account
- Handle 2FA manually on first login

### Phase 3: Expand to Other Banks
- Add BoA, Citi scrapers
- Build UI for credential management
- Add sync scheduling

### Phase 4: Production Hardening
- Better error handling
- Scraper maintenance automation
- Consider switching to Plaid if it becomes too brittle

## Risks to Consider

| Risk | Severity | Mitigation |
|------|----------|-----------|
| Bank changes website | High | Quarterly updates, good error alerts |
| 2FA blocks login | Medium | Manual login once, reuse session |
| Credentials exposed | Critical | Local encryption only, never send to cloud |
| IP blocked by bank | Medium | Rotate IPs, add delays, monitor |
| Terms of Service | Medium | Only use personally, don't commercialize |

## When to Use Each Approach

| Approach | When | Why |
|----------|------|-----|
| **CSV Import** | Now | Simple, reliable, no code |
| **Web Scraper** | Later, if motivated | Automates manual exports |
| **Plaid** | At scale | Production-grade, multi-user |
| **Open Banking APIs** | Europe/UK | Free regulatory requirement |

---

## Next Steps

If you want to build this:

1. **Start with Chase scraper** - their website is most consistent
2. **Use Playwright** instead of Selenium (faster, better error messages)
3. **Test locally first** on your own account
4. **Store credentials encrypted locally** - never send to server
5. **Handle 2FA gracefully** - ask for manual intervention once
6. **Add robust error handling** - banks change things frequently

Would you like me to build a working Chase scraper example?
