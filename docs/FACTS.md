# Facts worth remembering

Short, verified facts about the demo and the model that are easy to forget and expensive to rediscover. One line of context each; the measurement or the code it comes from is named.

## Radio

- **ZW's command-post link has 1.6 dB of margin by design.** In `collapse_01`, the safety checker's radio prior puts the P-1 zone ZW's target at −86.4 dBm against the −88 dBm link floor (`LINK_DOWN_DBM`), with no furniture. Anything that sits on the straight line from the command post into Office A/B (a 1.9 m bookshelf in the exported furniture, a new wall, a relay moved) makes ZW the first zone to predict dead and the checker rejects P-1 even after "allow dark". ZB has 3.9 dB, ZNE is dead on purpose (−135 dBm). Measured 2026-11-08 with `rssi(prior, cmd, centroid)`; see rayan.md 17:00 and the furniture-loss PR.
- **Furniture costs 1 dB per piece crossed in the radio model** (`FURNITURE_LOSS_DB`, `DZ_OBSTACLES=1`), not the metal-wall 22 dB: Rappaport, *Wireless Communications: Principles and Practice* (2nd ed.), Table 4.3, light partitions and light machinery 1–4 dB at 1.3 GHz; the low end because the exported footprints are open shelving and desks. A piece can declare its own `loss_db`. Walls and rubble keep the materials table.
