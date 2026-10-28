import { useEffect, useRef, useState } from "react";
import {
  BriefcaseBusiness,
  ClipboardList,
  LayoutDashboard,
  LogOut,
  Menu,
  ShieldCheck,
  UsersRound,
  X,
} from "lucide-react";
import { Link, NavLink, Outlet, useLocation } from "react-router";
import { useAuth } from "../auth/AuthContext";

const navigation = [
  { to: "/overview", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/cases", label: "Cases", icon: BriefcaseBusiness, end: false },
  { to: "/tasks", label: "My tasks", icon: ClipboardList, end: true },
];

function sectionLabel(pathname: string): string {
  if (pathname.startsWith("/customer/cases/")) return "Case details";
  if (pathname.startsWith("/customer/cases")) return "Your cases";
  if (pathname.startsWith("/cases/")) return "Case workspace";
  if (pathname.startsWith("/cases")) return "Case register";
  if (pathname.startsWith("/tasks")) return "My tasks";
  if (pathname.startsWith("/approvals")) return "Approvals";
  if (pathname.startsWith("/admin/users")) return "User access";
  return "Operations overview";
}

export function AppShell() {
  const { user, logout } = useAuth();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(() => window.matchMedia?.("(max-width: 820px)").matches ?? false);
  const toggleRef = useRef<HTMLButtonElement>(null);
  const sidebarRef = useRef<HTMLElement>(null);
  const returnFocusRef = useRef<HTMLElement | null>(null);
  const canApprove = user?.role === "MANAGER" || user?.role === "ADMIN";
  const canManageUsers = user?.role === "ADMIN";
  const customerMode = user?.role === "CUSTOMER";
  const activeNavigation = customerMode
    ? [{ to: "/customer/cases", label: "Your cases", icon: BriefcaseBusiness, end: false }]
    : navigation;
  const homePath = customerMode ? "/customer/cases" : "/overview";
  const initials = user?.full_name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("") || "V";

  useEffect(() => {
    const media = window.matchMedia?.("(max-width: 820px)");
    if (!media) return;
    const update = () => {
      setIsMobile(media.matches);
      if (!media.matches) setMobileOpen(false);
    };
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    if (!isMobile || !mobileOpen) return;
    returnFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const firstLink = sidebarRef.current?.querySelector<HTMLElement>("a[href], button:not([disabled])");
    firstLink?.focus();

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setMobileOpen(false);
        toggleRef.current?.focus();
      }
      if (event.key !== "Tab" || !sidebarRef.current) return;
      const focusable = Array.from(
        sidebarRef.current.querySelectorAll<HTMLElement>("a[href], button:not([disabled]), [tabindex]:not([tabindex='-1'])"),
      );
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (!first || !last) return;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isMobile, mobileOpen]);

  useEffect(() => {
    if (mobileOpen || !returnFocusRef.current) return;
    returnFocusRef.current.focus();
    returnFocusRef.current = null;
  }, [mobileOpen]);

  function handleNavigation() {
    setMobileOpen(false);
    if (!isMobile) return;
    returnFocusRef.current = null;
    window.requestAnimationFrame(() => document.getElementById("main-content")?.focus());
  }

  return (
    <div className="app-frame">
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <button
        ref={toggleRef}
        className="mobile-menu-toggle"
        type="button"
        aria-label={mobileOpen ? "Close navigation" : "Open navigation"}
        aria-expanded={mobileOpen}
        aria-controls="primary-navigation"
        onClick={() => setMobileOpen((value) => !value)}
      >
        {mobileOpen ? <X size={20} aria-hidden="true" /> : <Menu size={20} aria-hidden="true" />}
      </button>
      {mobileOpen && <button className="mobile-scrim" type="button" aria-label="Close navigation" tabIndex={-1} onClick={() => setMobileOpen(false)} />}

      <aside
        ref={sidebarRef}
        className={`sidebar ${mobileOpen ? "sidebar-open" : ""}`}
        aria-label="Main navigation"
        aria-hidden={isMobile && !mobileOpen}
        inert={isMobile && !mobileOpen}
        role={isMobile && mobileOpen ? "dialog" : undefined}
        aria-modal={isMobile && mobileOpen ? true : undefined}
      >
        <Link className="brand-lockup" to={homePath} aria-label="VerifiaAI workspace home">
          <img className="brand-symbol" src="/verifia-mark.svg" alt="" width="40" height="40" />
          <span className="brand-copy"><strong>Verifia <span>AI</span></strong><small>{customerMode ? "Customer portal" : "Operations workspace"}</small></span>
        </Link>

        <div className="workspace-switcher" aria-label="Current organization scope">
          <span className="workspace-avatar" aria-hidden="true">V</span>
          <span className="workspace-label"><strong>{customerMode ? "Customer account" : "Current workspace"}</strong><small>{customerMode ? "Your linked cases" : "Organization scoped"}</small></span>
          <ShieldCheck size={16} className="workspace-indicator" aria-hidden="true" />
        </div>

        <nav id="primary-navigation" className="primary-nav" aria-label="Workspace" onClick={handleNavigation}>
          <p className="nav-section-label">{customerMode ? "Customer portal" : "Workspace"}</p>
          {activeNavigation.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end} className={({ isActive }) => `nav-link ${isActive ? "nav-link-active" : ""}`}>
              <Icon size={18} strokeWidth={1.9} aria-hidden="true" />
              <span>{label}</span>
            </NavLink>
          ))}
          {!customerMode && canApprove && (
            <NavLink to="/approvals" className={({ isActive }) => `nav-link ${isActive ? "nav-link-active" : ""}`}>
              <ShieldCheck size={18} strokeWidth={1.9} aria-hidden="true" />
              <span>Approvals</span>
            </NavLink>
          )}
          {!customerMode && canManageUsers && (
            <NavLink to="/admin/users" className={({ isActive }) => `nav-link ${isActive ? "nav-link-active" : ""}`}>
              <UsersRound size={18} strokeWidth={1.9} aria-hidden="true" />
              <span>User access</span>
            </NavLink>
          )}
        </nav>

        <div className="sidebar-footer">
          <div className="user-avatar" aria-hidden="true">{initials}</div>
          <div className="user-summary">
            <strong>{user?.full_name || "Verifia operator"}</strong>
            <small>{user?.role ?? "Signed in"}</small>
          </div>
          <button className="signout-button" type="button" aria-label="Sign out" title="Sign out" onClick={logout}>
            <LogOut size={17} aria-hidden="true" />
          </button>
        </div>
      </aside>

      <div className="main-column" inert={isMobile && mobileOpen} aria-hidden={isMobile && mobileOpen}>
        <header className="topbar">
          <div className="topbar-context">
            <Link className="topbar-kicker" to={homePath}>VERIFIAAI</Link>
            <span className="topbar-divider" aria-hidden="true">/</span>
            <span aria-current="page">{sectionLabel(location.pathname)}</span>
          </div>
          <div className="topbar-right">
            <span className="connection-chip"><span aria-hidden="true" /> Signed in</span>
            <span className="topbar-avatar" aria-hidden="true">{initials}</span>
          </div>
        </header>
        <main className="page-content" id="main-content" tabIndex={-1}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
