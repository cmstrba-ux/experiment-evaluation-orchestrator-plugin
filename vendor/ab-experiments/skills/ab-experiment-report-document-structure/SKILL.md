---
name: ab-experiment-report-document-structure
description: >
  Generate A/B/C experiment evaluation reports as Word documents (.docx) following
  the exact Groupon MBNXT experiment report structure. Use whenever a user asks to
  produce, generate, or create an experiment report, evaluation report, or A/B test
  report. Always reads this SKILL.md first before writing any code.
---

# A/B Experiment Evaluation Report Skill

Generates polished Word document experiment reports that exactly match the established
Groupon MBNXT report structure. Always reads the docx SKILL.md first for implementation
patterns, then follows this document's specifications.

**First action**: Read `/mnt/skills/public/docx/SKILL.md` before writing any code.

---

## Critical Rules

- **NEVER break a table across pages.** Every `TableRow` MUST include `cantSplit: true`.
  This is non-negotiable. Tables that split between pages corrupt the report layout.
- Always use US Letter page size (12240 × 15840 DXA), 1-inch margins on all sides.
- Use Arial font throughout. Default body size: 20 (10pt). Section headings: 28 (14pt).
- Use `ShadingType.CLEAR` (never SOLID) for all cell fills.
- All table widths must use `WidthType.DXA`. Column widths must sum exactly to table width (9360 DXA).
- After generating, validate with `python scripts/office/validate.py`.

---

## Document Structure

The report has a fixed section order. Every section must appear, in this exact sequence:

1. **Title Block** (centered header with experiment name and period)
2. **Experiment Context** (GrowthBook URL, Description, Hypothesis)
3. **Executive Summary Table** (colored verdict cards per variant)
4. **Metric Definitions Table**
5. **Step 1** — Traffic Split (SRM Check)
6. **Step 2** — Overall Results
7. **Step 3** — Platform Results (Touch + Web sub-tables)
8. **Step 4** — Day-Level Stability Analysis
9. **Step 5** — Statistical Significance Testing
10. **Step 6** — Power Analysis & Minimum Detectable Effect
11. **Step 7** — Practical Significance (7a, 7b, 7c, 7d sub-sections)
12. **Step 8** — Behavioral Mechanism & Context
13. **Step 9** — Business Impact Estimate
14. **Final Recommendation Table**
15. **Treatment Decision Framing Table** (for each DIRECTIONAL/HOLD variant)
16. **Notes & Data Quality**

---

## Color Palette

| Element | Color (hex) |
|---------|-------------|
| Main title text | `1F3864` (dark navy) |
| Experiment name subtitle | `2E75B6` (blue) |
| Meta line (date, visitors) | `444444` (dark gray) |
| Section headings (Step N — ...) | `1F3864` |
| Heading underline border | `2E75B6` |
| Table header background | `1F3864` |
| Table header text | `FFFFFF` |
| Table row alternating (even) | `D9E1F2` (light blue-gray) |
| Table row alternating (odd) | `FFFFFF` |
| KILL verdict cell background | `FFC7CE` (light red) |
| HOLD/DIRECTIONAL cell background | `FFEB9C` (light yellow) |
| SHIP verdict cell background | `C6EFCE` (light green) |
| BASELINE cell background | `FFFFFF` (white) |
| KILL verdict text | `C00000` (dark red) |
| BASELINE verdict text | `444444` (dark gray) |
| DIRECTIONAL/HOLD verdict text | `7F6000` (dark amber) |
| SHIP verdict text | `375623` (dark green) |
| Body text | `000000` |
| Muted/secondary text | `555555` |
| Table border color | `AAAAAA` |
| Delta rows (vs. Control) | `F2F2F2` (light gray background) |

---

## Typography Scale

| Element | Size (half-pts) | Points | Bold |
|---------|----------------|--------|------|
| Main report title | 40 | 20pt | Yes |
| Experiment name subtitle | 26 | 13pt | No |
| Meta line (dates/visitors) | 20 | 10pt | No |
| Executive summary variant name | 24 | 12pt | Yes |
| Executive summary KILL/SHIP label | 40 | 20pt | Yes |
| Executive summary DIRECTIONAL label | 30 | 15pt | Yes |
| Executive summary BASELINE label | 36 | 18pt | Yes |
| Executive summary subtext | 18 | 9pt | No |
| Section headings (Step N — Title) | 28 | 14pt | Yes |
| Table header text | 20 | 10pt | Yes |
| Table body text | 20 | 10pt | No |
| Notes section body | 18 | 9pt | No |

---

## Page Setup

```javascript
sections: [{
  properties: {
    page: {
      size: { width: 12240, height: 15840 },  // US Letter
      margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 }
    }
  },
  children: [/* all content */]
}]
```

---

## Section Heading Style

Each numbered step uses this heading pattern:

```javascript
new Paragraph({
  spacing: { before: 320, after: 160 },
  border: {
    bottom: { style: BorderStyle.SINGLE, size: 6, color: "2E75B6", space: 1 }
  },
  children: [
    new TextRun({
      text: "Step N — Section Title",
      bold: true,
      size: 28,
      color: "1F3864",
      font: "Arial"
    })
  ]
})
```

---

## Table Structure Template

Every table follows this pattern. **`cantSplit: true` on every row is mandatory.**

```javascript
new Table({
  width: { size: 9360, type: WidthType.DXA },
  columnWidths: [/* must sum to 9360 */],
  rows: [
    // HEADER ROW
    new TableRow({
      cantSplit: true,        // ← REQUIRED on every row
      tableHeader: true,
      children: columnHeaders.map(text =>
        new TableCell({
          width: { size: colWidth, type: WidthType.DXA },
          shading: { fill: "1F3864", type: ShadingType.CLEAR },
          margins: { top: 80, bottom: 80, left: 120, right: 120 },
          borders: tableBorders,
          children: [new Paragraph({
            alignment: AlignmentType.CENTER,
            children: [new TextRun({ text, bold: true, size: 20, color: "FFFFFF", font: "Arial" })]
          })]
        })
      )
    }),
    // DATA ROWS (alternate fills: odd=FFFFFF, even=D9E1F2)
    ...dataRows.map((row, i) =>
      new TableRow({
        cantSplit: true,        // ← REQUIRED on every row
        children: row.map((cell, colIdx) =>
          new TableCell({
            width: { size: colWidths[colIdx], type: WidthType.DXA },
            shading: { fill: i % 2 === 0 ? "FFFFFF" : "D9E1F2", type: ShadingType.CLEAR },
            margins: { top: 80, bottom: 80, left: 120, right: 120 },
            borders: tableBorders,
            children: [new Paragraph({
              children: [new TextRun({ text: cell, size: 20, font: "Arial" })]
            })]
          })
        )
      })
    )
  ]
})
```

**Standard border definition** (use for all tables):
```javascript
const border = { style: BorderStyle.SINGLE, size: 1, color: "AAAAAA" };
const tableBorders = { top: border, bottom: border, left: border, right: border, insideH: border, insideV: border };
```

---

## Section-by-Section Specifications

### Title Block

Three centered paragraphs, no table:

```javascript
// Line 1: Report title
new Paragraph({
  spacing: { before: 0, after: 200 },
  alignment: AlignmentType.CENTER,
  children: [new TextRun({ text: "A/B/C Experiment Evaluation Report", bold: true, size: 40, color: "1F3864", font: "Arial" })]
})
// Line 2: Experiment ID
new Paragraph({
  spacing: { after: 100 },
  alignment: AlignmentType.CENTER,
  children: [new TextRun({ text: experimentId, size: 26, color: "2E75B6", font: "Arial" })]
})
// Line 3: Test period meta
new Paragraph({
  spacing: { after: 300 },
  alignment: AlignmentType.CENTER,
  children: [new TextRun({ text: `Test Period: ${dateRange}  |  ${days} Days  |  ${visitors} Total Visitors`, size: 20, color: "444444", font: "Arial" })]
})
```

### Experiment Context

A 3-row, 2-column table placed immediately after the Title Block. Displays the GrowthBook URL, description, and hypothesis pulled from GrowthBook during the evaluation.

2 columns: Label | Value
Column widths: 2340 | 7020 (sum = 9360)

The GrowthBook URL should be rendered as a clickable hyperlink using `ExternalHyperlink`.

If any field is empty in GrowthBook, display "Not provided in GrowthBook" in muted gray (`555555`).

```javascript
// Experiment Context heading
sectionHeading("Experiment Context"),

new Table({
  width: { size: 9360, type: WidthType.DXA },
  columnWidths: [2340, 7020],
  rows: [
    // Header row
    new TableRow({
      cantSplit: true,
      tableHeader: true,
      children: ["Field", "Details"].map(text =>
        new TableCell({
          width: { size: text === "Field" ? 2340 : 7020, type: WidthType.DXA },
          shading: { fill: "1F3864", type: ShadingType.CLEAR },
          margins: { top: 80, bottom: 80, left: 120, right: 120 },
          borders: tableBorders,
          children: [new Paragraph({
            alignment: AlignmentType.CENTER,
            children: [new TextRun({ text, bold: true, size: 20, color: "FFFFFF", font: "Arial" })]
          })]
        })
      )
    }),
    // Row 1: GrowthBook URL
    new TableRow({
      cantSplit: true,
      children: [
        labelCell("GrowthBook URL", 2340),
        new TableCell({
          width: { size: 7020, type: WidthType.DXA },
          shading: { fill: "FFFFFF", type: ShadingType.CLEAR },
          margins: { top: 80, bottom: 80, left: 120, right: 120 },
          borders: tableBorders,
          children: [new Paragraph({
            children: [new ExternalHyperlink({
              link: growthbookUrl,
              children: [new TextRun({ text: growthbookUrl, size: 20, font: "Arial", color: "2E75B6", underline: {} })]
            })]
          })]
        })
      ]
    }),
    // Row 2: Description
    dataRow(["Description", description || "Not provided in GrowthBook"], [2340, 7020], 1),
    // Row 3: Hypothesis
    dataRow(["Hypothesis", hypothesis || "Not provided in GrowthBook"], [2340, 7020], 2),
  ]
})
```

### Executive Summary Table

One row, one column per variant (3 for A/B/C, 2 for A/B). Column order: Treatment A | Control | Treatment B (for A/B/C).

Cell backgrounds:
- KILL variant → `FFC7CE`
- SHIP variant → `C6EFCE`
- DIRECTIONAL/HOLD variant → `FFEB9C`
- BASELINE (Control) → `FFFFFF`

Each cell contains 3 paragraphs (all centered):
1. Variant name — bold, 24 half-pts
2. Verdict label (❌ KILL / ✅ SHIP / ⚠️ DIRECTIONAL SIGNAL / BASELINE) — bold, colored, large
3. One-line summary — muted gray, 18 half-pts

All rows use `cantSplit: true`.

### Metric Definitions Table

3 columns: Metric (Full Name) | Formula | Description
Column widths: 2800 | 3000 | 3560 (sum = 9360)

Standard header (dark navy background, white text) + alternating rows.

### Step 1 — Traffic Split

4 columns: Variant | Visitors | Share | Expected
Column widths: 2340 | 2340 | 2340 | 2340 (sum = 9360)

Last row is a **Total** bold summary row (fill: `D9E1F2`, bold text).

Below the table: one paragraph with ✓ or ✗ SRM check result text.

### Step 2 — Overall Results

6 columns: Variant | Conversion Rate | Margin per Visitor | Revenue per Visitor | Margin per Order | Visitors
Column widths: 1440 | 1560 | 1560 | 1560 | 1560 | 1680 (sum = 9360)

Row order: Control → Treatment A row → **vs. Control delta row** → Treatment B row → **vs. Control delta row**

Delta rows have background `F2F2F2` and bold text. First cell reads "vs. Control".

### Step 3 — Platform Results

Two separate sub-tables: one for Touch, one for Web.

Each has a sub-heading paragraph (bold, 22 half-pts, color `1F3864`) before it.

4 columns: Variant | Conversion Rate | Margin per Visitor | Revenue per Visitor | Visitors
Column widths: 1872 | 1872 | 1872 | 1872 | 1872 (sum = 9360)

Same delta row pattern as Step 2.

### Step 4 — Day-Level Stability

4 columns: Variant vs. Control | Days Beating Control | Share of Days | Avg Daily Delta (Margin per Visitor)
Column widths: 2340 | 2340 | 2340 | 2340 (sum = 9360)

### Step 5 — Statistical Significance

7 columns: Comparison | Mean Daily Delta | Std Dev | Std Error | t-stat | p-value | 95% Confidence Interval
Column widths: 1440 | 1440 | 1200 | 1200 | 1200 | 1200 | 1680 (sum = 9360)

Below the table: narrative paragraph explaining significance findings and CI interpretation.

### Step 6 — Power Analysis

6 columns: Variant | MDE @80% Power | MDE (% of Ctrl MPV) | Days Needed (80%) | Days Needed (90%) | Current Days
Column widths: 1560 | 1560 | 1560 | 1560 | 1560 | 1560 (sum = 9360)

Below the table: one paragraph per treatment explaining extension viability.

### Step 7 — Practical Significance

Four sub-sections, each with a bold sub-heading (22 half-pts, color `1F3864`):

**7a — Effect Size (Cohen's d)**
4 columns: Variant | Cohen's d | Classification | What This Means
Column widths: 1440 | 1440 | 2040 | 4440 (sum = 9360)

Classification thresholds:
- |d| < 0.2 → "Trivial (< 0.2)"
- 0.2 ≤ |d| < 0.5 → "Small (0.2 – 0.5)"
- 0.5 ≤ |d| < 0.8 → "Medium (0.5 – 0.8)"
- |d| ≥ 0.8 → "Large (≥ 0.8)"

**7b — Relative Effect vs. Business Relevance Threshold**
3 columns: Variant | Relative MPV Uplift | Assessment
Column widths: 1560 | 2400 | 5400 (sum = 9360)

**7c — Cost-of-Change Assessment**
3 columns: Factor | Assessment | Notes
Column widths: 1560 | 2040 | 5760 (sum = 9360)
Standard rows: Change type | Risk profile | Implementation cost

**7d — Practical Significance Verdict**
One paragraph "Verdict: [Marginally Practical / Practical / Not Practical / etc.]" bold.
Then "What the data shows:" bullet list.
Then "What remains uncertain:" bullet list.
Then "What it would cost to act vs. not act:" narrative.
Then "What factors should drive the team's decision:" bullet list.

### Step 8 — Behavioral Mechanism & Context

Narrative-only paragraphs (no tables). Includes:
- One paragraph explaining what the experiment tests and its hypothesis.
- Sub-heading "Observed vs. predicted:" followed by one paragraph per treatment.
- One paragraph on mechanism context.

### Step 9 — Business Impact Estimate

Intro paragraph: "The following estimates apply to [variant]. All figures are directional..."

3 columns: Projection | Estimated Range | Basis
Column widths: 3120 | 3120 | 3120 (sum = 9360)

Row 1: Observed-period equivalent
Row 2: Monthly range
Row 3: Annual range

Below the table: disclaimer paragraph about directional-only nature.

### Final Recommendation Table

3 columns: Variant | Status | Summary
Column widths: 1560 | 2040 | 5760 (sum = 9360)

One row per non-Control variant. Status cell shows emoji + verdict text. Status cell background matches verdict color:
- KILL → `FFC7CE`
- SHIP → `C6EFCE`
- DIRECTIONAL/HOLD → `FFEB9C`

### Treatment Decision Framing Table (for DIRECTIONAL/HOLD variants only)

Two-column table. First row is a split header:
- Left cell: "If the team acts on the directional signal" (fill `C6EFCE`, green)
- Right cell: "If the team does not act" (fill `FFC7CE`, red/pink)

Column widths: 4680 | 4680

Content rows contain bullet-point reasoning for each path. All rows `cantSplit: true`.

Below: "Key considerations for the team's decision:" followed by bullet list.

### Notes & Data Quality

Bold sub-heading "Notes & Data Quality" at 22 half-pts.

Bullet list with:
- Source table name
- Data quality filter
- Orders field used
- Statistical method
- Practical significance method
- Any data gaps (missing days, etc.)
- Report generation date

---

## Implementation Checklist

Before writing a single line of code, confirm:
- [ ] Read `/mnt/skills/public/docx/SKILL.md` (docx-js patterns, table rules)
- [ ] Gathered all experiment data (variant names, metrics, stats results)
- [ ] Determined experiment type (A/B or A/B/C)
- [ ] Know which variants are KILL / SHIP / DIRECTIONAL / HOLD

During code generation:
- [ ] Every `TableRow` includes `cantSplit: true`
- [ ] All table column widths sum to 9360 DXA
- [ ] All table cells have `width` AND table has `columnWidths`
- [ ] All cells use `ShadingType.CLEAR`
- [ ] All cells have margins `{ top: 80, bottom: 80, left: 120, right: 120 }`
- [ ] Page size explicitly set to 12240 × 15840
- [ ] Font is Arial throughout
- [ ] Validate with `python scripts/office/validate.py` after generation

---

## Variant Verdict Determination

Use this logic to assign verdicts (feed into Executive Summary and Final Recommendation):

```
if p < 0.05 AND mean_delta > 0:
  verdict = "SHIP"
elif p < 0.05 AND mean_delta < 0:
  verdict = "KILL"
elif mean_delta < 0 AND cohens_d < -0.1:
  verdict = "KILL"        # Consistent negative signal even without significance
elif mean_delta < 0:
  verdict = "KILL"        # Negative direction
elif cohens_d >= 0.2 AND relative_uplift >= 0.5%:
  verdict = "DIRECTIONAL SIGNAL"   # Positive but not confirmed
else:
  verdict = "HOLD"        # Insufficient signal
```

The control variant always gets "BASELINE".

---

## Bullet Lists in Narrative Sections

Use `LevelFormat.BULLET` with numbering config (never unicode bullets):

```javascript
const doc = new Document({
  numbering: {
    config: [{
      reference: "bullets",
      levels: [{
        level: 0, format: LevelFormat.BULLET, text: "•",
        alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 360, hanging: 180 } } }
      }]
    }]
  },
  ...
})
// Usage:
new Paragraph({
  numbering: { reference: "bullets", level: 0 },
  children: [new TextRun({ text: "Bullet content", size: 20, font: "Arial" })]
})
```

---

## Example: Minimal Working Script Skeleton

```javascript
const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
        BorderStyle, WidthType, ShadingType, AlignmentType, LevelFormat } = require('docx');
const fs = require('fs');

const border = { style: BorderStyle.SINGLE, size: 1, color: "AAAAAA" };
const tableBorders = { top: border, bottom: border, left: border, right: border };

function headerRow(columns, widths) {
  return new TableRow({
    cantSplit: true,
    tableHeader: true,
    children: columns.map((text, i) => new TableCell({
      width: { size: widths[i], type: WidthType.DXA },
      shading: { fill: "1F3864", type: ShadingType.CLEAR },
      margins: { top: 80, bottom: 80, left: 120, right: 120 },
      borders: tableBorders,
      children: [new Paragraph({
        alignment: AlignmentType.CENTER,
        children: [new TextRun({ text, bold: true, size: 20, color: "FFFFFF", font: "Arial" })]
      })]
    }))
  });
}

function dataRow(cells, widths, rowIndex) {
  const fill = rowIndex % 2 === 0 ? "FFFFFF" : "D9E1F2";
  return new TableRow({
    cantSplit: true,
    children: cells.map((text, i) => new TableCell({
      width: { size: widths[i], type: WidthType.DXA },
      shading: { fill, type: ShadingType.CLEAR },
      margins: { top: 80, bottom: 80, left: 120, right: 120 },
      borders: tableBorders,
      children: [new Paragraph({
        children: [new TextRun({ text, size: 20, font: "Arial" })]
      })]
    }))
  });
}

function sectionHeading(title) {
  return new Paragraph({
    spacing: { before: 320, after: 160 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: "2E75B6", space: 1 } },
    children: [new TextRun({ text: title, bold: true, size: 28, color: "1F3864", font: "Arial" })]
  });
}

const doc = new Document({
  numbering: {
    config: [{ reference: "bullets", levels: [{
      level: 0, format: LevelFormat.BULLET, text: "•",
      alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 360, hanging: 180 } } }
    }]}]
  },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 },
        margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 }
      }
    },
    children: [
      // Title block
      // Executive Summary table
      // Metric Definitions table
      // Steps 1–9
      // Final Recommendation
      // Notes
    ]
  }]
});

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync('experiment_report.docx', buf);
  console.log('Done');
});
```

---

## Evals

See `evals/evals.json` for test cases.
