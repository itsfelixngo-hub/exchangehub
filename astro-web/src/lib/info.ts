import "./env";

// Copy carried over verbatim from the Flask app's INFO_PAGES (app.py), so the
// two front ends say the same thing while both are live.
export const CONTACT_EMAIL = process.env.SITE_CONTACT_EMAIL ?? "contact@ratehubfx.com";

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
        heading: "Cookies and advertising",
        body: [
          "Advertising partners, including Google if enabled, may use cookies to serve ads based on a user's prior visits to this or other websites.",
          "Users can manage cookie preferences in their browser settings. If Google ads are used, users can also review Google's advertising controls and privacy settings.",
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
        heading: "Contact",
        body: [`For privacy requests, contact ${CONTACT_EMAIL}.`],
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
