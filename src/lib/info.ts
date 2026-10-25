import "./env";

// The one email address the site shows anywhere. Started as the Flask app's
// INFO_PAGES copy; About and Disclaimer have since been rewritten.
export const CONTACT_EMAIL = process.env.SITE_CONTACT_EMAIL ?? "contact@ratehubfx.com";

/**
 * The day the copy below last changed, as `sitemap.xml` reports it for the
 * info pages. Bump it when you edit INFO_PAGES — a wrong date here is better
 * than the old behaviour, which stamped today onto every URL on every crawl
 * and taught Google to ignore this site's lastmod entirely.
 */
export const INFO_CONTENT_LAST_MODIFIED = "2026-10-25";

export type InfoSection = {
  heading: string;
  /** Plain text. `[label](https://…)` becomes a link, and CONTACT_EMAIL a mailto link (InfoPage.astro). */
  body: string[];
};

export type InfoPage = {
  /** Small pill above the title. */
  eyebrow: string;
  title: string;
  description: string;
  heading: string;
  sections: InfoSection[];
};

export const INFO_PAGES = {
  about: {
    eyebrow: "About",
    title: "About ratehubfx.com",
    description: "ratehubfx.com is an independent exchange-rate reference site run from Vietnam, with mid-market rates from Open Exchange Rates, a converter, charts and 7-day statistics.",
    heading: "About ratehubfx.com",
    sections: [
      {
        heading: "What this site is",
        body: [
          "ratehubfx.com (shown in the header as ExchangeHub) is a small reference site for checking exchange rates. Each currency pair has its own page with the latest mid-market rate, a converter, a chart, and statistics for the last 7 days: the high, the low, the average and the change.",
          "Most attention goes to the pairs between the US dollar, euro, British pound, Japanese yen, Chinese yuan and Vietnamese dong, because those are the conversions the site's readers look up most. Other currencies are covered against the US dollar.",
        ],
      },
      {
        heading: "Who runs it",
        body: [
          "ratehubfx.com is operated by Ngo Minh Tam, based in Vietnam. It is an independent project, not a bank, broker, money-transfer service or any other kind of financial institution. The site does not exchange, hold or send money, and it is not affiliated with any company that does.",
        ],
      },
      {
        heading: "Where the rates come from",
        body: [
          "Rates come from [Open Exchange Rates](https://openexchangerates.org/), which publishes a mid-market rate for each currency against the US dollar. They are updated continuously, on the schedule set by the provider.",
          "Rates between two currencies other than the dollar, such as EUR/VND, are calculated from each currency's dollar rate at the same update. Every pair page shows when its rate was last updated.",
        ],
      },
      {
        heading: "What the numbers are for",
        body: [
          "The rates are a reference for comparison. A bank, card or transfer service will quote its own rate, usually with a margin and fees on top of the mid-market rate, so the amount you actually receive will differ. Nothing on this site is financial advice; the disclaimer page explains the limits in more detail.",
          `Corrections and questions are welcome at ${CONTACT_EMAIL}.`,
        ],
      },
    ],
  },
  contact: {
    eyebrow: "Contact",
    title: "Contact ExchangeHub",
    description: "Contact ExchangeHub for feedback, correction requests, partnerships, and exchange-rate content questions.",
    heading: "Contact",
    sections: [
      {
        heading: "Feedback and corrections",
        body: [
          "If you find a broken page, stale data, confusing explanation, or exchange-rate display issue, please contact the site owner so it can be reviewed.",
          `Send feedback, correction requests, and partnership questions to ${CONTACT_EMAIL}.`,
        ],
      },
      {
        heading: "Response scope",
        body: [
          "ExchangeHub can review site issues, data display problems, and general content questions. The site does not provide personal financial, banking, tax, legal, or investment advice.",
        ],
      },
    ],
  },
  "privacy-policy": {
    eyebrow: "Privacy",
    title: "Privacy Policy",
    description: "Privacy Policy for ExchangeHub, including analytics, advertising, cookies, and server log information.",
    heading: "Privacy Policy",
    sections: [
      {
        heading: "Information we may collect",
        body: [
          "ExchangeHub may collect standard server log information such as IP address, browser type, referring page, device information, request time, and pages visited. This information helps monitor performance, security, and usage patterns.",
          "If analytics or advertising products are enabled, those providers may use cookies or similar technologies to measure traffic, prevent fraud, personalize or limit ads, and report aggregate performance.",
        ],
      },
      {
        heading: "Cookies this site sets",
        body: [
          "ExchangeHub sets a small number of first-party cookies for the site to work: a language preference cookie recording the language chosen in the header, the cookie Google's translation widget uses to remember that choice, and a short-lived cookie issued to the contact form to reject automated submissions.",
          "These cookies carry no advertising identifier and are not shared with advertising partners.",
        ],
      },
      {
        heading: "Third-party advertising and Google",
        body: [
          "Third-party vendors, including Google, use cookies to serve ads based on a user's prior visits to this website or other websites.",
          "Google's use of advertising cookies enables it and its partners to serve ads to users based on their visit to this site and/or other sites on the Internet.",
          "Users may opt out of personalised advertising by visiting Google's Ads Settings at https://www.google.com/settings/ads. Further detail is published at https://policies.google.com/technologies/ads.",
          "Where third-party vendors other than Google are used, users may opt out of personalised advertising through http://www.aboutads.info/choices/.",
        ],
      },
      {
        heading: "How data is used",
        body: [
          "Collected information is used to operate the site, improve page performance, detect abuse, understand which tools are useful, and comply with legal or platform requirements.",
          "ExchangeHub does not ask users to create accounts for basic currency conversion pages. Do not enter private banking, card, wallet, or personal financial information into any public exchange-rate tool.",
        ],
      },
      {
        heading: "How long data is kept",
        body: [
          "Server logs are retained only as long as needed to investigate performance and abuse, and are then deleted or aggregated so that individual visits can no longer be identified.",
          "Messages sent through the contact form are kept while the request is handled and for a reasonable period afterwards for reference, then deleted on request.",
          "Retention of any advertising or analytics data is governed by the provider that collects it, under its own policy.",
        ],
      },
      {
        heading: "Visitors in the European Economic Area and the United Kingdom",
        body: [
          "Where consent is required for advertising or analytics cookies, it is requested before those cookies are set, and a visitor may change or withdraw that choice at any time.",
          "Visitors in these regions have the right to request access to their personal data, ask for its correction or erasure, object to or restrict processing, and lodge a complaint with their national data protection authority.",
          `Requests of this kind can be sent to ${CONTACT_EMAIL} and are answered within the period required by applicable law.`,
        ],
      },
      {
        heading: "Visitors in California",
        body: [
          "ExchangeHub does not sell personal information for money. Sharing data with advertising partners for personalised advertising may nonetheless count as a sale or share under California law.",
          `To opt out of that sharing, use the advertising controls linked above or send a Do Not Sell or Share My Personal Information request to ${CONTACT_EMAIL}. No visitor is treated differently for exercising this right.`,
        ],
      },
      {
        heading: "Children",
        body: [
          "This site is a general-audience currency reference and is not directed at children under 13. ExchangeHub does not knowingly collect personal information from children under 13; if such information is found to have been collected, it is deleted.",
        ],
      },
      {
        heading: "Changes and contact",
        body: [
          "This policy is updated when the site's data practices change, and the date of the most recent revision is shown on this page.",
          `For privacy requests or questions about this policy, contact ${CONTACT_EMAIL}.`,
        ],
      },
    ],
  },
  terms: {
    eyebrow: "Terms",
    title: "Terms of Use",
    description: "Terms of Use for ExchangeHub exchange-rate tools, charts, and informational content.",
    heading: "Terms of Use",
    sections: [
      {
        heading: "Informational use only",
        body: [
          "ExchangeHub provides exchange-rate tools, charts, and educational explanations for informational and comparison purposes only. The site does not provide financial, investment, tax, legal, banking, or remittance advice.",
          "You are responsible for verifying rates, fees, timing, and terms with your bank, broker, exchange, card provider, or money-transfer provider before making a transaction.",
        ],
      },
      {
        heading: "Data availability",
        body: [
          "Exchange-rate data may be delayed, unavailable, incomplete, or different from the rate offered by a specific provider. The site may change data sources, update schedules, supported currencies, or page features at any time.",
        ],
      },
      {
        heading: "Acceptable use",
        body: [
          "Do not overload, scrape aggressively, interfere with, reverse engineer, or misuse the service. Automated access should respect reasonable request rates and any published robots or API restrictions.",
        ],
      },
    ],
  },
  disclaimer: {
    eyebrow: "Disclaimer",
    title: "Exchange Rate Disclaimer",
    description: "Important disclaimer about exchange-rate data, charts, converters, and financial decisions.",
    heading: "Exchange Rate Disclaimer",
    sections: [
      {
        heading: "Rates are indicative only",
        body: [
          "The rates shown on ratehubfx.com are indicative mid-market reference rates for comparison. They are not guaranteed transaction rates, should not be treated as a binding quote, and nothing on this site is financial advice.",
          "Banks, remittance companies, card networks, brokers, and exchanges may use different bid/ask rates, spreads, fees, minimums, maximums, or settlement timing.",
        ],
      },
      {
        heading: "Data source",
        body: [
          "Rates come from [Open Exchange Rates](https://openexchangerates.org/) and are updated continuously, on the schedule set by the provider. A rate shown here may lag the market, and may be older if the source or this site is temporarily unavailable.",
          "Rates between two non-dollar currencies are calculated from each currency's US dollar rate. Every pair page shows the time of its last update, and the statistics cover the last 7 days of stored data only.",
        ],
      },
      {
        heading: "Charts explain movement, not outcomes",
        body: [
          "Charts and statistics help explain historical movement in the available data window. They do not predict future exchange rates and should not be used as the only basis for financial decisions.",
        ],
      },
      {
        heading: "Verify before acting",
        body: [
          "Before sending money, converting currency, booking travel, pricing invoices, or making business decisions, compare final quotes from regulated providers and consider all fees and terms.",
        ],
      },
    ],
  },
} satisfies Record<string, InfoPage>;

export type InfoSlug = keyof typeof INFO_PAGES;

// One list for the footer column and the bottom bar, in the order the old
// site's footer used.
export const INFO_LINKS: { label: string; href: string }[] = [
  { label: "About", href: "/about" },
  { label: "Contact", href: "/contact" },
  { label: "Privacy Policy", href: "/privacy-policy" },
  { label: "Terms of Use", href: "/terms" },
  { label: "Disclaimer", href: "/disclaimer" },
];
