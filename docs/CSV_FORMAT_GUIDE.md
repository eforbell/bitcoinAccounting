# CSV Format Guide — Exchange Imports

This guide covers the expected file formats for each supported exchange, how to
obtain the correct export, and common issues you may encounter.

Use `import_csv --format <name>` at any time to print the expected columns for a
specific parser without opening this file.

---

## Quick Reference

| Exchange | File type | Auto-detected | Key detection columns |
|----------|-----------|---------------|----------------------|
| Coinbase | CSV | Yes | `Transaction Type`, `Quantity Transacted`, `Spot Price at Transaction` |
| Kraken | CSV | Yes | `txid`, `refid`, `aclass` |
| Strike | CSV | Yes | `BTC Amount`, `USD Amount`, `Type` |
| River | CSV | Yes | Account Activity: `Reference Code`, `Transaction Type`, `Bitcoin Price Amount`; Bitcoin Activity: 8-column set without `Transaction Type` |
| Swan | CSV | Yes | `Amount (BTC)`, `Price (USD)`, `Total (USD)` |
| Cash App | CSV | Yes | `Cost Basis ($)`, `Gain/Loss ($)`, `Amount (BTC)` |
| Gemini | CSV or xlsx | Yes | CSV: `base-asset`, `quote-asset`, `trade-id`; xlsx: `BTC Amount BTC`, `Withdrawal Destination` |
| Native | CSV | Yes | Clean or legacy column set (see Native section) |

---

## Coinbase

**How to export**: In the Coinbase app or website, navigate to your transaction
history and look for a CSV download or export option. The export should contain
all transaction types across all assets — the parser filters to BTC automatically.

**Expected columns**:
```
Timestamp, Transaction Type, Asset, Quantity Transacted, Spot Price Currency,
Spot Price at Transaction, Subtotal, Total, Fees, Notes
```

**Transaction types mapped**:

| Source type | Maps to | Notes |
|-------------|---------|-------|
| Buy | Trade | Sell amount = Total (includes fee) |
| Sell | Trade | Buy amount = Total |
| Send | Withdrawal | Apply `--withdraw-to` or defaults to `Coinbase-Withdrawal` |
| Receive | Deposit | |
| Rewards Income | Interest Income | |
| Learning Reward | Interest Income | |
| Coinbase Earn | Interest Income | |
| Convert | Trade | Only the BTC leg is imported |

**Notes**:
- Only rows where `Asset == BTC` are imported; all other assets are skipped.
- `Subtotal` is preferred for the USD amount; falls back to `Quantity × Spot Price`
  when Subtotal is empty.

---

## Kraken

**How to export**: From the Kraken website, go to **Funds → History → Ledger**
and export as CSV. Make sure the date range covers all transactions you want to
import. Export the **Ledger** format (not the Trades format — the column sets differ).

**Expected columns** (13-column ledger format):
```
txid, refid, time, type, subtype, aclass, asset, amount, fee, balance
```

**Transaction types mapped**:

| Source type | Maps to | Notes |
|-------------|---------|-------|
| trade | Trade | Two rows share the same `refid`; parser combines them |
| deposit | Deposit | |
| withdrawal | Withdrawal | Apply `--withdraw-to` or defaults to `Kraken-Withdrawal` |
| staking | Interest Income | |
| reward | Interest Income | |
| dividend | Interest Income | |

**Notes**:
- Kraken uses non-standard asset codes: `XXBT` and `XBT` both mean BTC;
  `ZUSD` means USD. The parser normalises these automatically.
- Trades appear as **two rows** with the same `refid` — one positive amount (buy leg)
  and one negative amount (sell leg). The parser pairs them before emitting a single
  Trade transaction.
- Only transactions involving BTC are imported.

---

## Strike

**How to export**: From the Strike app, look for a transaction history or
statement export option. The download should be a CSV with the columns listed below.

**Expected columns**:
```
Date, Type, Description, BTC Amount, USD Amount
```
Optional columns (present in some exports): `Fee (USD)`, `Fee (BTC)`

**Transaction types mapped**:

| Source type | Maps to | Notes |
|-------------|---------|-------|
| Purchase | Trade | Fee added to USD Amount for total cost |
| Send | Withdrawal | Apply `--withdraw-to` or defaults to `Strike-Withdrawal` |
| Payment | Withdrawal | Lightning Network payment |
| Receive | Deposit | |

**Notes**:
- Strike is Bitcoin-only; no asset filtering is needed.
- Fee handling: BTC fee is preferred when present; falls back to USD fee.

---

## River

River ships **two different CSV exports**. The parser auto-detects which one you have.

### Account Activity export (21 columns)

**How to export**: From the River app or website, look for a full account activity
or statement export.

**Key columns** (selected from the 21-column set):
```
Date, Reference Code, Transaction Type, Sent Amount, Sent Currency,
Received Amount, Received Currency, Fee Amount, Fee Currency, Total Amount,
Total Currency, Bitcoin Price Amount, ...
```

**Transaction types mapped**:

| Source type | Maps to |
|-------------|---------|
| Buy | Trade |
| Send | Withdrawal |
| Interest Payout | Interest Income |

### Bitcoin Activity export (8 columns)

**How to export**: From the River app, look for a Bitcoin-specific activity or
history export.

**Expected columns**:
```
Date, Sent Amount, Sent Currency, Received Amount, Received Currency,
Fee Amount, Fee Currency, Tag
```

**Transaction types mapped** (inferred from Tag and amounts):

| Tag / pattern | Maps to |
|---------------|---------|
| Buy | Trade |
| Interest | Interest Income |
| *(empty tag, BTC sent)* | Withdrawal |

**Notes**:
- Cash-only rows (no BTC on either side) are skipped in both formats.
- Account Activity is checked first during auto-detection; if both column sets
  are present, the Account Activity path is used.
- For Bitcoin Activity trades: fee is only added to the sell amount when it is
  denominated in the same currency as the sent amount.

---

## Swan

**How to export**: From the Swan Bitcoin app or website, navigate to your
transaction or purchase history and look for a CSV export option.

**Expected columns**:
```
Date, Type, Amount (BTC), Price (USD), Total (USD), Fee (USD), Status
```

**Transaction types mapped**:

| Source type | Maps to | Notes |
|-------------|---------|-------|
| Purchase | Trade | Tagged with group `DCA` |
| Withdrawal | Withdrawal | Apply `--withdraw-to` or defaults to `Swan-Withdrawal` |
| Deposit | Deposit | BTC received from external wallet |
| USD Deposit | *(skipped)* | No BTC involved |

**Notes**:
- Rows with Status `Pending` or `Failed` are silently skipped.
- `Total (USD)` already includes the fee — it represents the full USD amount
  deducted from your account. The fee is still tracked separately for tax reporting.

---

## Cash App

**How to export**: In the Cash App, navigate to **Bitcoin → Statement** (or a
similar path depending on app version) and download the gain/loss CSV. This is
the Bitcoin-specific tax statement export.

**Expected columns**:
```
Date, Transaction Type, Amount (BTC), Market Price ($),
Cost Basis ($), Proceeds ($), Gain/Loss ($), Note
```

**Transaction types mapped**:

| Source type | Maps to | Notes |
|-------------|---------|-------|
| Purchase | Trade | Sell = Cost Basis; falls back to `Amount × Market Price` |
| Sale | Trade | Buy = Proceeds; falls back to `Amount × Market Price` |
| Send | Withdrawal | Apply `--withdraw-to` or defaults to `CashApp-Withdrawal` |
| Receive | Deposit | See warning note below |

**Notes**:
- Cash App does **not** include cost basis for Bitcoin received from external
  wallets. When `Cost Basis` is `$0` or empty on a Receive, the parser emits a
  warning and tags the transaction comment with `"Cost basis $0 - verify before
  tax filing"`. Review these after importing and set the correct cost basis before
  filing taxes.
- No fee information is available in this export format; fee fields are zeroed.

---

## Gemini

Gemini supports **two export formats**; the parser handles both automatically.

### CSV export (third-party gemini-exports tool)

**How to obtain**: The `gemini-exports` command-line tool (third-party) pulls
your trade history via the Gemini API and outputs CSV.

**Expected columns**:
```
time, base-asset, quote-asset, type, price, quantity, total, fee, fee-currency, trade-id
```

**Transaction types mapped**:

| Source type | Maps to | Notes |
|-------------|---------|-------|
| Buy | Trade | Sell = total; falls back to `price × quantity` |
| Sell | Trade | Buy = total; same fallback |
| Deposit | Deposit | |
| Withdrawal | Withdrawal | Apply `--withdraw-to` or defaults to `Gemini-Withdrawal` |
| Earn / Earn Interest | Interest Income | Comment: "Gemini Earn" |

### xlsx export (native "Account History" download)

**How to obtain**: From the Gemini website, go to your account history and
download the **Account History** xlsx file (the native export, not a CSV).

**Key columns used** (the file contains 30+ columns; only these are read):
```
Date, Type, Symbol, Specification,
USD Amount USD, Fee (USD) USD,
BTC Amount BTC, Fee (BTC) BTC,
Withdrawal Destination
```

**Transaction types mapped**:

| Type + Symbol | Maps to | Notes |
|---------------|---------|-------|
| Buy + BTCUSD | Trade | USD amounts stored as negative; abs() applied |
| Sell + BTCUSD | Trade | BTC amount stored as negative; abs() applied |
| Credit + BTC | Deposit | |
| Debit + BTC *(spec contains "Withdrawal")* | Withdrawal | Destination address captured in comment |

**Notes**:
- The xlsx column set is **dynamic** — it includes per-asset columns only for
  assets you currently hold. The parser discovers columns at runtime, so missing
  columns (GUSD, BAT, etc.) are silently ignored.
- Gemini stores Buy USD amounts and fees as **negative numbers** (accounting
  convention: money leaving = negative). The parser applies `abs()` to all
  amount fields.
- Non-BTC rows (GUSD sells, BAT deposits, etc.) are filtered out via the
  `Symbol` column.

---

## Native format

The Native parser imports CSV files that are already in the ledger's own column
layout. Useful for re-importing previous exports or migrating data from another
source.

### Clean format (preferred)
```
trans_type, buy, buy_curr, sell, sell_curr, fee, fee_curr, exchange, group, comment, created_date
```

### Legacy format (also accepted)
```
Type, Buy, Buy Cur., Sell, Sell Cur., Fee, Fee Cur., Exchange, Group, Comment, Date
```

Both formats are auto-detected. Transaction types are passed through unchanged —
no type mapping is applied.

---

## Troubleshooting

### "Could not auto-detect parser"

The file's header row doesn't match any registered parser's detection markers.
Possible causes:
- The export format has changed since the parser was written.
- The file is from an unsupported exchange.
- The file has a BOM or extra whitespace in the header row.

**Fix**: Specify the parser explicitly with `--source <name>`. If that also fails,
compare your file's first row against the expected columns (use
`import_csv --format <name>`).

### "No transactions found in file"

The parser ran but all rows were filtered out. Common reasons:
- **Coinbase / Kraken / Gemini**: The export contains only non-BTC transactions.
  These parsers extract BTC only.
- **Swan**: All rows have Status `Pending` or `Failed`.
- **Kraken**: You exported the "Trades" CSV instead of the "Ledger" CSV. Make
  sure you use the ledger export.

### Duplicate detection warnings

`import_csv` checks for existing transactions with the same date, exchange,
amount, and type before importing. If duplicates are flagged:
- Use `--dry-run` to review the full list before deciding whether to proceed.
- Re-exporting from the exchange and re-importing is safe; duplicates are
  warned but not blocked by default.

### Cash App "$0 cost basis" warnings

Receives from external wallets have no cost basis in the Cash App export.
The parser flags these with a warning. After importing, find these transactions
in the ledger and set the correct cost basis (the price you originally paid in
your source wallet).

### Gemini xlsx "no default style" warning

This is a harmless warning from the openpyxl library, not a parser error.
Gemini's native xlsx export lacks a default cell style, which triggers the
warning. The file is parsed correctly despite it.
