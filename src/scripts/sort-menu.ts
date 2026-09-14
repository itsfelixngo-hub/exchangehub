/* The dropdown half of SortFilterBar.astro: a listbox standing in for a
 * `<select>`, because a native one draws its popup from the operating system
 * and there is no way to bring that into the page's own dark styling.
 *
 * What it keeps from the element it replaces is the part scripts/sort-filter.ts
 * reads: the chosen value (here on `data-value`) and a bubbling `change` event
 * when it moves.
 */

const OPEN = "[data-sf-sort] .sf-menu-panel:not([hidden])";

function closeAll(except?: Element) {
  for (const panel of document.querySelectorAll<HTMLElement>(OPEN)) {
    if (panel === except) continue;
    panel.hidden = true;
    panel.parentElement?.querySelector(".sf-menu-btn")?.setAttribute("aria-expanded", "false");
  }
}

function wireMenu(menu: HTMLElement) {
  const button = menu.querySelector<HTMLButtonElement>(".sf-menu-btn");
  const panel = menu.querySelector<HTMLElement>(".sf-menu-panel");
  const label = menu.querySelector<HTMLElement>("[data-sf-menu-label]");
  if (!button || !panel) return;
  const optionsOf = () => Array.from(panel.querySelectorAll<HTMLButtonElement>(".sf-menu-option"));

  const setOpen = (open: boolean) => {
    closeAll(open ? panel : undefined);
    panel.hidden = !open;
    button.setAttribute("aria-expanded", open ? "true" : "false");
    if (open) {
      (optionsOf().find((o) => o.getAttribute("aria-selected") === "true") ?? optionsOf()[0])?.focus();
    }
  };

  const choose = (option: HTMLElement) => {
    const value = option.dataset.value || "";
    if (value !== menu.dataset.value) {
      menu.dataset.value = value;
      if (label) label.textContent = option.textContent?.trim() || value;
      for (const other of optionsOf()) {
        other.setAttribute("aria-selected", other === option ? "true" : "false");
      }
      // What wireSortFilter listens for — same event a `<select>` would send.
      menu.dispatchEvent(new Event("change", { bubbles: true }));
    }
    setOpen(false);
    button.focus();
  };

  // The board's base-currency bar opens its currency picker on any click; the
  // dropdown sitting inside it must not also do that.
  menu.addEventListener("click", (event) => event.stopPropagation());
  // `hidden` is typed `boolean | "until-found"`, hence the coercion.
  button.addEventListener("click", () => setOpen(Boolean(panel.hidden)));
  panel.addEventListener("click", (event) => {
    const target = event.target;
    const option = target instanceof Element ? target.closest<HTMLElement>(".sf-menu-option") : null;
    if (option) choose(option);
  });

  menu.addEventListener("keydown", (event) => {
    const key = (event as KeyboardEvent).key;
    if (key === "Escape" && !panel.hidden) {
      setOpen(false);
      button.focus();
      return;
    }
    if (key !== "ArrowDown" && key !== "ArrowUp") return;
    event.preventDefault();
    if (panel.hidden) {
      setOpen(true);
      return;
    }
    const options = optionsOf();
    const at = options.indexOf(document.activeElement as HTMLButtonElement);
    const next = key === "ArrowDown"
      ? Math.min(options.length - 1, at + 1)
      : Math.max(0, at - 1);
    options[at === -1 ? 0 : next]?.focus();
  });
}

let documentWired = false;

export function wireSortMenus(root: ParentNode = document) {
  for (const menu of root.querySelectorAll<HTMLElement>("[data-sf-sort]")) {
    if (menu.dataset.sfMenuWired) continue;
    menu.dataset.sfMenuWired = "true";
    wireMenu(menu);
  }
  if (!documentWired) {
    documentWired = true;
    document.addEventListener("click", () => closeAll());
  }
}
