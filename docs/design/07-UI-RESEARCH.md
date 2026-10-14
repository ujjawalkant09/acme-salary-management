# 07 · UI research and the v3 layout

Why the UI changed after the second prototype, and what research it is based on.

## Feedback on prototype v2
- Filters along the top felt crowded; they should be in a **left panel**.
- The pages showed too much at once, and the Insights page was overwhelming.
- There was no sign of **who is logged in**, and no way to sign out.

## What we looked at
| Source | Takeaway for us |
|--------|-----------------|
| [Dashboard filter design guide (Aufait UX)](https://www.aufaitux.com/blog/dashboard-filter-design-guide/) | Use a **side panel when there are 8 or more filter dimensions** and a top bar below that. Show active filters as removable chips with "Clear all". Filter live only if the backend answers in under ~300 ms; otherwise use an Apply button. On mobile, use a drawer and a "Filters (3)" button |
| [Improving filtering for enterprise solutions (UX Collective)](https://uxdesign.cc/3-ways-to-improve-filtering-for-enterprise-solutions-ux-286b5a39b34d) | Left panels are easy to overlook, so selections must be obvious, with immediate confirmation. **Show counts** per option so users see which filter limits results. Offer presets and remember the last filters |
| [Best filter UI for large-scale data (UX Movement)](https://uxmovement.substack.com/p/best-filter-ui-design-for-large-scale) | A left sidebar fits many filters without hiding options; the risk is that it reads as unrelated to the content. Keep it visually attached to the table |
| [Dashboard design principles (DesignRush)](https://www.designrush.com/agency/ui-ux-design/trends/dashboard-design-principles) | Lead with a few actionable metrics; move detail lower or behind a click (**progressive disclosure**); every widget must earn its place |
| [Sidebar navigation case study (UX Planet)](https://uxplanet.org/case-study-research-sidebar-navigation-b41272026c6d) | **Logo at the top of the sidebar, user's avatar, name and email in the sidebar** with access to account actions; keep admin/settings items separate from the main pages; the sidebar can collapse |
| [SaaS navigation menu design (Lollypop)](https://lollypop.design/blog/2025/december/saas-navigation-menu-design/) | Keep top-level items to the essentials, use clear labels, show a clear active state, and hide what the user can't access |
| [HR dashboard template guide (TheFrontKit)](https://thefrontkit.com/blogs/nextjs-hr-dashboard-template-guide-2026) | Common HR screens: dashboard with headcount and an activity feed, directory with search, filters and a sortable table, filter state in the URL, profile with tabs |
| [HiBob compensation](https://www.hibob.com/product-briefs/compensation-management/), [Pave compensation bands](https://www.pave.com/compensation-bands), [Ravio's comparison of compensation tools](https://ravio.com/blog/best-compensation-management-software) | Comp tools centre on **range positioning** (where a person sits in their pay range), comp ratio and an org-wide overview; complex navigation is a common complaint about older tools (Workday, Payscale), so simple navigation is a real advantage |

## The v3 layout
```
┌──────────────┬──────────────────────────────────────────────────────┐
│ ACME Pay     │  Page title                      [Search ⌘K] [+ Add] │
│              ├──────────────────────────────────────────────────────┤
│ Home         │                                                      │
│ People       │                    page content                      │
│ Insights     │                                                      │
│ Imports      │                                                      │
│              │                                                      │
│ Settings     │                                                      │
│ ──────────── │                                                      │
│ (PS) Priya   │                                                      │
│ HR Manager ▾ │                                                      │
└──────────────┴──────────────────────────────────────────────────────┘
```
- **Sidebar:** logo, four main pages, Settings kept separate, and the **signed-in user** at the bottom (avatar, name, role). Clicking the user opens a menu with the email, "Account settings" and "Sign out".
- **Sign-in page** (the demo login), so the flow starts like the real app.

### Home: calm, only what needs action
1. A greeting with today's date.
2. **Three numbers:** current employees, yearly salary cost, median salary.
3. **Needs your attention:** short, clickable to-dos, for example "12 people paid outside the usual range", "3 salary changes start next week", "1 import waiting for review".
4. **Recent changes:** the last few salary changes, each linking to the person.

No charts on Home; they live in Insights.

### People: filters in a left panel
```
┌─────────────────┬────────────────────────────────────────────────────┐
│ Filters  Clear  │ [Search name, email or code]          [Export CSV] │
│                 │ India ✕  Engineering ✕            1,142 people     │
│ Status          │ ┌────────────────────────────────────────────────┐ │
│ (•) Current     │ │ Employee        Role         Location   Salary │ │
│ ( ) Left        │ │ …                                              │ │
│                 │ └────────────────────────────────────────────────┘ │
│ Country         │ 1–20 of 1,142                  ‹ Page 1 of 58 ›    │
│ [x] India   348 │                                                    │
│ [ ] US      260 │                                                    │
│ …               │                                                    │
│ Department      │                                                    │
│ Level  1 2 3 4… │                                                    │
│ Type            │                                                    │
│ Salary (USD)    │                                                    │
│ [min] – [max]   │                                                    │
└─────────────────┴────────────────────────────────────────────────────┘
```
- Every option shows **how many people** it would match.
- Filters apply instantly (our list API targets < 200 ms), and active filters are repeated as **chips above the table**, so they're never missed.
- The panel can be hidden for a wider table. On a phone it becomes a "Filters (2)" button that opens a drawer.

### Insights: one question per tab
Instead of one long page: **Overview** (pay by country/department), **By role** (one country at a time) and **Unusual salaries**. Each tab answers one question and fits on one screen.

### Employee details
Changed after the decision book (Q39): the employee has their own page (/people/<id>) with salary, pay-range position, history, documents and details; Back returns to the filtered list.
