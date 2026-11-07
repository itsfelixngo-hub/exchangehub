// Every Adsterra unit the site shows, and the only place their codes live.
// AdSlot.astro reserves the space and decides which unit goes in it; nothing
// else on the site should hold an ad key or script URL.
//
// The keys and script URLs are Adsterra's, copied as issued — do not edit
// them. bannerSnippet() rebuilds the exact snippet Adsterra hands out, which
// each banner then runs inside an iframe of its own (see AdSlot.astro).

export interface BannerUnit {
  key: string;
  width: number;
  height: number;
  src: string;
}

/** Slot 1 on screens 768px and wider. */
export const BANNER_728x90: BannerUnit = {
  key: "795ec92039b167feae083553a6a70058",
  width: 728,
  height: 90,
  src: "https://bauval.org/22/795ec92039b167feae083553a6a70058",
};

/** Slot 1 below 768px. */
export const BANNER_320x50: BannerUnit = {
  key: "f95b6a10c5bc286348771af089bda200",
  width: 320,
  height: 50,
  src: "https://bauval.org/22/f95b6a10c5bc286348771af089bda200",
};

/** Slot 2, under the converter. */
export const BANNER_300x250: BannerUnit = {
  key: "4d66d9fd4f9b40d1691a268691113df2",
  width: 300,
  height: 250,
  src: "https://bauval.org/22/4d66d9fd4f9b40d1691a268691113df2",
};

/**
 * Slot 3, above the footer. The script fills the element with this exact id,
 * so it can appear only once on a page.
 */
export const NATIVE_BANNER = {
  src: "https://bauval.org/21/ffba18719b395e898dc75da2457b7ccd",
  containerId: "container-ffba18719b395e898dc75da2457b7ccd",
};

/**
 * Adsterra's banner snippet, as issued. `atOptions` is a global the second
 * script reads, which is why each banner gets a document of its own.
 * `<\/script>` is `</script>`, escaped so this text never closes a script
 * element if the bundle is inlined into the page.
 */
export function bannerSnippet(unit: BannerUnit): string {
  return `<script>
  atOptions = {
    'key' : '${unit.key}',
    'format' : 'iframe',
    'height' : ${unit.height},
    'width' : ${unit.width},
    'params' : {}
  };
<\/script>
<script src="${unit.src}"><\/script>`;
}

export type AdSlotName = "below-main" | "below-converter" | "above-footer";

/**
 * Pages allowed to carry ads: the home page, a currency hub (/vnd) and a pair
 * page (/vnd-usd). About, Contact, the legal pages, /chart and /analysis are
 * left out, and a 404 renders no layout at all. Paths reach here already
 * lower-cased and canonical (src/middleware.ts).
 */
export function isAdPage(pathname: string): boolean {
  return pathname === "/" || /^\/[a-z]{3}(-[a-z]{3})?\/?$/.test(pathname);
}
