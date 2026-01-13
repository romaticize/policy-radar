# PolicyRadar Frontend V2.1 - Changelog

**Date:** January 13, 2026  
**Previous Version:** V2.0  
**New Version:** V2.1

---

## Summary of Changes

Major UX overhaul with nested domain/subsector filters replacing the confusing category system:
- **Nested domain filters** with dynamic sub-sector rows
- Critical summary widget for quick scanning
- Mobile export button and pull-to-refresh
- Removed useless "1 min read" display

---

## New Filter System

### Domain → Sub-sector Hierarchy

| Domain | Sub-sectors |
|--------|-------------|
| 💰 **Economy & Finance** | 🏦 Banking & RBI, 📈 Markets & SEBI, 💳 Fintech & Payments, 🧾 Tax & Budget |
| 💻 **Technology** | 📡 Telecom & TRAI, 🔒 Privacy & Data, 🤖 AI & Emerging Tech, 🛡️ Cybersecurity |
| ⚖️ **Legal & Regulatory** | ⚖️ Courts & Judiciary, 🏢 Competition & CCI, 📋 Tribunals, 🛒 Consumer Protection |
| 🏛️ **Governance** | 🏛️ Parliament & Bills, 📜 Executive & Policy, 🗳️ Elections, 👔 Public Admin |
| 🏥 **Social Sector** | 🏥 Healthcare, 📚 Education, 👷 Labour & Employment, 🌿 Environment |

### How It Works

1. Click a **Domain** pill → filters articles by domain keywords
2. **Sub-sector row appears** below with specific filters
3. Click a **Sub-sector** → narrows to that specific area
4. Click "All [Domain]" to show entire domain again

---

## Files Modified

### `index.html`

#### Removed:
- Old category bar (`.category-bar`, `.category-chip`)
- Flat sector pills
- `renderTopCategoryBar()` function
- `filterByCategory()` function
- Reading time display

#### Added:
- Domain filter row (`.domain-filter-row`, `.domain-pill`)
- Sub-sector filter row (`.subsector-filter-row`, `.subsector-pill`)
- `DOMAIN_CONFIG` object with all keywords
- `setDomainFilter()` function
- `setSubsectorFilter()` function
- Critical summary widget
- Mobile export button
- Pull-to-refresh

---

## URL Parameters

Filters are preserved in URL:
- `?domain=technology` - Domain filter
- `?domain=technology&subsector=telecom` - With sub-sector
- `?time=today&priority=critical&domain=legal` - Combined

---

## How to Deploy

```bash
cp index.html /path/to/policy-radar/index.html
git add index.html
git commit -m "Frontend V2.1: Nested domain filters, critical summary"
git push
```

---

*Generated: January 13, 2026*
