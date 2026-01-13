# PolicyRadar Frontend V2.1 - P2 Fixes Changelog

**Date:** January 13, 2026  
**Previous Version:** V2.0  
**New Version:** V2.1

---

## Summary of Changes

This update adds P2 improvements from the professional audit:
- Critical summary widget for quick scanning
- PDF export accessible on mobile nav
- Pull-to-refresh for mobile users
- **NEW: Sector filter pills** for quick domain filtering
- Removed useless "1 min read" display

---

## Files Modified

### 1. `index.html`

#### CSS Changes:
- **Added** Critical Summary Widget styles
- **Added** Pull-to-Refresh indicator styles
- **Added** Sector filter pill styles (`.sector-pill`, `.sector-pills`, etc.)
- **Removed** `.article-read-time` CSS

#### HTML Changes:
- **Added** Critical Summary Widget in sidebar
- **Added** Export button to mobile navigation (now 5 items)
- **Added** Sector filter pills: Telecom, Fintech, Privacy, Competition, AI/Tech
- **Removed** Reading time display from article cards

#### JavaScript Changes:
- **Added** `SECTOR_KEYWORDS` mapping for each sector
- **Added** `toggleSectorFilter()` - Toggle sector filter on/off
- **Added** Sector filtering in `applyFiltersAndRender()`
- **Added** `updateCriticalSummary()` - Critical summary widget
- **Added** `filterByCritical()` - Quick filter
- **Added** `initPullToRefresh()` - Mobile pull-to-refresh
- **Removed** `estimateReadTime()` function

---

## Features Added

### 1. Sector Filter Pills (NEW)
Quick-access filters for key policy domains:

| Sector | Keywords Matched |
|--------|------------------|
| 📡 Telecom | trai, dot, spectrum, 5g, broadband, telecom, bsnl, jio, airtel |
| 💳 Fintech | rbi, sebi, upi, digital lending, nbfc, fintech, payment, banking |
| 🔒 Privacy | dpdp, data protection, privacy, meity, personal data, consent |
| ⚖️ Competition | cci, antitrust, merger, cartel, competition commission, monopoly |
| 🤖 AI/Tech | artificial intelligence, semiconductor, deepfake, machine learning, ai regulation |

**Behavior:** Click to filter, click again to deselect (toggle)

### 2. Critical Summary Widget
- Shows count of critical articles from today
- "View All" button filters to critical + today

### 3. Mobile PDF Export
- Export button now in bottom navigation

### 4. Pull-to-Refresh (Mobile)
- Pull down from top of feed to refresh

---

## Removed

### Reading Time Display
- **Why:** Always showed "1 min" (only counted summary words)
- **Impact:** Cleaner article cards

---

## How to Deploy

```bash
cp index.html /path/to/policy-radar/index.html
git add index.html
git commit -m "Frontend V2.1: Sector filters, critical summary, mobile export"
git push
```

---

*Generated: January 13, 2026*
