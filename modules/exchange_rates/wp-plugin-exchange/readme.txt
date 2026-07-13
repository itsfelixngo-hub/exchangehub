=== RateHubFX Exchange Rates ===
Contributors: ratehubfx
Tags: exchange rates, currency converter, forex, currency chart, rates
Requires at least: 5.8
Tested up to: 6.6
Requires PHP: 7.4
Stable tag: 1.0.0
License: GPLv2 or later
License URI: https://www.gnu.org/licenses/gpl-2.0.html

Display currency converters, exchange-rate tables, charts, and SEO-friendly currency-pair pages from RateHubFX data files.

== Description ==

RateHubFX Exchange Rates adds lightweight currency widgets and virtual pair pages to WordPress. It is designed for finance blogs, travel sites, business sites, and international commerce content that need readable exchange-rate references.

The plugin reads JSON rate files from `wp-content/uploads/rates` by default, or from a custom rates base URL configured in Settings.

Features:

* Currency-pair converter shortcode.
* Interactive chart shortcode.
* Tabbed exchange-rate chart shortcode.
* Virtual SEO pages such as `/usd-vnd` and `/eur-usd`.
* Canonical URL, meta description, Open Graph tags, and JSON-LD on virtual pair pages.
* Conditional asset loading so Chart.js is loaded only on pages that use the plugin.
* Optional RateHubFX attribution link.

== Installation ==

1. Upload the `wp-plugin-exchange` folder to `/wp-content/plugins/`.
2. Activate "RateHubFX Exchange Rates" from the Plugins screen.
3. Go to Settings > RateHubFX Rates and confirm the rates base URL.
4. Make sure the rates directory contains `index.json` and per-pair files such as `usd_vnd.json`.
5. Add a shortcode to a page or visit a virtual pair URL such as `/usd-vnd`.

== Shortcodes ==

`[exchange_rates_tabs]`

Displays a tabbed chart using the configured rates index.

`[exchange_rate_pair base="USD" target="VND"]`

Renders an SEO-friendly converter, chart, statistics, and FAQ block for one pair.

`[exchange_rate_chart]`

Displays a selectable chart widget.

Each chart shortcode can override the rates index:

`[exchange_rate_chart index_url="https://example.com/rates/index.json"]`

== Frequently Asked Questions ==

= Where should the JSON files live? =

By default the plugin reads from `wp-content/uploads/rates/index.json` and matching pair files listed inside that index. You can override the public base URL from Settings > RateHubFX Rates.

= Does this plugin provide financial advice? =

No. The plugin displays informational exchange-rate data only. Banks, brokers, card networks, and transfer providers may apply spreads, fees, and settlement rules.

= Does Chart.js load on every page? =

No. Assets are loaded only on virtual pair pages or singular pages that contain one of the plugin shortcodes.

== Changelog ==

= 1.0.0 =

* Initial store-ready release.
* Added shortcode widgets, virtual pair pages, SEO metadata, settings page, and conditional asset loading.
