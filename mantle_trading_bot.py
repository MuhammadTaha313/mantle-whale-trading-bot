"""
Mantle AI Trading Bot - Turing Test Hackathon 2026
===================================================
Track: AI Trading & Strategy

Setup:
1. pip install web3 requests python-dotenv
2. PRIVATE_KEY aur WALLET_ADDRESS fill karo
3. python mantle_trading_bot.py

Network: Mantle Mainnet
DEX: Merchant Moe
"""

import os
import time
import requests
import logging
from web3 import Web3
from datetime import datetime

# ═══════════════════════════════════════════
#         YAHAN APNI SETTINGS BHARO
# ═══════════════════════════════════════════

PRIVATE_KEY     = "YOUR_PRIVATE_KEY_HERE"   # Apni private key
WALLET_ADDRESS  = "YOUR_WALLET_ADDRESS"      # Apna wallet address

# Mantle Network Settings
RPC_URL  = "https://rpc.mantle.xyz"
CHAIN_ID = 5000

# Trading Settings
CHECK_INTERVAL   = 30     # 30 sec mein ek baar check
STOP_LOSS_PCT    = -8     # -8% pe sell
TAKE_PROFIT_PCT  = +15    # +15% pe sell
MIN_VOLUME_USD   = 10000  # Minimum $10k volume chahiye signal ke liye

# ═══════════════════════════════════════════
#         MANTLE TOKEN ADDRESSES
# ═══════════════════════════════════════════

TOKENS = {
    "MNT":  "0x78c1b0C915c4FAA5FffA6CAbf0219DA63d7f4cb8",
    "WETH": "0xdEAddEaDdeadDEadDEADDEAddEADDEAddead1111",
    "USDT": "0x201EBa5CC46D216Ce6DC03F6a759e8E766e956aE",
    "USDC": "0x09Bc4E0D864854c6aFB6eB9A9cdF58aC190D0dF9",
    "mETH": "0xcDA86A272531e8640cD7F1a92c01839911B90bb0",
}

# ═══════════════════════════════════════════
#                 LOGGING
# ═══════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler('mantle_bot.log'),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# ═══════════════════════════════════════════
#              AI SIGNAL ENGINE
# ═══════════════════════════════════════════

class AISignalEngine:
    """
    Simple AI logic jo price + volume dekhke signal deta hai
    """

    def __init__(self):
        self.price_history = {}

    def get_token_data(self, token_address):
        """DexScreener se token data fetch karo"""
        try:
            url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                pairs = r.json().get('pairs', [])
                # Sirf Mantle chain ke pairs lo
                mantle_pairs = [p for p in pairs if p.get('chainId') == 'mantle']
                if mantle_pairs:
                    # Sabse zyada liquidity wala pair lo
                    best = max(mantle_pairs, key=lambda x: float(x.get('liquidity', {}).get('usd', 0) or 0))
                    return {
                        'symbol':          best.get('baseToken', {}).get('symbol', '?'),
                        'price_usd':       float(best.get('priceUsd', 0) or 0),
                        'liquidity_usd':   float(best.get('liquidity', {}).get('usd', 0) or 0),
                        'volume_5m':       float(best.get('volume', {}).get('m5', 0) or 0),
                        'volume_1h':       float(best.get('volume', {}).get('h1', 0) or 0),
                        'price_change_5m': float(best.get('priceChange', {}).get('m5', 0) or 0),
                        'price_change_1h': float(best.get('priceChange', {}).get('h1', 0) or 0),
                        'pair_address':    best.get('pairAddress', ''),
                    }
        except Exception as e:
            log.error(f"DexScreener error: {e}")
        return None

    def analyze(self, symbol, data):
        """
        AI Analysis:
        - Volume spike detect karo
        - Price momentum check karo
        - BUY / SELL / HOLD signal do
        """
        if not data:
            return "HOLD", "No data available"

        price    = data['price_usd']
        vol_5m   = data['volume_5m']
        vol_1h   = data['volume_1h']
        chg_5m   = data['price_change_5m']
        chg_1h   = data['price_change_1h']
        liq      = data['liquidity_usd']

        reasons = []

        # --- Liquidity check ---
        if liq < 5000:
            return "HOLD", "❌ Low liquidity"

        # --- Volume spike check ---
        avg_vol_per_5m = vol_1h / 12 if vol_1h > 0 else 0
        vol_spike = avg_vol_per_5m > 0 and vol_5m > avg_vol_per_5m * 2

        # --- Price momentum ---
        strong_pump  = chg_5m > 3 and chg_1h > 5
        mild_pump    = chg_5m > 1.5
        dump_signal  = chg_5m < -5 or chg_1h < -10

        # --- Scoring ---
        score = 0
        if vol_spike:
            score += 2
            reasons.append("📈 Volume spike")
        if strong_pump:
            score += 3
            reasons.append("🚀 Strong pump")
        elif mild_pump:
            score += 1
            reasons.append("↗️ Mild pump")
        if dump_signal:
            score -= 5
            reasons.append("📉 Dump signal")

        # --- Decision ---
        if dump_signal:
            return "SELL", " | ".join(reasons)
        elif score >= 3:
            return "BUY", " | ".join(reasons)
        elif score >= 1:
            return "WATCH", " | ".join(reasons)
        else:
            return "HOLD", "No clear signal"

# ═══════════════════════════════════════════
#              MANTLE BOT
# ═══════════════════════════════════════════

class MantleBot:

    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(RPC_URL))
        self.ai  = AISignalEngine()
        self.positions = {}  # Active positions

        if self.w3.is_connected():
            log.info(f"✅ Connected to Mantle Network | Chain ID: {CHAIN_ID}")
        else:
            log.error("❌ Mantle Network se connect nahi hua!")
            exit(1)

        # Wallet check
        if WALLET_ADDRESS != "YOUR_WALLET_ADDRESS":
            bal = self.get_mnt_balance()
            log.info(f"💼 Wallet: {WALLET_ADDRESS[:10]}... | Balance: {bal:.4f} MNT")

    def get_mnt_balance(self):
        """MNT balance check karo"""
        try:
            bal_wei = self.w3.eth.get_balance(
                Web3.to_checksum_address(WALLET_ADDRESS)
            )
            return self.w3.from_wei(bal_wei, 'ether')
        except:
            return 0

    def scan_tokens(self):
        """Saare tokens scan karo aur signals dhundo"""
        log.info(f"\n{'═'*55}")
        log.info(f"🔍 Scanning {len(TOKENS)} tokens on Mantle...")
        log.info(f"{'═'*55}")

        signals = []

        for symbol, address in TOKENS.items():
            data = self.ai.get_token_data(address)

            if data:
                signal, reason = self.ai.analyze(symbol, data)
                price = data['price_usd']
                liq   = data['liquidity_usd']
                chg   = data['price_change_5m']

                # Color coding for signals
                if signal == "BUY":
                    icon = "🟢"
                elif signal == "SELL":
                    icon = "🔴"
                elif signal == "WATCH":
                    icon = "🟡"
                else:
                    icon = "⚪"

                log.info(
                    f"{icon} {symbol:<6} | "
                    f"${price:<10.4f} | "
                    f"Liq: ${liq:<10,.0f} | "
                    f"5m: {chg:+.1f}% | "
                    f"{signal} → {reason}"
                )

                if signal in ["BUY", "SELL"]:
                    signals.append({
                        'symbol':  symbol,
                        'address': address,
                        'signal':  signal,
                        'reason':  reason,
                        'data':    data,
                    })
            else:
                log.warning(f"⚠️  {symbol:<6} | Data fetch failed")

            time.sleep(1)  # Rate limit se bachne ke liye

        return signals

    def process_signals(self, signals):
        """Signals process karo"""
        for s in signals:
            sym    = s['symbol']
            sig    = s['signal']
            reason = s['reason']
            data   = s['data']

            if sig == "BUY" and sym not in self.positions:
                log.info(f"\n🎯 BUY SIGNAL: {sym}")
                log.info(f"   Reason: {reason}")
                log.info(f"   Price: ${data['price_usd']:.6f}")
                log.info(f"   ⚠️  DEMO MODE: Real transaction ke liye private key set karo")

                # Position track karo (demo mode)
                self.positions[sym] = {
                    'buy_price': data['price_usd'],
                    'time':      datetime.now(),
                    'reason':    reason,
                }

            elif sig == "SELL" and sym in self.positions:
                buy_price = self.positions[sym]['buy_price']
                cur_price = data['price_usd']
                pnl = ((cur_price - buy_price) / buy_price * 100) if buy_price > 0 else 0

                log.info(f"\n⚡ SELL SIGNAL: {sym}")
                log.info(f"   Reason: {reason}")
                log.info(f"   Buy: ${buy_price:.6f} → Now: ${cur_price:.6f} | PnL: {pnl:+.1f}%")
                log.info(f"   ⚠️  DEMO MODE: Real transaction ke liye private key set karo")

                del self.positions[sym]

    def show_positions(self):
        """Active positions dikhao"""
        if not self.positions:
            return
        log.info(f"\n📊 Active Positions ({len(self.positions)}):")
        for sym, pos in self.positions.items():
            data = self.ai.get_token_data(TOKENS.get(sym, ""))
            if data:
                cur  = data['price_usd']
                buy  = pos['buy_price']
                pnl  = ((cur - buy) / buy * 100) if buy > 0 else 0
                icon = "🟢" if pnl >= 0 else "🔴"
                log.info(f"   {icon} {sym}: Buy ${buy:.6f} | Now ${cur:.6f} | PnL: {pnl:+.1f}%")

                # Stop loss / Take profit check
                if pnl <= STOP_LOSS_PCT:
                    log.warning(f"   🛑 STOP LOSS triggered for {sym}! ({pnl:.1f}%)")
                elif pnl >= TAKE_PROFIT_PCT:
                    log.info(f"   🎯 TAKE PROFIT triggered for {sym}! ({pnl:.1f}%)")

    def run(self):
        """Main bot loop"""
        log.info("🚀 Mantle AI Trading Bot - Turing Test Hackathon 2026")
        log.info(f"⚙️  Check interval: {CHECK_INTERVAL}s | SL: {STOP_LOSS_PCT}% | TP: {TAKE_PROFIT_PCT}%")
        log.info("📝 DEMO MODE - Sirf signals dikhayega, real trade nahi karega\n")

        cycle = 0
        while True:
            try:
                cycle += 1
                log.info(f"\n🔄 Cycle #{cycle} | {datetime.now().strftime('%H:%M:%S')}")

                # Active positions check karo
                if self.positions:
                    self.show_positions()

                # Tokens scan karo
                signals = self.scan_tokens()

                # Signals process karo
                if signals:
                    log.info(f"\n⚡ {len(signals)} signal(s) mila!")
                    self.process_signals(signals)
                else:
                    log.info("\n😴 Koi signal nahi mila, wait kar rahe hain...")

                log.info(f"\n⏳ {CHECK_INTERVAL} seconds baad agla scan...")
                time.sleep(CHECK_INTERVAL)

            except KeyboardInterrupt:
                log.info("\n⛔ Bot band kar diya. Alvida! 👋")
                break
            except Exception as e:
                log.error(f"Error: {e}")
                time.sleep(10)


# ═══════════════════════════════════════════
#                  MAIN
# ═══════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 55)
    print("  🤖 Mantle AI Trading Bot")
    print("  Turing Test Hackathon 2026")
    print("  Track: AI Trading & Strategy")
    print("=" * 55)

    bot = MantleBot()
    bot.run()
