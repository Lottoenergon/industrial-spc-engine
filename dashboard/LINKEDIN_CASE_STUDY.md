# LinkedIn Case Study Post: Defect Reduction & Statistical Process Control (SPC)

**Headline:** Why Standard p-Charts Failed Our Shop Floor (And How Laney p'-Charts & Root-Cause Analytics Cut Flagship Scrap by 52.2%)

---

### The Reality of Industrial Process Variation
In molded perlite thermal insulation manufacturing, process engineers face a delicate physical trade-off:
1. **Under-density (<220 kg/m³):** The product becomes brittle, corners chip, and structural friability spikes (accounting for 67.6% of baseline scrap notes).
2. **Over-density (>270 kg/m³):** Compacting to avoid friability increases material consumption and triggers overweight rejections (21.95% of baseline notes).

Together, these two failure modes accounted for **89.55% of all baseline reject notes**.

---

### Why Standard SPC Failed (The Overdispersion Problem)
Standard binomial p-charts assume constant binomial variance. When monitoring production batches with varying subgroup sizes (n up to 370 pieces), standard control limits become artificially narrow—triggering **16 standard limit breaches (14 of which were standard-only false alarms that did not breach Laney limits)**.

By implementing the **Laney p'-Chart** adjustment:
* We calculated a process overdispersion factor (baseline sigma_z = 2.57, post sigma_z = 2.66; order-sensitivity range 2.1–2.7).
* Absorbed natural batch-to-batch operational noise.
* Successfully filtered false alarms down to **2 candidate special-cause signals**: Batch 3" 65 (20.7% reject) and Batch 6" 30 (33.3% reject).
* Hypothesis: Rather than general slurry degradation, these spikes aligned with short-run setup friction and dimensional variance requiring standardized mold verification.

---

### The Data Analyst Takeaway: Statistical Rigor Over Vanity Metrics
Analyzing 115 commercial batches across Jan–Sep 2026 revealed critical insights about real-world manufacturing data:
* **Flagship Line (6" 90):** Reject rate dropped from **10.77% to 5.15% (-52.2% scrap cut)**. This improvement is **statistically significant** (Mann-Whitney p = 0.003; cluster bootstrap 95% CI [+2.95, +8.72] pp).
* **Facility-Wide Yield:** Overall scrap dropped nominally from **5.85% to 4.74% (-18.9%)**. But here is the honest data analyst lesson: once adjusted for overdispersion and batch clustering, the facility-wide drop is **not statistically significant** (p = 0.22). Confounding from a 4.7x volume expansion in Period 2 (calendar monthly throughput grew ~+133%) and SKU mix shifts cannot be ignored!
* **8" 90 Product Line:** Dropped from **4.39% to 2.91%**, but the confidence interval [-0.24, +3.05] pp includes zero—highlighting that not every positive trend is proven.
* **Process Trade-offs:** Tracking defects per 100 pcs produced revealed that friability dropped (-1.65 pp), but thermal cracks (+0.46 pp) and dimensional defects (+0.34 pp) rose, eroding ~0.8 pp of the gains.
* **Measurement Health:** Density histogram diagnostics revealed artificial capping concentrated at 270 kg/m³ (34 readings exactly at the limit), pinpointing that measurement practices must be audited before trusting process capability (Cpk ≈ 0.55–0.56).

---

### 3 Lessons for Data Analysts in Industrial Operations
1. **Always check for overdispersion:** If sample sizes vary, standard p-charts cause alarm fatigue. Use Laney p'-charts.
2. **Question headline numbers:** A pooled percentage drop can hide SKU mix confounding and calendar clustering (e.g. 75 of 90 batches sitting in April–May).
3. **Be transparent about limitations:** Differentiating robust SKU findings from inconclusive plant-wide shifts is what separates real data analysts from dashboard decorators.

Explore the fully reproducible Python pipeline, SQLite views, and automated charts on GitHub:
https://github.com/Lottoenergon/industrial-spc-engine

#DataAnalytics #StatisticalProcessControl #QualityControl #IndustrialAnalytics #Python #SQL #SixSigma #Manufacturing
