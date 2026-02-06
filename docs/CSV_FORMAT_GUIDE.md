# CSV Format Guide — Exchange & Wallet Imports

This guide covers the expected file formats for each supported exchange and
wallet, how to obtain the correct export, and common issues you may encounter.

Use `import_csv --format <name>` at any time to print the expected columns for a
specific parser without opening this file.

---

## Quick Reference

### Exchanges

| Exchange | File type | Auto-detected | Fiat support | Key detection columns |
|----------|-----------|---------------|--------------|----------------------|
| Coinbase | CSV | Yes | No | `Transaction Type`, `Quantity Transacted`, `Spot Price at Transaction` |
| Coinbase Pro | CSV | Yes | Yes (USD) | `portfolio`, `trade id`, `amount/balance unit` |
| Kraken | CSV | Yes | Yes (USD, EUR) | `txid`, `refid`, `aclass` |
| Strike | CSV | Yes | Yes (USD) | `Amount BTC`, `Amount USD`, `Transaction Type` |
| River | CSV | Yes | Yes (USD) | Account Activity: `Reference Code`, `Transaction Type`, `Bitcoin Price Amount`; Bitcoin Activity: 8-column set without `Transaction Type` |
| Swan | CSV | Yes | Yes (USD) | `Amount (BTC)`, `Price (USD)`, `Total (USD)` |
| Cash App | CSV | Yes | No | `Cost Basis ($)`, `Gain/Loss ($)`, `Amount (BTC)` |
| Gemini | CSV or xlsx | Yes | Yes (USD, xlsx only) | CSV: `base-asset`, `quote-asset`, `trade-id`; xlsx: `BTC Amount BTC`, `Withdrawal Destination` |
| Native | CSV | Yes | Yes | Clean or legacy column set (see Native section) |

### Wallets

Wallet imports require `--wallet-name` to identify the wallet for deposit transactions.

| Wallet | File type | Auto-detected | Key detection columns |
|--------|-----------|---------------|----------------------|
| Ledger Live | CSV | Yes | `Operation Date`, `Operation Type`, `Currency` |
| Trezor Suite | CSV | Yes | `TX ID`, `Address`, `Date` |
| Sparrow | CSV | Yes | `Label`, `Balance`, `Value`, `TXID` |
| Coldcard | CSV | Yes | `Type`, `Amount`, `TXID` (without `Address` or `Label`) |

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

## Coinbase Pro

**How to export**: From the Coinbase Pro website, go to **Accounts → (select portfolio) → Statements** and download the CSV for the desired date range. Coinbase Pro exports use a multi-row format where each trade consists of 2-3 rows.

**Expected columns**:
```
portfolio, type, time, amount, balance, amount/balance unit, transfer id, trade id, order id
```

**Row types**:
- `match`: One leg of a trade (buy or sell). Each trade has 2 match rows.
- `fee`: Trading fee. Each trade has 0-1 fee rows.
- `deposit`: Fiat or BTC deposit (single row)
- `withdrawal`: Fiat or BTC withdrawal (single row)

**Transaction types mapped**:

| Source type | Maps to | Notes |
|-------------|---------|-------|
| match (BTC trade) | Trade | Two match rows paired by `trade id`; positive amount = buy leg, negative = sell leg; fees aggregated from fee row |
| match (altcoin) | *(skipped)* | Trades without BTC on either side (e.g., LTC/USD, LINK/USD) are filtered out |
| deposit (BTC) | Deposit | BTC received from external wallet |
| deposit (USD) | Deposit | **Fiat support**: USD deposit captured |
| deposit (USDC) | Deposit | **Fiat support**: Stablecoin deposit captured |
| deposit (altcoin) | *(skipped)* | Non-BTC, non-fiat deposits filtered out |
| withdrawal (BTC) | Withdrawal | Apply `--withdraw-to` or defaults to `CoinbasePro-Withdrawal` |
| withdrawal (USD) | Withdrawal | **Fiat support**: Bank withdrawal; stays at `CoinbasePro` (not self-custody) |
| withdrawal (altcoin) | *(skipped)* | Non-BTC, non-fiat withdrawals filtered out |

**Notes**:
- **Fiat tracking enabled**: USD and stablecoin (USDC, USDT, etc.) deposits/withdrawals captured automatically
- Trade pairing: Parser groups rows by `trade id`, pairs buy/sell legs, and aggregates fees
- BTC filter: Only trades where BTC is on at least one side are imported
- Transfer IDs are preserved in transaction comments for deposits/withdrawals
- Coinbase Pro format is distinct from standard Coinbase exports; the parser auto-detects which format you have

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
- **Fiat tracking enabled**: USD and EUR deposits/withdrawals captured automatically
- Kraken uses non-standard asset codes: `XXBT` and `XBT` both mean BTC;
  `ZUSD` means USD, `ZEUR` means EUR. The parser normalises these automatically.
- Trades appear as **two rows** with the same `refid` — one positive amount (buy leg)
  and one negative amount (sell leg). The parser pairs them before emitting a single
  Trade transaction.
- Only transactions involving BTC or fiat currencies are imported; altcoin-only transactions are filtered out.

---

## Strike

**How to export**: From the Strike app, go to **Settings → Export All Transactions**. The download will be a CSV with 12 columns including BTC and USD amounts, fees, and transaction metadata.

**Expected columns**:
```
Date & Time (UTC), Transaction Type, Description, Amount USD, Fee USD, Amount BTC,
Fee BTC, Reference, BTC Price, Cost Basis (USD), Destination, Transaction Hash, Note
```

**Transaction types mapped**:

| Source type | Maps to | Notes |
|-------------|---------|-------|
| Purchase | Trade | USD spent for BTC; fee captured separately |
| Deposit | Deposit | **Fiat support**: Positive Amount USD = fiat deposit |
| Deposit (Reversal) | Withdrawal | Negative Amount USD + "Reversal" in Description = fiat withdrawal |
| Send (on-chain) | Withdrawal | Destination starts with `bc1`/`1`/`3`; uses `--withdraw-to` for on-chain wallet |
| Send (Lightning BTC) | Withdrawal | Destination starts with `lnbc`; uses separate Lightning wallet target (e.g., `{withdraw_to}-Lightning`) |
| Send (Lightning USD) | Withdrawal | **Fiat support**: Amount USD only (no BTC); pure fiat debit, stays at Strike |

**Notes**:
- **Fiat tracking enabled**: USD deposits and USD sends are captured automatically
- Strike supports both Bitcoin and USD balances; parser imports both
- On-chain and Lightning BTC sends use different destination wallets (hardware wallets can't receive Lightning)
- Lightning USD sends (no BTC amount) are pure fiat transactions
- Deposit reversals are identified by negative Amount USD + "Reversal" in Description
- Destination address and Transaction Hash are preserved in transaction comments

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
- **Fiat tracking enabled**: Cash deposits in Account Activity format are captured as USD Deposit transactions
- Cash-only rows without BTC or fiat (e.g., altcoin-only) are skipped in both formats
- Account Activity is checked first during auto-detection; if both column sets
  are present, the Account Activity path is used
- For Bitcoin Activity trades: fee is only added to the sell amount when it is
  denominated in the same currency as the sent amount

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
| USD Deposit | Deposit | **Fiat support**: USD deposit captured |

**Notes**:
- **Fiat tracking enabled**: USD deposits are now captured (previously skipped)
- Rows with Status `Pending` or `Failed` are silently skipped
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
| Credit + BTC | Deposit | BTC received from external wallet |
| Credit + USD | Deposit | **Fiat support**: USD deposit captured |
| Debit + BTC *(spec contains "Withdrawal")* | Withdrawal | Destination address captured in comment |
| Debit + USD *(spec contains "Withdrawal")* | Withdrawal | **Fiat support**: Bank withdrawal captured |

**Notes**:
- **Fiat tracking enabled** (xlsx only): USD deposits and withdrawals are captured
- The xlsx column set is **dynamic** — it includes per-asset columns only for
  assets you currently hold. The parser discovers columns at runtime, so missing
  columns (GUSD, BAT, etc.) are silently ignored.
- Gemini stores Buy USD amounts and fees as **negative numbers** (accounting
  convention: money leaving = negative). The parser applies `abs()` to all
  amount fields.
- Non-BTC rows (GUSD sells, BAT deposits, etc.) are filtered out via the
  `Symbol` column.

---

## Ledger Live

**How to export**: In Ledger Live, go to **Settings → Accounts**, select a
Bitcoin account, and click **Export operations**. The export includes all
operations across all currencies — the parser filters to BTC automatically.

**Expected columns**:
```
Operation Date, Currency, Operation Type, Amount, Fees, Hash,
Account Name, xpub, Cost Currency, Cost, Cost at Export
```

**Transaction types mapped**:

| Source type | Maps to | Notes |
|-------------|---------|-------|
| IN | Deposit | Uses `--wallet-name` as exchange field |
| OUT | Withdrawal | Apply `--withdraw-to` or defaults to placeholder |

**Notes**:
- Only rows where `Currency == BTC` are imported; all other assets are skipped.
- Withdrawal amounts may appear as negative — the parser applies `abs()`.
- Zero-fee withdrawals get an empty `fee_curr` to avoid orphan currency labels.

**Example**:
```bash
import_csv --wallet-name "Ledger Nano X" ledger_operations.csv
import_csv --wallet-name "Ledger Nano X" --withdraw-to ColdCard ledger_operations.csv
```

---

## Trezor Suite

**How to export**: In Trezor Suite, navigate to **Transactions** and click
**Export** to download the transaction history CSV.

**Expected columns**:
```
Date, Time, Type, Amount, Fee, Address, TX ID
```

**Transaction types mapped**:

| Source type | Maps to | Notes |
|-------------|---------|-------|
| recv / received | Deposit | Uses `--wallet-name` as exchange field |
| sent / send | Withdrawal | Apply `--withdraw-to` or defaults to placeholder |

**Notes**:
- Trezor Suite's BTC export is single-currency — no asset filtering needed.
- Date and Time are separate columns; the parser combines them into one timestamp.
- Type matching is case-insensitive (`RECV`, `recv`, `Recv` all work).
- `TX ID` (two words with space) distinguishes Trezor from Coldcard's `TXID`.

**Example**:
```bash
import_csv --wallet-name "Trezor Model T" trezor_export.csv
```

---

## Sparrow Wallet

**How to export**: In Sparrow Wallet, go to **Tools → Export CSV** to download
the transaction history.

**Expected columns**:
```
Date, Label, Value, Balance, Fee, TXID
```

**Transaction types mapped** (inferred from Value sign):

| Pattern | Maps to | Notes |
|---------|---------|-------|
| Positive Value | Deposit | Uses `--wallet-name` as exchange field |
| Negative Value | Withdrawal | Apply `--withdraw-to` or defaults to placeholder |

**Notes**:
- Sparrow exports values in **satoshis** by default (e.g. `50000000` = 0.5 BTC).
  The parser auto-converts to BTC. Decimal BTC values are also accepted as fallback.
- The `Label` field is preserved as the transaction comment.
- For withdrawals, the label and review comment are combined with `"; "` separator.
- The `Balance` column (running total) is unique to Sparrow — used for detection.

**Example**:
```bash
import_csv --wallet-name "Sparrow Cold" sparrow_export.csv
```

---

## Coldcard

**How to export**: On the Coldcard device, use the **Address Explorer** to
export the transaction history CSV to the SD card.

**Expected columns**:
```
Date, Type, Amount, Fee, TXID
```

**Transaction types mapped**:

| Source type | Maps to | Notes |
|-------------|---------|-------|
| receive / received / in | Deposit | Uses `--wallet-name` as exchange field |
| send / sent / out | Withdrawal | Apply `--withdraw-to` or defaults to placeholder |
| *(empty type, positive amount)* | Deposit | Sign-based fallback for older firmware |
| *(empty type, negative amount)* | Withdrawal | Sign-based fallback for older firmware |

**Notes**:
- Amounts are in **decimal BTC** (not satoshis like Sparrow).
- Supports both type-based and sign-based transaction detection to handle
  firmware version variations where the Type column may be empty.
- `TXID` (one word) distinguishes Coldcard from Trezor's `TX ID` (two words).
- Type matching is case-insensitive.

**Example**:
```bash
import_csv --wallet-name "Coldcard Mk4" coldcard_export.csv
```

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
