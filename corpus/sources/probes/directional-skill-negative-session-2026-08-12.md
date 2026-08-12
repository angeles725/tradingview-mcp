# Probe receipt — Directional skill is a base-rate mirage (session 2026-08-12)

Local reproducible measurement over the pooled walk-forward directional data.
Pool: corpus/direction-cal-data.jsonl (6448 records, 12 symbols, TFs 1/15/60/D/W/M).

## Significance test  (analysis/direction_significance.py --data corpus/direction-cal-data.jsonl)
```
=== TEST DE SIGNIFICANCIA DEL SKILL DIRECCIONAL ===
  benchmark = mejor predictor CONSTANTE (siempre la clase mayoritaria)
  1: n=8 — muestra insuficiente (<20)
  15: n=84 (84up/0dn, 6 simbolos)
    hit=57.1%  benchmark(siempre-mayoria)=57.1%  -> SKILL=+0.0%
    skill CI95=[-50.0%, +0.0%]  perm p=1.000  => SIN SKILL demostrable
  60: n=198 (155up/43dn, 12 simbolos)
    hit=51.0%  benchmark(siempre-mayoria)=60.6%  -> SKILL=-9.6%
    skill CI95=[-15.7%, -5.0%]  perm p=0.973  => SIN SKILL demostrable
  D: n=279 (210up/69dn, 12 simbolos)
    hit=52.7%  benchmark(siempre-mayoria)=53.0%  -> SKILL=-0.4%
    skill CI95=[-6.2%, +3.1%]  perm p=0.387  => SIN SKILL demostrable
  D [conf>=0.6]: n=33 (33up/0dn, 5 simbolos)
    hit=63.6%  benchmark(siempre-mayoria)=63.6%  -> SKILL=+0.0%
    skill CI95=[-14.3%, +0.0%]  perm p=1.000  => SIN SKILL demostrable
  M: n=549 (397up/152dn, 11 simbolos)
    hit=55.6%  benchmark(siempre-mayoria)=59.2%  -> SKILL=-3.6%
    skill CI95=[-6.5%, -1.4%]  perm p=0.259  => SIN SKILL demostrable
  M [conf>=0.6]: n=122 (122up/0dn, 8 simbolos)
    hit=65.6%  benchmark(siempre-mayoria)=65.6%  -> SKILL=+0.0%
    skill CI95=[+0.0%, +0.0%]  perm p=1.000  => SIN SKILL demostrable
  W: n=438 (306up/132dn, 12 simbolos)
    hit=54.6%  benchmark(siempre-mayoria)=58.7%  -> SKILL=-4.1%
    skill CI95=[-9.8%, +0.5%]  perm p=0.342  => SIN SKILL demostrable
  W [conf>=0.6]: n=49 (48up/1dn, 6 simbolos)
    hit=55.1%  benchmark(siempre-mayoria)=57.1%  -> SKILL=-2.0%
    skill CI95=[-20.0%, +0.0%]  perm p=1.000  => SIN SKILL demostrable
  Nota: skill>0 con CI que NO cruza 0 y p<0.05 = edge real sobre base-rate.
```

## OOS confidence recalibration  (analysis/direction_recalibrate.py --data corpus/direction-cal-data.jsonl)
```
=== RECALIBRACION DE CONFIANZA (OOS, por TF) ===
  1    n=8    -> SIN CALIBRAR (n<40, insufficient evidence)
  15   n=84   up/dn=84/0 hit=57.1% | Brier raw=0.3133 marg=0.2441 iso=0.3032 -> MARGINAL (colapsa a base-rate) val=0.569
  60   n=198  up/dn=155/43 hit=51.0% | Brier raw=0.3029 marg=0.2502 iso=0.2703 -> MARGINAL (colapsa a base-rate) val=0.5145
  D    n=279  up/dn=210/69 hit=52.7% | Brier raw=0.26 marg=0.2679 iso=0.2609 -> cruda (ya era mejor) 
  M    n=549  up/dn=397/152 hit=55.6% | Brier raw=0.2747 marg=0.2474 iso=0.2409 -> ISOTONICA 
  W    n=438  up/dn=306/132 hit=54.6% | Brier raw=0.3236 marg=0.2483 iso=0.2656 -> MARGINAL (colapsa a base-rate) val=0.5065
  Nota: 'marginal' = la confianza cruda no aportaba; la honesta es la base-rate.

-> /home/cristian/TRADINGVIEW/analysis/../corpus/direction-calibration.json
```
