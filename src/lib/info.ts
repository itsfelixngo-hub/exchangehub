import "./env";

// Copy carried over verbatim from the Flask app's INFO_PAGES (app.py), so the
// two front ends say the same thing while both are live.
export const CONTACT_EMAIL = process.env.SITE_CONTACT_EMAIL ?? "contact@ratehubfx.com";

/**
 * The day the copy below last changed, as `sitemap.xml` reports it for the
 * info pages. Bump it when you edit INFO_PAGES — a wrong date here is better
 * than the old behaviour, which stamped today onto every URL on every crawl
 * and taught Google to ignore this site's lastmod entirely.
 */
export const INFO_CONTENT_LAST_MODIFIED = "2026-09-13";

export type InfoSection = { heading: string; body: string[] };

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
    title: "About ExchangeHub",
    description: "Learn how ExchangeHub builds currency converters, exchange-rate charts, indexed dashboards, and educational exchange-rate explainers.",
    heading: "About ExchangeHub",
    sections: [
      {
        heading: "What this site does",
        body: [
          "ExchangeHub is a currency reference site built around practical tools: exchange-rate converters, pair pages, comparison tables, raw rate charts, and indexed dashboards.",
          "The goal is to make exchange-rate movement easier to read. A pair page shows the actual rate for one currency pair, while the dashboard uses a base-100 index so many currencies can be compared on the same scale.",
        ],
      },
      {
        heading: "How we add value",
        body: [
          "Raw exchange rates can be hard to compare because each pair has a different scale. VND pairs may use very large numbers while EUR or GBP pairs may be below 2. ExchangeHub explains both the raw rate and the relative movement behind it.",
          "Each supported pair can include latest conversion tables, high-low-average statistics, reverse rates, trend context, and plain-language explanations for non-specialist readers.",
        ],
      },
      {
        heading: "Data and accuracy",
        body: [
          "Rates are collected on a configured schedule and stored locally before being shown on the site. Pages include update timestamps so readers can understand when the displayed data was last refreshed.",
          "Exchange rates are provided for informational reference only. Actual rates from banks, brokers, card networks, exchanges, and remittance providers may include spreads, fees, timing differences, and rounding rules.",
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
        heading: "Rates are not transaction quotes",
        body: [
          "The rates shown on ExchangeHub are reference rates for comparison. They are not guaranteed transaction rates and should not be treated as a binding quote.",
          "Banks, remittance companies, card networks, brokers, and exchanges may use different bid/ask rates, spreads, fees, minimums, maximums, or settlement timing.",
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
