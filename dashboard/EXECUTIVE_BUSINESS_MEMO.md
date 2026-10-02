# Executive Quality & Reliability Engineering Memo
> *Disclaimer: Illustrative engineering memo prepared for case study demonstration, portfolio audit, and continuous quality improvement analysis.*

**To:** Plant General Manager & Quality Steering Committee  
**From:** Quality Control & Continuous Improvement Lead  
**Date:** Post-Evaluation Review  
**Subject:** Observed Defect Variation, Laney p'-Chart Implementation, and Density Capability Analysis in Perlite Insulation Manufacturing

---

### Executive Summary

Across **115 commercial production batches (27,817 inspection pieces)** recorded between January 14 and September 3, 2026 (note: February had no production logs, and 75 of 90 post-intervention batches clustered in April–May), process data was analyzed to evaluate defect shifts and operational capability.

Key Empirical Findings:
1. **Macro Plant Yield (Observational vs. Statistical):** Overall facility scrap dropped from **5.85% to 4.74%** (-18.9% relative change). However, due to significant batch-to-batch overdispersion (mean sigma_z ≈ 2.65), this overall macro shift is **not statistically significant** (Laney-adjusted Z = 1.24, p = 0.22, 95% CI [-0.64, +2.85] pp). Confounding effects from monthly SKU volume fluctuations (total volume 4.7x larger in a monitoring window twice as long; calendar throughput +133% from ~1,635 to ~3,818 pcs/month) cannot be ruled out.
2. **Flagship SKU 6" 90 Turnaround:** On our highest-volume product line (**6" 90**), reject rates decreased from **10.77% down to 5.15% (-52.2% scrap cut)**. This improvement is **robust and statistically significant** (Mann-Whitney p = 0.003; cluster bootstrap 95% CI [+2.95, +8.72] pp).
3. **SKU 8" 90 Inconclusive Shift:** 8" 90 showed an observed drop from **4.39% to 2.91%** (-33.7%), but this shift is **not statistically significant** when accounting for batch clustering (bootstrap 95% CI [-0.24, +3.05] pp, spanning zero).
4. **Normalized Financial Benchmark:** Cost of Poor Quality (COPQ) modeled at an assumed benchmark of Rp 45,000/pc declined from **Rp 2,632 to Rp 2,135 per manufactured piece** (-18.9%, mathematically identical to the pooled reject reduction due to flat cost assumptions).

---

### The "So What?": 3 Strategic Engineering Recommendations

#### 1. Investigate Low-Volume & Specialized Setup Friction (Candidate Special Causes)
* **Finding:** Standard high-volume lines exhibited steady quality, but two distinct batches breached the Laney Upper Control Limit (UCL p'): **3" 65 on April 1 (20.7% reject, n=184)** and **6" 30 on June 24 (33.3% reject, n=48)**.
* **Working Hypothesis:** In-plant notes associate these excursions with dimensional wall-thickness deviations and small-batch setup friction rather than uniform slurry issues. These remain operational hypotheses that require on-machine validation.
* **Action:** Establish a standardized pre-run tooling inspection and verification checklist for short production runs (n < 50) and non-standard mold profiles.

#### 2. Re-evaluate Bulk Density Operational Window vs. Boundary Truncation
* **Finding:** Bulk density measurements (n = 4,514) show an empirical distribution centered near 242 kg/m³ with natural spread (6-sigma ≈ 79 kg/m³) exceeding the specification interval (LSL = 220, USL = 270 kg/m³), yielding Cpk ≈ 0.55–0.56. Furthermore, diagnostics reveal measurement truncation concentrated at exactly 270.0 kg/m³ (34 readings at upper limit vs. 5 at 200.0 kg/m³).
* **Trade-off Analysis:** While friability rejects dropped from 3.95 to 2.30 pcs/100 (-42%), thermal curing cracks rose from 0.61 to 1.07 pcs/100 (+75%) and dimensional defects appeared (+0.34 pcs/100), eroding ~0.8 pp of the 1.65 pp friability gains.
* **Action:** Audit digital scale calibration and eliminate manual boundary truncation in recording. Target slurry formulation to 245–265 kg/m³ once measurement integrity is confirmed.

#### 3. Institutionalize Shop-Floor Laney p'-Charts to Eliminate Alarm Fatigue
* **Finding:** Standard binomial p-charts generated **16 control limit breaches across both periods (3 baseline, 13 post-intervention)**. Fourteen of these 16 breaches did not exceed Laney limits, driven purely by subgroup size variation (n up to 370 pieces).
* **Improvement:** The Laney p'-chart filtered operational noise down to **2 genuine out-of-control batches**, while the 8-point run rule produced zero false triggers across both phases (low power on this series).
* **Action:** Embed Laney calculations into shop-floor reporting terminals so supervisors focus solely on true special-cause excursions.

---

### Methodological Notes & Limitations
* **Quasi-Experimental Design:** Observational pre/post framework without a concurrent control group.
* **Uneven Temporal Distribution:** February is unrepresented; production concentrated heavily in April (47 batches) and May (28 batches), tapering sharply to 15 batches across June–September.
* **Cost Accounting Basis:** Financial figures utilize a standardized scrap valuation assumption of Rp 45,000 per rejected piece and do not represent internal accounting ledgers.
