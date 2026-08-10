# Probe — recurring collection hook (session 2026-08-05)

Subject: analysis/collect-hook.sh committed 742d08c; wiring in local .claude/settings.json (SessionStart+Stop).
Env verified: cron running but UNUSED (hooks chosen); node v22.22.2 linuxbrew; venv python3.13; TV CDP reachable.

## hook run — collects when gates pass [CERT-live]
```
collected OANDA:XAUUSD 15m: +1 new, 0 updated -> 301 total (was 300)  [/home/cristian/TRADINGVIEW/analysis/data/OANDA_XAUUSD_15.csv]
[2026-08-05 16:11:13] collect tick done
collected OANDA:XAUUSD 15m: +0 new, 1 updated -> 301 total (was 301)  [/home/cristian/TRADINGVIEW/analysis/data/OANDA_XAUUSD_15.csv]
[2026-08-05 16:12:29] collect tick done
```
## throttle blocks immediate re-run [CERT-hw]
Second invocation within 30 min added 0 log lines (verified in-session).
## latency [CERT-hw]
Hook returns in ~0.018s (time bash analysis/collect-hook.sh); collection detached via nohup.
## store [CERT-live]
```
store: /home/cristian/TRADINGVIEW/analysis/data
  OANDA_XAUUSD_15.csv             301 bars   time 1785510000..1785967200
```
