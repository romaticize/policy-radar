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
- Removed useless "1 min read" display

---

## Files Modified

### 1. `index.html`

#### CSS Changes:
- **Added** Critical Summary Widget styles (`.critical-summary`, etc.)
- **Added** Pull-to-Refresh indicator styles (`.pull-indicator`)
- **Removed** `.article-read-time` CSS (was showing "1 min" for everything)

#### HTML Changes:
- **Added** Critical Summary Widget in sidebar
- **Added** Export button to mobile navigation (now 5 items)
- **Removed** Reading time display from article cards

#### JavaScript Changes:
- **Added** `updateCriticalSummary()` - Populates critical summary widget
- **Added** `filterByCritical()` - Quick filter to critical + today
- **Added** `initPullToRefresh()` - Mobile pull-to-refresh
- **Removed** `estimateReadTime()` function (was broken - only counted summary words)

---

## Features Added

### 1. Critical Summary Widget
- Shows count of critical articles from today
- Displays preview of first critical item
- "View All" button filters to critical + today

### 2. Mobile PDF Export
- Export button now in bottom navigation
- Accessible without keyboard shortcuts

### 3. Pull-to-Refresh (Mobile)
- Pull down from top of feed to refresh
- Visual indicator shows pull progress

---

## Removed

### Reading Time Display
- **Why:** Always showed "1 min" because it estimated from summary text only
- **Impact:** Cleaner article cards, less visual noise

---

## How to Deploy

```bash
cp index.html /path/to/policy-radar/index.html
git add index.html
git commit -m "Frontend V2.1: Critical summary, mobile export, remove reading time"
git push
```

---

*Generated: January 13, 2026*
