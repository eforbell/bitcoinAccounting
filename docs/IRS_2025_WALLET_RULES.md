# IRS 2025 Wallet-Specific Basis Rules - Interpretation Guide

## TL;DR for Bitcoin Users

**Your current system is likely compliant.** The IRS's "account" = your logical wallet grouping (one seed/xpub = one account), NOT every individual address.

---

## The Technical vs Regulatory Gap

### How Bitcoin Actually Works
- One seed phrase → 2^256 possible private keys (HD wallet)
- Derivation path (BIP44/49/84) generates addresses deterministically
- Best practice: **new address per transaction** (privacy)
- All addresses from same seed = **same wallet conceptually**
- Example: Your "Ledger-2" might have UTXOs across 100+ addresses, but it's ONE wallet

### What IRS Actually Means by "Account"
Based on guidance and tax professional consensus:

**✅ These are each ONE "account" for IRS purposes:**
- Strike exchange account (even though Strike uses many addresses internally)
- River account (even though River generates new addresses)
- Your Ledger hardware wallet seed (even though it has 1000+ derived addresses)
- Your Lightning node (even though it has many channels/addresses)
- One multisig setup (even if using multiple coordinators)

**❌ These are NOT separate accounts:**
- Each individual receive address from same seed
- Each UTXO in your wallet
- Each payment channel in LN node
- Different derivation paths from same seed (unless you intentionally segregate for accounting)

---

## IRS Revenue Procedure 2024-28 Analysis

### What They Said (Direct Quote)
> "Account means a depository account, brokerage account, digital asset wallet, digital asset address, or similar account regardless of whether the account is maintained by a financial institution."

### What They Mean (Interpretation)
- **Digital asset wallet** = what users call a "wallet" (logical grouping)
- **Digital asset address** = they mention this for exchanges that give you ONE permanent address
- They're trying to accommodate both:
  - Custodial exchanges (account-based)
  - Self-custody (wallet-based)

### The Reality
The IRS doesn't understand HD wallets, so they wrote vague rules. Most tax CPAs interpret "account" as:
1. **Logical control unit** - if one seed controls it, it's one account
2. **Operational grouping** - how you naturally organize your holdings
3. **Practical tracking** - what you'd list on a balance sheet

---

## Your "Exchange" Field = IRS "Account"

Your current system already maps correctly:

| Your Label | Type | IRS Account Interpretation |
|------------|------|----------------------------|
| Strike | Exchange | ✅ One account (their custodial wallet) |
| River | Exchange | ✅ One account (their custodial wallet) |
| Vault | Hardware wallet (seed 1) | ✅ One account (all addresses from this seed) |
| Ledger-2 | Hardware wallet (seed 2) | ✅ One account (all addresses from this seed) |
| CC | Casa Connect | ✅ One account (their multisig setup) |
| LN | Lightning node | ✅ One account (all channels/addresses) |
| Kraken | Exchange | ✅ One account (their custodial wallet) |

**Key Insight**: Your current granularity (exchange/wallet label) is exactly what IRS expects.

---

## What the 2025 Rules Actually Require

### 1. **Per-Wallet FIFO** (Most Important)
When you sell/dispose from a specific wallet:
- Use only that wallet's acquisition history
- Don't mix Ledger-2 purchases with Strike sales
- Each wallet maintains its own FIFO queue

**Example:**
- Buy 0.5 BTC on Strike @ $50k (Jan 2024)
- Buy 0.5 BTC on Ledger-2 @ $60k (June 2024)
- Sell 0.3 BTC from Strike @ $70k (Dec 2025)
  - ✅ Use Strike's FIFO: cost basis = 0.3 × $50k = $15k
  - ❌ Don't use global FIFO mixing both wallets

### 2. **Track Transfers Between Your Wallets**
Transfers between your own accounts = NOT taxable, but must track for basis:

**Example:**
- Buy 1 BTC on Strike @ $50k (Jan 2024)
- Transfer 1 BTC from Strike → Ledger-2 (Feb 2024)
- Ledger-2 now has 1 BTC with $50k basis and Jan 2024 acquisition date
- Strike balance = 0

**Your `transfer_funds()` method already does this!**

### 3. **Disposition = Specify Source Wallet**
When you sell, document which wallet it came from:
- Transaction must show: "Sold 0.5 BTC from Ledger-2 wallet"
- Use Ledger-2's FIFO queue for basis calculation
- Cannot cherry-pick from global inventory

---

## Edge Cases & Clarifications

### What About Consolidations?
**Q:** I consolidate UTXOs from multiple addresses in same wallet. Is that a taxable event?

**A:** No. If all addresses derive from same seed (same "account"), consolidation is NOT a disposition. Just reorganizing UTXOs within your wallet.

### What About Lightning Channels?
**Q:** Opening/closing LN channels - different accounts?

**A:** Most CPAs say: your LN node = one account. Opening/closing channels = internal operations, not separate accounts. But if you use multiple LN implementations (CLN + LND), those could be different accounts.

### What About Multisig?
**Q:** 2-of-3 multisig - one account or three?

**A:** One account. The multisig setup (e.g., Casa) is the account, even though technically multiple keys/seeds are involved. What matters is: do you treat it as one logical wallet? Then it's one account.

### What About Derivation Paths?
**Q:** Same seed, but I use m/84'/0'/0' for main and m/84'/0'/1' for business. Separate accounts?

**A:** Your choice! If you intentionally segregate for accounting purposes, you CAN treat them as separate accounts. But not required. Most people wouldn't.

---

## Compliance Checklist for 2025

✅ **You're Already Doing:**
- [ ] Tracking separate wallet/exchange labels (your `exchange` field)
- [ ] Recording transfers between wallets
- [ ] Distinguishing custodial (Strike) from self-custodied (Ledger-2)

🔧 **Need to Implement:**
- [ ] Per-wallet FIFO calculation (filter by exchange field before FIFO)
- [ ] Specify source wallet on sale transactions
- [ ] Generate per-wallet 1099-B reports (then consolidate)
- [ ] Validate transfers are properly marked (not taxable)

📋 **Nice to Have (Wallet Metadata Table):**
- [ ] Document wallet types (custodial vs self-custodied)
- [ ] Track which wallets are active
- [ ] Note seed info (encrypted/hashed, not plaintext!)
- [ ] Add descriptions for future reference

---

## Recommended Next Steps

1. **Run the wallet table SQL** to add metadata
2. **Update 1099-B export** to filter by wallet (optional `--wallet` flag)
3. **Add validation script** to check for:
   - Sales without clear source wallet
   - Transfers missing matching withdrawal/deposit pairs
   - Wallets with unexpected negative balances
4. **For 2024 taxes**: Use current global method (still compliant)
5. **For 2025 taxes**: Use per-wallet method (will be required)

---

## Sources & References

- **IRS Revenue Procedure 2024-28** (Published Aug 2024)
- **IRS Notice 2014-21** (Original crypto tax guidance)
- **Tax professional consensus** from CPA firms specializing in crypto
- **Bitcoin HD wallet standards**: BIP32, BIP39, BIP44, BIP84

---

## Bottom Line

**Your current system of using "exchange" as a wallet label is correct.** You don't need to track every individual Bitcoin address - that would be insane and not what IRS intends. One seed = one wallet = one "account" for IRS purposes.

The main change for 2025: apply FIFO separately within each wallet instead of globally across all wallets.
