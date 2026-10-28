# VerifiaAI Frontend Design System

**Status:** Phase 18 operations UI, updated for Phase 19 organization-admin user access  
**Implementation:** `frontend/src/styles.css` and shared UI components in `frontend/src/components/Ui.tsx`

## Product feel

The workspace should feel calm, precise, and operational. A deep ink sidebar anchors navigation, while warm near-white surfaces keep case information readable. Teal marks primary actions and verified navigation; amber identifies review or pending states; red is reserved for failures and rejected outcomes. Dense operational data uses clear spacing and restrained borders rather than decorative charts or fictional totals.

The interface uses system fonts and locally bundled icons. It does not request remote fonts or images. The same custom VerifiaAI SVG mark appears in the application shell, sign-in page, and browser favicon alongside the text wordmark.

## Tokens

| Purpose | Token | Value |
|---|---|---|
| Page canvas | `--canvas` | `#f3f6f5` |
| Main text | `--ink` | `#17282d` |
| Secondary text | `--muted` | `#5d6e72` |
| Surface and border | `--surface`, `--line` | `#ffffff`, `#dce5e3` |
| Navigation | `--navy` | `#152a2f` |
| Primary action | `--teal` | `#0b716a` |
| Review state | `--amber` | `#9a5d16` |
| Error state | `--red` | `#a73e3c` |
| Confirmed success | `--green` | `#176b53` |

The root design tokens also define semantic soft fills and borders, focus color, spacing, type sizes, radii, elevation, and shadows. Status tone is mapped by the backend enum string. `PASS`, `APPROVED`, and completed states are positive. `FAIL`, `FAILED`, `REJECTED`, and `CANCELLED` are negative. `REVIEW`, `INCONCLUSIVE`, `PENDING_REVIEW`, `NEEDS_REVIEW`, and active processing states are caution. Unknown values remain neutral. `INCONCLUSIVE` never receives the pass treatment.

## Layout and navigation

- Desktop uses a fixed navigation rail and a fluid content column.
- At tablet widths, the rail becomes a dismissible dialog drawer with a visible scrim, focus containment, Escape handling, and focus restoration.
- At narrow widths, metrics and metadata use compact grids; tables scroll horizontally; case sections remain horizontally navigable.
- The page header states the current task and uses supporting copy to explain data scope.
- A skip link moves keyboard users directly to the page content.
- No charts are shown where the API does not provide aggregate totals.

## Shared components

`PageHeader`, `SectionHeading`, `Button`, `Field`, `StatusBadge`, `LoadingState`, `ErrorState`, `EmptyState`, `SuccessNotice`, and `ErrorNotice` provide consistent page hierarchy and feedback. `ConfirmDialog` supplies an accessible modal pattern with focus containment, Escape handling, and disabled submission while a mutation is pending.

Every query-driven page has distinct loading, empty, and error feedback. A failed request is never presented as an empty queue. Partial dashboard failures are called out separately from the sections that remain available.

## Accessibility and interaction

- Semantic headings, navigation, tables, labels, and alert/status roles are used for screen reader context.
- All interactive controls have visible keyboard focus and touch-friendly hit areas.
- Dialogs and the mobile navigation drawer are labelled, trap Tab navigation, close on Escape when idle, and cannot submit while a request is pending.
- `prefers-reduced-motion` disables nonessential animation and transitions.
- Color is paired with text labels for status; color alone is not the meaning.
- Search copy states when it filters only the returned API page.

## Data and trust boundaries

- Status, counts, case fields, tasks, and approval outcomes are displayed from backend responses.
- Case totals are bounded by the API’s 100-record page and are labelled as a returned window, not an organization-wide count.
- AI recommendations are labelled advisory. A Supervisor run requires an explicit action and confirmation, and the UI displays only summary/proposal fields.
- Documents are downloaded as authenticated Blobs. The UI previews supported PDFs and images; it does not render uploaded HTML or arbitrary files inline.
- Customer case listing, details, creation, and uploads use participant-scoped backend endpoints. Public signup is retired; an organization ADMIN can provision only CUSTOMER, EMPLOYEE, and MANAGER accounts through the API.

## Visual QA checklist

When a browser and running backend are available, inspect the login, overview, case register, case workspace sections, task queue, and approval dialog at desktop, tablet, and mobile widths. Check keyboard-only navigation, focus visibility, reduced-motion settings, long case names, empty/error states, and narrow horizontal table overflow. This manual browser review remains distinct from the automated frontend checks.
