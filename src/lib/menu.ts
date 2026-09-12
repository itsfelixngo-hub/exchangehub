import { MENU_GROUPS, pairUrl } from "./config";

export type MenuLink = { label: string; href: string; active?: boolean };
export type MenuGroup = { title: string; links: MenuLink[] };
export type HeaderGroup = { base: string; label: string; links: MenuLink[] };

export type MenuModel = {
  groups: MenuGroup[];
  footerLinks: MenuLink[];
  headerGroups: HeaderGroup[];
  activeHeaderBase: string | null;
  activeHeaderTarget: string | null;
  activeHeaderLinks: MenuLink[];
};

export function buildMenuModel(activeBase?: string, activeTarget?: string): MenuModel {
  const base = activeBase ? activeBase.toUpperCase() : null;
  const target = activeTarget ? activeTarget.toUpperCase() : null;

  const groups: MenuGroup[] = [];
  const seen: [string, string][] = [];
  for (const [b, targets] of Object.entries(MENU_GROUPS)) {
    const links: MenuLink[] = [];
    for (const t of targets) {
      if (b === t) continue;
      seen.push([b, t]);
      links.push({ label: `${b}/${t}`, href: pairUrl(b, t) });
    }
    groups.push({ title: `${b} pairs`, links });
  }

  const footerLinks: MenuLink[] = seen.slice(0, 30).map(([b, t]) => ({
    label: `${b} to ${t}`,
    href: pairUrl(b, t),
  }));

  const headerGroups: HeaderGroup[] = Object.entries(MENU_GROUPS).map(([b, targets]) => ({
    base: b,
    label: `${b} pairs`,
    links: targets.filter((t) => t !== b).map((t) => ({ label: `${b}/${t}`, href: pairUrl(b, t) })),
  }));

  const activeHeaderLinks: MenuLink[] = base
    ? (MENU_GROUPS[base] ?? []).filter((t) => t !== base).map((t) => ({
        label: `${base}/${t}`,
        href: pairUrl(base, t),
        active: t === target,
      }))
    : [];

  return {
    groups,
    footerLinks,
    headerGroups,
    activeHeaderBase: base,
    activeHeaderTarget: target,
    activeHeaderLinks,
  };
}
