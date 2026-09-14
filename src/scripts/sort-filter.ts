/* The behaviour behind SortFilterBar.astro, shared by the three lists that
 * carry one: the home rate board, the pair table on a currency hub and the
 * card grid on /analysis.
 *
 * It owns only ordering and matching. What a hidden item looks like differs
 * per list — the board's rows are `display:flex` with zebra stripes, the hub's
 * are table rows, the analysis cards use the `hidden` attribute — so the list
 * itself is handed the result and decides. Everything is read off the items'
 * own `data-sf-*` attributes, which both the server render and the client
 * re-render stamp on, so no list has to keep a parallel copy of its data.
 */

export type SortFilterHandle = {
  /** Re-run the current filter and sort — after rows are re-rendered. */
  refresh: () => void;
  /** Re-apply without re-indexing, e.g. after "Load more" moves the cut-off. */
  apply: () => void;
};

export type SortFilterOptions = {
  /** The bar rendered by SortFilterBar.astro. A page missing it still gets
   *  working `apply`/`refresh` calls, just with nothing to drive them. */
  bar: HTMLElement | null;
  /** The element the items live in; they are re-appended here in sort order. */
  container: HTMLElement;
  itemSelector: string;
  /**
   * Called after every pass with the items that match the search box, in their
   * new document order, and with every item so the caller can hide the rest.
   */
  onApply: (matched: HTMLElement[], all: HTMLElement[]) => void;
  /** Runs before a pass the visitor triggered, never before a `refresh()`. */
  onInput?: () => void;
  /** Word for the "3 of 19 …" readout, e.g. "currencies", "pairs". */
  countNoun?: string;
};

function numeric(value: string | undefined): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : NaN;
}

export function wireSortFilter(options: SortFilterOptions): SortFilterHandle {
  const { bar, container, itemSelector, onApply, onInput, countNoun = "results" } = options;
  const search = bar?.querySelector<HTMLInputElement>("[data-sf-search]");
  // A listbox rather than a `<select>` — see scripts/sort-menu.ts. It keeps
  // the two things read here: a value, and a bubbling `change` when it moves.
  const sort = bar?.querySelector<HTMLElement>("[data-sf-sort]");
  const sortValue = () => sort?.dataset.value || "order-asc";
  const count = bar?.querySelector<HTMLElement>("[data-sf-count]");

  const items = () => Array.from(container.querySelectorAll<HTMLElement>(itemSelector));

  // The order the server sent, kept so "Default" can restore it. Items that
  // already carry an index keep it: a sort has moved them since, and
  // re-indexing there would make the current order the default one.
  const indexItems = () => {
    items().forEach((el, i) => {
      if (el.dataset.sfOrder === undefined) el.dataset.sfOrder = String(i);
    });
  };

  const compare = (a: HTMLElement, b: HTMLElement, field: string, direction: string) => {
    const sign = direction === "desc" ? -1 : 1;
    if (field === "code") {
      return sign * (a.dataset.sfCode || "").localeCompare(b.dataset.sfCode || "");
    }
    const key = field === "rate" ? "sfRate" : field === "change" ? "sfChange" : "sfOrder";
    const left = numeric(a.dataset[key]);
    const right = numeric(b.dataset[key]);
    // A row with no number to sort on sits at the bottom either way rather
    // than jumping to the top when the direction flips.
    if (Number.isNaN(left) || Number.isNaN(right)) {
      return Number.isNaN(left) ? (Number.isNaN(right) ? 0 : 1) : -1;
    }
    return sign * (left - right);
  };

  const apply = () => {
    const all = items();
    const [field, direction] = sortValue().split("-");
    const sorted = all.slice().sort((a, b) => compare(a, b, field, direction));
    // Re-appending an element that is already in place still moves it, so only
    // pay for the reflow when the order actually changed.
    if (sorted.some((el, i) => el !== all[i])) {
      const fragment = document.createDocumentFragment();
      for (const el of sorted) fragment.appendChild(el);
      container.appendChild(fragment);
    }

    const query = (search?.value || "").trim().toLowerCase();
    const matched = query
      ? sorted.filter((el) => (el.dataset.sfSearch || "").includes(query))
      : sorted;
    if (count) {
      count.textContent = query ? `${matched.length} of ${sorted.length} ${countNoun}` : "";
    }
    onApply(matched, sorted);
  };

  const applyFromInput = () => {
    onInput?.();
    apply();
  };

  search?.addEventListener("input", applyFromInput);
  sort?.addEventListener("change", applyFromInput);
  indexItems();

  return {
    apply,
    refresh: () => {
      indexItems();
      apply();
    },
  };
}
