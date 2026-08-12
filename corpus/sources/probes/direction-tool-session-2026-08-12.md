# Probe receipt — Multi-timeframe directional bias tool (session 2026-08-12)

Live run of `analysis/direction.sh OANDA:XAUUSD` (TradingView CDP): pulls OHLCV per timeframe,
runs `analysis/direction.py bias` on each, aggregates a descriptive up/down/flat + confidence table.
The tool restores the starting chart on exit and holds the shared chart lock during its run.

Command: `bash analysis/direction.sh OANDA:XAUUSD`

```
======================================================================
 ESTADO DIRECCIONAL  OANDA:XAUUSD
 DESCRIPTIVO — no es una prediccion (skill probado ~0/negativo)
======================================================================
 TF       SESGO   CONF   P.acierto  NOTA
 ------------------------------------------------------------------
 1 mes    ^ up    0.94   74% hist   trend-up (trend sig R2=0.694) [skill NEGATIVO]
 1 semana ~ flat  0.16   51% hist   trend-down (trend sig R2=0.737) [sin skill] -- ruido
 1 dia    ^ up    0.33   53% hist   trend-up (R2=0.409 no sig) [sin skill]
 1 hora   ~ flat  0.06   51% hist   chop (R2=0.8 no sig) [skill NEGATIVO] -- ruido
 15 min   ~ flat  0.04   57% hist   chop (R2=0.66 no sig) [sin skill] -- ruido
 1 min    ~ flat  0.09   s/cal      trend-down (R2=0.249 no sig) [s/test] -- ruido
 ------------------------------------------------------------------
 ESTRUCTURA: 2 alcista / 0 bajista / 4 plano  |  TFs altos (D/W/M): 2 up / 0 down
 ESTADO ESTRUCTURAL: ALCISTA  (DESCRIPTIVO, no predice)
======================================================================
```

The `P.acierto` column is each call's REAL historical hit-rate; the `[skill NEGATIVO]` / `[sin skill]`
stamps come from the pooled significance test (see `directional-skill-negative-session-2026-08-12.md`).
The tool never promises direction — it reports a descriptive state and defers sizing to the cones.
