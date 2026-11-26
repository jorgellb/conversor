"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { type ReactNode, useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";

import type { MegaMenuPanel } from "@/lib/menu-items";

import { CategoryIcon, categoryColor } from "./art/CategoryIcon";
import { PageLink } from "./PageLink";

export type MegaMenuItem = { id: string; href: string; label: string; count: string };
export type MegaMenuLabels = {
  nav: string; close: string; seeAll: string; inBrowser: string; submenu: string; title: string; loading: string;
};

/*
 * Submenú de cada categoría (D-272). Una sola lista sirve para los dos tamaños:
 * - desde 1024 px, barra de categorías con un panel desplegable por categoría (al pasar el ratón, o con su botón ▾ desde
 *   el teclado), con las secciones de la categoría y sus herramientas más buscadas;
 * - por debajo, la misma lista dentro de una hoja a pantalla completa que abre el botón «Menú», con cada categoría como
 *   acordeón.
 * La barra viene en el HTML; el contenido de los paneles se pide aparte (/api/menu/<idioma>, el mismo para todo el sitio
 * y en caché) cuando el navegador está libre o al primer gesto, para no cargar cada página con sus 190 enlaces.
 * El botón «Menú» vive en la otra fila de la cabecera y comparte con la lista un estado del módulo.
 */
let drawerOpen = false;
const listeners = new Set<() => void>();
function setDrawer(value: boolean) {
  drawerOpen = value;
  for (const listener of listeners) listener();
}
function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
function useDrawer() {
  return useSyncExternalStore(subscribe, () => drawerOpen, () => false);
}

const DESKTOP = "(min-width: 1024px)";

let panelsPromise: Promise<MegaMenuPanel[]> | null = null;
function loadPanels(locale: string): Promise<MegaMenuPanel[]> {
  panelsPromise ??= fetch(`/api/menu/${locale}`).then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))));
  panelsPromise.catch(() => { panelsPromise = null; });
  return panelsPromise;
}

export function MenuToggle({ label }: { label: string }) {
  const open = useDrawer();
  return (
    <button type="button" className="mm-toggle" data-mm-toggle aria-expanded={open} aria-controls="menu-categorias"
      onClick={() => setDrawer(!open)}>
      <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <path d="M4 7h16M4 12h16M4 17h10" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      </svg>
      <span>{label}</span>
    </button>
  );
}

function Chevron() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d="m6 9 6 6 6-6" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function Arrow() {
  return (
    <svg className="mm-arrow" width="14" height="14" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d="M5 12h14M13 6l6 6-6 6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function MegaMenu({ locale, items, labels, children }: {
  locale: string; items: MegaMenuItem[]; labels: MegaMenuLabels; children?: ReactNode;
}) {
  const pathname = usePathname();
  const drawer = useDrawer();
  const [open, setOpen] = useState<string | null>(null);
  const [panels, setPanels] = useState<Record<string, MegaMenuPanel> | null>(null);
  const load = useCallback(() => {
    loadPanels(locale).then((list) => setPanels(Object.fromEntries(list.map((p) => [p.id, p])))).catch(() => {});
  }, [locale]);

  // Se pide cuando el navegador queda libre, para que el primer panel se abra ya lleno.
  useEffect(() => {
    // Safari aún no tiene requestIdleCallback.
    if (typeof window.requestIdleCallback === "function") {
      const id = window.requestIdleCallback(load, { timeout: 4000 });
      return () => window.cancelIdleCallback(id);
    }
    const id = setTimeout(load, 2500);
    return () => clearTimeout(id);
  }, [load]);
  useEffect(() => {
    if ((open || drawer) && !panels) load();
  }, [open, drawer, panels, load]);
  const navRef = useRef<HTMLElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const timer = useRef<number | undefined>(undefined);

  const isDesktop = () => window.matchMedia(DESKTOP).matches;
  const schedule = useCallback((next: string | null, ms: number) => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setOpen(next), ms);
  }, []);

  // Al navegar se cierra todo.
  useEffect(() => {
    setOpen(null);
    setDrawer(false);
  }, [pathname]);

  // Escape cierra el panel (y devuelve el foco a su botón) o la hoja; un clic fuera cierra el panel.
  useEffect(() => {
    if (!open && !drawer) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (drawer) {
        setOpen(null);
        setDrawer(false);
        document.querySelector<HTMLButtonElement>("[data-mm-toggle]")?.focus();
      } else if (open) {
        const id = open;
        setOpen(null);
        navRef.current?.querySelector<HTMLButtonElement>(`[data-mm-caret="${id}"]`)?.focus();
      }
    };
    const onDown = (e: PointerEvent) => {
      if (open && isDesktop() && !navRef.current?.contains(e.target as Node)) setOpen(null);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onDown);
    };
  }, [open, drawer]);

  // La hoja de móvil bloquea el desplazamiento de la página y se cierra sola si la ventana pasa a escritorio.
  useEffect(() => {
    if (!drawer) return;
    const root = document.documentElement;
    const previous = root.style.overflow;
    root.style.overflow = "hidden";
    closeRef.current?.focus();
    const mq = window.matchMedia(DESKTOP);
    const onChange = () => mq.matches && setDrawer(false);
    mq.addEventListener("change", onChange);
    return () => {
      root.style.overflow = previous;
      mq.removeEventListener("change", onChange);
    };
  }, [drawer]);

  useEffect(() => () => window.clearTimeout(timer.current), []);

  return (
    <>
      <nav ref={navRef} id="menu-categorias" className="mm" aria-label={labels.nav} data-drawer={drawer ? "open" : undefined}
        onPointerEnter={() => !panels && load()}
        onPointerLeave={(e) => e.pointerType === "mouse" && isDesktop() && schedule(null, 160)}
        onBlur={(e) => {
          if (isDesktop() && !e.currentTarget.contains(e.relatedTarget as Node | null)) setOpen(null);
        }}>
        <div className="mm-sheet-head">
          <span className="display text-lg font-extrabold">{labels.title}</span>
          <button ref={closeRef} type="button" className="mm-close" aria-label={labels.close} onClick={() => {
            setDrawer(false);
            document.querySelector<HTMLButtonElement>("[data-mm-toggle]")?.focus();
          }}>
            <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
              <path d="M6 6l12 12M18 6 6 18" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
            </svg>
          </button>
        </div>
        <ul className="mm-bar">
          {items.map((item) => {
            const current = pathname === item.href;
            const expanded = open === item.id;
            const panelId = `mm-panel-${item.id}`;
            return (
              <li key={item.id} className="mm-item" style={categoryColor(item.id)} data-open={expanded ? "" : undefined}
                onPointerEnter={(e) => e.pointerType === "mouse" && isDesktop() && schedule(item.id, open ? 40 : 110)}>
                <div className="mm-row">
                  <Link href={item.href} className="mm-link" aria-current={current ? "page" : undefined}>
                    <span className="mm-ico"><CategoryIcon id={item.id} size={18} /></span>
                    <span className="mm-link-text">
                      <span>{item.label}</span>
                      <span className="mm-link-count">{item.count}</span>
                    </span>
                  </Link>
                  <button type="button" className="mm-caret" data-mm-caret={item.id} aria-expanded={expanded} aria-controls={panelId}
                    aria-label={`${labels.submenu}: ${item.label}`} onClick={() => {
                      window.clearTimeout(timer.current);
                      setOpen(expanded ? null : item.id);
                    }}>
                    <Chevron />
                  </button>
                </div>
                <div id={panelId} className="mm-panel">
                  {expanded && <Panel item={item} panel={panels?.[item.id]} labels={labels} />}
                </div>
              </li>
            );
          })}
        </ul>
        {/* Precios y cuenta: en móvil salen de la fila de arriba y van al pie de la hoja. */}
        <div className="mm-sheet-foot">{children}</div>
      </nav>
      {/* Fuera de la cabecera: su backdrop-filter haría de caja de los elementos fijos y el velo no taparía la página. */}
      {open && createPortal(<div className="mm-scrim" aria-hidden="true" onPointerDown={() => setOpen(null)} />, document.body)}
    </>
  );
}

function Panel({ item, panel, labels }: { item: MegaMenuItem; panel?: MegaMenuPanel; labels: MegaMenuLabels }) {
  if (!panel) {
    return (
      <div className="mm-loading" role="status" aria-label={labels.loading}>
        {[0, 1, 2].map((i) => <span key={i} />)}
      </div>
    );
  }
  return (
    <>
      <div className="mm-aside">
        <span className="mm-aside-bg" aria-hidden="true"><CategoryIcon id={item.id} size={220} /></span>
        <span className="mm-aside-ico"><CategoryIcon id={item.id} size={34} /></span>
        <p className="display mt-3 text-2xl font-extrabold">{item.label}</p>
        <p className="muted mt-1 text-sm">{panel.blurb}</p>
        <p className="mm-count">{panel.count}</p>
        <Link href={item.href} className="mm-cta">
          {labels.seeAll}
          <Arrow />
        </Link>
        <p className="mm-legend"><span className="mm-local" aria-hidden="true" />{labels.inBrowser}</p>
      </div>
      <div className={`mm-groups mm-groups-${Math.min(panel.groups.length, 3)}`}>
        {panel.groups.map((group) => (
          <div key={group.id} className="mm-group">
            <p className="mm-group-title">
              <span>{group.label}</span>
              <span className="mm-group-n">{group.total}</span>
            </p>
            <ul>
              {group.tools.map((tool) => (
                <li key={tool.href}>
                  <PageLink href={tool.href} className="mm-tool">
                    <span>{tool.name}</span>
                    {tool.client && <span className="mm-local" title={labels.inBrowser}><span className="sr-only">{labels.inBrowser}</span></span>}
                  </PageLink>
                </li>
              ))}
            </ul>
            {group.total > group.tools.length && (
              <Link href={group.href} className="mm-more">
                {group.more}
                <Arrow />
              </Link>
            )}
          </div>
        ))}
      </div>
    </>
  );
}
