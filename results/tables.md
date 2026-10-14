### Topologies and stress calibration

| Topology | Buses | Lines | Real tie switches | PV nameplate / total load (calibrated) | Test-year curtailment hours (DE / IN-solar) |
|---|---|---|---|---|---|
| mv_oberrhein | 179 | 181 | 6 | 1.78x | 10.8% / 25.6% |
| CIGRE MV | 15 | 15 | 3 | 0.34x | 9.7% / 23.8% |
| Kerber Dorfnetz | 116 | 114 | 0 | 3.34x | 11.1% / 25.6% |
| Kerber Vorstadtnetz | 294 | 292 | 0 | 7.46x | 9.5% / 23.8% |

### Product 1 — German real data (OPSD hourly solar + demand)

Test = 2019 (never seen in training). Errors in MW per bus-hour over all hours. Event F1 = does the network curtail next hour (>0.01 MW), threshold picked on 2018 validation.

| Topology | Model | MAE | RMSE | Network-total correlation | Event F1 (P / R) |
|---|---|---|---|---|---|
| mv_oberrhein | mean | 0.00737 | 0.033 | n/a | 0.000 (0.00 / 0.00) |
| mv_oberrhein | persistence | 0.00162 | 0.0171 | 0.896 | 0.821 (0.82 / 0.82) |
| mv_oberrhein | GCN | 0.00231 | 0.0097 | 0.989 | 0.953 (0.94 / 0.97) |
| mv_oberrhein | GBM-graph **(best)** | 0.00079 | 0.00732 | 0.994 | 0.962 (0.96 / 0.96) |
| mv_oberrhein | GBM-nolag | 0.000817 | 0.00732 | 0.994 | 0.954 (0.93 / 0.98) |
| CIGRE MV | mean | 0.0175 | 0.0605 | n/a | 0.000 (0.00 / 0.00) |
| CIGRE MV | persistence | 0.00381 | 0.0351 | 0.875 | 0.811 (0.82 / 0.80) |
| CIGRE MV | GCN | 0.00594 | 0.0194 | 0.971 | 0.948 (0.94 / 0.96) |
| CIGRE MV | GBM-graph **(best)** | 0.00201 | 0.0163 | 0.977 | 0.958 (0.94 / 0.97) |
| CIGRE MV | GBM-nolag | 0.00208 | 0.0164 | 0.975 | 0.952 (0.95 / 0.96) |
| Kerber Dorfnetz | mean | 0.000139 | 0.000902 | n/a | 0.000 (0.00 / 0.00) |
| Kerber Dorfnetz | persistence | 2.8e-05 | 0.000402 | 0.909 | 0.827 (0.82 / 0.83) |
| Kerber Dorfnetz | GCN | 2.91e-05 | 0.000183 | 0.99 | 0.961 (0.95 / 0.98) |
| Kerber Dorfnetz | GBM-graph **(best)** | 2.01e-05 | 0.00018 | 0.992 | 0.954 (0.94 / 0.96) |
| Kerber Dorfnetz | GBM-nolag | 2.06e-05 | 0.000181 | 0.991 | 0.954 (0.96 / 0.95) |
| Kerber Vorstadtnetz | mean | 0.000103 | 0.000607 | n/a | 0.000 (0.00 / 0.00) |
| Kerber Vorstadtnetz | persistence | 2.27e-05 | 0.000315 | 0.894 | 0.812 (0.78 / 0.84) |
| Kerber Vorstadtnetz | GCN **(best)** | 2.83e-05 | 0.000162 | 0.989 | 0.957 (0.95 / 0.97) |
| Kerber Vorstadtnetz | GBM-graph | 2.05e-05 | 0.000166 | 0.992 | 0.953 (0.96 / 0.95) |
| Kerber Vorstadtnetz | GBM-nolag | 2.29e-05 | 0.000187 | 0.99 | 0.949 (0.96 / 0.94) |

| Topology | Train / val / test days | Best model beats mean (MAE) | beats persistence (RMSE) | beats persistence (MAE) |
|---|---|---|---|---|
| mv_oberrhein | 1088 / 365 / 363 | True | True | True |
| CIGRE MV | 1088 / 365 / 363 | True | True | True |
| Kerber Dorfnetz | 1088 / 365 / 363 | True | True | True |
| Kerber Vorstadtnetz | 1088 / 365 / 363 | True | True | False |

### Product 1 — Indian solar (NASA POWER, Rajasthan) + German demand shape

Test = 2019 (never seen in training). Errors in MW per bus-hour over all hours. Event F1 = does the network curtail next hour (>0.01 MW), threshold picked on 2018 validation.

| Topology | Model | MAE | RMSE | Network-total correlation | Event F1 (P / R) |
|---|---|---|---|---|---|
| mv_oberrhein | mean | 0.0235 | 0.0683 | n/a | 0.000 (0.00 / 0.00) |
| mv_oberrhein | persistence | 0.00615 | 0.0369 | 0.867 | 0.833 (0.84 / 0.83) |
| mv_oberrhein | GCN | 0.0053 | 0.0187 | 0.981 | 0.968 (0.95 / 0.98) |
| mv_oberrhein | GBM-graph **(best)** | 0.00256 | 0.0152 | 0.985 | 0.973 (0.97 / 0.98) |
| mv_oberrhein | GBM-nolag | 0.00258 | 0.0153 | 0.984 | 0.972 (0.97 / 0.98) |
| CIGRE MV | mean | 0.0561 | 0.121 | n/a | 0.000 (0.00 / 0.00) |
| CIGRE MV | persistence | 0.0161 | 0.0718 | 0.852 | 0.825 (0.82 / 0.82) |
| CIGRE MV | GCN | 0.0112 | 0.036 | 0.969 | 0.964 (0.95 / 0.98) |
| CIGRE MV | GBM-graph | 0.00718 | 0.033 | 0.971 | 0.966 (0.97 / 0.96) |
| CIGRE MV | GBM-nolag **(best)** | 0.00725 | 0.033 | 0.97 | 0.968 (0.97 / 0.96) |
| Kerber Dorfnetz | mean | 0.000403 | 0.00175 | n/a | 0.000 (0.00 / 0.00) |
| Kerber Dorfnetz | persistence | 9.35e-05 | 0.000814 | 0.885 | 0.835 (0.81 / 0.86) |
| Kerber Dorfnetz | GCN | 5.68e-05 | 0.000347 | 0.986 | 0.970 (0.97 / 0.97) |
| Kerber Dorfnetz | GBM-graph **(best)** | 4.63e-05 | 0.000327 | 0.987 | 0.969 (0.96 / 0.98) |
| Kerber Dorfnetz | GBM-nolag | 4.78e-05 | 0.000335 | 0.985 | 0.967 (0.96 / 0.98) |
| Kerber Vorstadtnetz | mean | 0.000351 | 0.0013 | n/a | 0.000 (0.00 / 0.00) |
| Kerber Vorstadtnetz | persistence | 9.55e-05 | 0.000701 | 0.863 | 0.826 (0.83 / 0.82) |
| Kerber Vorstadtnetz | GCN | 8.12e-05 | 0.000346 | 0.98 | 0.954 (0.94 / 0.97) |
| Kerber Vorstadtnetz | GBM-graph **(best)** | 5.84e-05 | 0.00034 | 0.981 | 0.958 (0.97 / 0.95) |
| Kerber Vorstadtnetz | GBM-nolag | 6.3e-05 | 0.000367 | 0.978 | 0.955 (0.96 / 0.95) |

| Topology | Train / val / test days | Best model beats mean (MAE) | beats persistence (RMSE) | beats persistence (MAE) |
|---|---|---|---|---|
| mv_oberrhein | 1095 / 365 / 365 | True | True | True |
| CIGRE MV | 1095 / 365 / 365 | True | True | True |
| Kerber Dorfnetz | 1095 / 365 / 365 | True | True | True |
| Kerber Vorstadtnetz | 1095 / 365 / 365 | True | True | True |

### Product 2 — localization accuracy (300 trials per topology, random real 2019 operating states)

| Topology | Feature set / sensor coverage | Exact bus | ≤2 hops | ≤5 hops | True bus in top 3 |
|---|---|---|---|---|---|
| mv_oberrhein | voltage only (original method), all buses instrumented | 28.3% | 76.7% | 95.7% | 61.3% |
| mv_oberrhein | voltage + angle + line current, all instrumented | 93.7% | 96.0% | 97.3% | 96.0% |
| mv_oberrhein | voltage only, 30% of sensors | 9.7% | 57.7% | 83.7% | 39.7% |
| mv_oberrhein | voltage + angle + current, 30% of sensors | 39.7% | 86.0% | 97.0% | 78.7% |
| CIGRE MV | voltage only (original method), all buses instrumented | 65.0% | 94.7% | 100.0% | 92.7% |
| CIGRE MV | voltage + angle + line current, all instrumented | 99.3% | 100.0% | 100.0% | 100.0% |
| CIGRE MV | voltage only, 30% of sensors | 29.7% | 74.7% | 100.0% | 64.0% |
| CIGRE MV | voltage + angle + current, 30% of sensors | 59.0% | 91.7% | 100.0% | 88.7% |
| Kerber Dorfnetz | voltage only (original method), all buses instrumented | 24.0% | 62.3% | 89.3% | 49.3% |
| Kerber Dorfnetz | voltage + angle + line current, all instrumented | 96.3% | 99.3% | 100.0% | 99.0% |
| Kerber Dorfnetz | voltage only, 30% of sensors | 12.3% | 31.0% | 70.7% | 23.0% |
| Kerber Dorfnetz | voltage + angle + current, 30% of sensors | 36.0% | 76.0% | 96.3% | 66.3% |
| Kerber Vorstadtnetz | voltage only (original method), all buses instrumented | 6.0% | 26.7% | 68.3% | 22.0% |
| Kerber Vorstadtnetz | voltage + angle + line current, all instrumented | 92.3% | 99.3% | 99.7% | 98.7% |
| Kerber Vorstadtnetz | voltage only, 30% of sensors | 5.0% | 19.0% | 43.3% | 11.3% |
| Kerber Vorstadtnetz | voltage + angle + current, 30% of sensors | 35.0% | 65.7% | 88.7% | 55.7% |

### FISR — every feeder bus faulted once at the 2019 peak-load hour

| Topology | Faults | Localized exactly | Isolated ≤3 attempts | Lockout | Avoidable load restored (Vidyut) | (perfect localization) | Events needing ties → fully restored | Violations after − before (mean) |
|---|---|---|---|---|---|---|---|---|
| mv_oberrhein | 175 | 88.0% | 94.3% | 5.7% | 93.5% | 99.2% | 123 / 153 | 0 |
| CIGRE MV | 12 | 100.0% | 100.0% | 0.0% | 100.0% | 100.0% | 9 / 9 | 1.92 |
| Kerber Dorfnetz | 114 | 98.2% | 99.1% | 0.9% | 71.4% | 72.3% | 0 / 57 | 0 |
| Kerber Vorstadtnetz | 292 | 82.5% | 98.6% | 1.4% | 71.9% | 73.3% | 0 / 146 | 0 |