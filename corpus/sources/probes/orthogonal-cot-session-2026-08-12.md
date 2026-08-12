# Probe receipt — COT orthogonal edge probe (session 2026-08-12)

Live weekly XAUUSD bars (TradingView CDP) + CFTC Socrata COT history (remote, no auth).
Command: node src/cli/index.js ohlcv --count 400 (weekly XAU) | \
  python analysis/cot_probe.py --market "GOLD - COMMODITY EXCHANGE INC." --symbol OANDA:XAUUSD
```
=== COT EDGE PROBE  OANDA:XAUUSD  (comm_net, h=4w) ===
  COT rows=1928  price bars=400  extreme signals=110
  COT: n=110 (28up/82dn, 1 simbolos)
    hit=32.7%  benchmark(siempre-mayoria)=63.6%  -> SKILL=-30.9%
    skill CI95=[-30.9%, -30.9%]  perm p=0.997  => SIN SKILL demostrable
  COT [conf>=0.5]: n=58 (19up/39dn, 1 simbolos)
    hit=34.5%  benchmark(siempre-mayoria)=60.3%  -> SKILL=-25.9%
    skill CI95=[-25.9%, -25.9%]  perm p=0.989  => SIN SKILL demostrable
```
