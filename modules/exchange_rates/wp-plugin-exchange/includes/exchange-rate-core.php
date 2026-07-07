<?php

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

class Exchange_Rate_Core {
    const MENU_GROUPS = [
        'USD' => [ 'VND', 'EUR', 'JPY', 'GBP', 'CNY', 'KRW', 'THB', 'SGD' ],
        'EUR' => [ 'USD', 'VND', 'GBP', 'JPY', 'CHF', 'CNY' ],
        'JPY' => [ 'USD', 'VND', 'EUR', 'KRW', 'CNY', 'THB' ],
        'GBP' => [ 'USD', 'EUR', 'VND', 'JPY', 'AUD', 'CAD' ],
        'CNY' => [ 'USD', 'VND', 'JPY', 'EUR', 'KRW', 'THB' ],
        'VND' => [ 'USD', 'EUR', 'JPY', 'KRW', 'THB', 'CNY' ],
    ];

    public static function pair_key( $base, $target ) {
        return strtolower( $base ) . '_' . strtolower( $target );
    }

    public static function format_rate( $value ) {
        $value = (float) $value;
        $abs = abs( $value );
        if ( 0.0 === $value ) {
            return '0';
        }
        if ( $abs < 0.000001 ) {
            return sprintf( '%.6E', $value );
        }
        if ( $abs < 1 ) {
            return rtrim( rtrim( number_format( $value, 8, '.', '' ), '0' ), '.' );
        }
        if ( $abs < 1000 ) {
            return rtrim( rtrim( number_format( $value, 6, '.', '' ), '0' ), '.' );
        }
        return number_format( $value, 2, '.', ',' );
    }

    public static function format_amount( $value ) {
        $value = (float) $value;
        if ( abs( $value ) >= 1000 ) {
            return number_format( $value, 2, '.', ',' );
        }
        return self::format_rate( $value );
    }

    public static function pair_url( $base, $target ) {
        return home_url( '/' . strtolower( $base ) . '-' . strtolower( $target ) );
    }

    public static function render_brand_logo() {
        ob_start();
        ?>
        <span class="exchange-brand-lockup" aria-label="ExchangeHub">
            <svg class="exchange-brand-mark" viewBox="0 0 40 40" role="img" aria-hidden="true" focusable="false">
                <rect x="2" y="2" width="36" height="36" rx="10" fill="#111827"/>
                <circle cx="20" cy="20" r="4.2" fill="#f0b90b"/>
                <circle cx="20" cy="8.5" r="3.2" fill="#f0b90b"/>
                <circle cx="31.5" cy="20" r="3.2" fill="#f0b90b"/>
                <circle cx="20" cy="31.5" r="3.2" fill="#f0b90b"/>
                <circle cx="8.5" cy="20" r="3.2" fill="#f0b90b"/>
                <path d="M14.2 15.2h9.4l-2.4-2.4 2-2 5.9 5.9-5.9 5.9-2-2 2.4-2.4h-9.4z" fill="#22c55e"/>
                <path d="M25.8 24.8h-9.4l2.4 2.4-2 2-5.9-5.9 5.9-5.9 2 2-2.4 2.4h9.4z" fill="#38bdf8"/>
            </svg>
            <span class="exchange-brand-name">ExchangeHub</span>
        </span>
        <?php
        return ob_get_clean();
    }

    public static function render_site_header( $active_base = null, $active_target = null ) {
        $active_base = $active_base ? strtoupper( $active_base ) : null;
        $active_target = $active_target ? strtoupper( $active_target ) : null;
        ob_start();
        ?>
        <header class="exchange-site-header">
            <nav class="exchange-site-nav">
                <a class="exchange-brand" href="<?php echo esc_url( home_url( '/' ) ); ?>"><?php echo self::render_brand_logo(); ?></a>
                <div class="exchange-header-pairs">
                    <?php if ( $active_base && isset( self::MENU_GROUPS[ $active_base ] ) ) : ?>
                        <span class="exchange-header-pairs-label"><?php echo esc_html( $active_base ); ?> pairs</span>
                        <?php foreach ( self::MENU_GROUPS[ $active_base ] as $target ) : ?>
                            <?php $is_active = $target === $active_target; ?>
                            <a class="<?php echo $is_active ? 'is-active' : ''; ?>" href="<?php echo esc_url( self::pair_url( $active_base, $target ) ); ?>" <?php echo $is_active ? 'aria-current="page"' : ''; ?>><?php echo esc_html( $active_base . '/' . $target ); ?></a>
                        <?php endforeach; ?>
                    <?php else : ?>
                        <?php foreach ( self::MENU_GROUPS as $base => $targets ) : ?>
                            <div class="exchange-header-pair-group">
                                <button type="button"><?php echo esc_html( $base ); ?></button>
                                <div class="exchange-header-pair-submenu">
                                    <?php foreach ( $targets as $target ) : ?>
                                        <a href="<?php echo esc_url( self::pair_url( $base, $target ) ); ?>"><?php echo esc_html( $base . '/' . $target ); ?></a>
                                    <?php endforeach; ?>
                                </div>
                            </div>
                        <?php endforeach; ?>
                    <?php endif; ?>
                </div>
                <div class="exchange-mega">
                    <button type="button">Currency pairs</button>
                    <div class="exchange-mega-panel">
                        <?php foreach ( self::MENU_GROUPS as $base => $targets ) : ?>
                            <div class="exchange-mega-group">
                                <h3><?php echo esc_html( $base ); ?> pairs</h3>
                                <?php foreach ( $targets as $target ) : ?>
                                    <a href="<?php echo esc_url( self::pair_url( $base, $target ) ); ?>"><?php echo esc_html( $base . '/' . $target ); ?></a>
                                <?php endforeach; ?>
                            </div>
                        <?php endforeach; ?>
                    </div>
                </div>
                <div class="exchange-translate-widget" aria-label="Translate page">
                    <button class="exchange-translate-toggle" type="button" aria-label="Translate page" aria-expanded="false">🌐</button>
                    <div class="exchange-translate-menu" role="menu">
                        <button class="exchange-translate-option" type="button" data-lang="en"><span class="exchange-translate-flag">🇺🇸</span><span>English</span></button>
                        <button class="exchange-translate-option" type="button" data-lang="vi"><span class="exchange-translate-flag">🇻🇳</span><span>Tiếng Việt</span></button>
                        <button class="exchange-translate-option" type="button" data-lang="th"><span class="exchange-translate-flag">🇹🇭</span><span>ไทย</span></button>
                        <button class="exchange-translate-option" type="button" data-lang="ja"><span class="exchange-translate-flag">🇯🇵</span><span>日本語</span></button>
                        <button class="exchange-translate-option" type="button" data-lang="ko"><span class="exchange-translate-flag">🇰🇷</span><span>한국어</span></button>
                        <button class="exchange-translate-option" type="button" data-lang="zh-CN"><span class="exchange-translate-flag">🇨🇳</span><span>中文</span></button>
                    </div>
                    <div id="google_translate_element" class="exchange-translate-native"></div>
                </div>
            </nav>
        </header>
        <?php
        return ob_get_clean();
    }

    public static function render_site_footer() {
        $links = [];
        foreach ( self::MENU_GROUPS as $base => $targets ) {
            foreach ( $targets as $target ) {
                $links[] = [ $base, $target ];
            }
        }
        $popular = array_slice( $links, 0, 12 );
        $cross = array_slice( $links, 12, 12 );
        $tools = [
            [ 'Exchange rates dashboard', home_url( '/' ) ],
            [ 'USD to VND', self::pair_url( 'USD', 'VND' ) ],
            [ 'VND to USD', self::pair_url( 'VND', 'USD' ) ],
            [ 'EUR to USD', self::pair_url( 'EUR', 'USD' ) ],
        ];
        ob_start();
        ?>
        <footer class="exchange-site-footer">
            <div class="exchange-footer-inner">
                <div class="exchange-footer-grid">
                    <div class="exchange-footer-brand">
                        <a class="exchange-footer-logo" href="<?php echo esc_url( home_url( '/' ) ); ?>"><?php echo self::render_brand_logo(); ?></a>
                        <p>Currency converters, pair charts, indexed dashboards, and exchange-rate explainers built for quick comparison and market context.</p>
                        <p class="exchange-footer-disclaimer">Rates are informational mid-market references. Banks, brokers, card networks, and transfer providers may apply spreads, fees, and settlement rules.</p>
                    </div>
                    <div class="exchange-footer-col">
                        <h2>Popular pairs</h2>
                        <div class="exchange-footer-links exchange-footer-pair-links">
                            <?php foreach ( $popular as $pair ) : ?>
                                <a href="<?php echo esc_url( self::pair_url( $pair[0], $pair[1] ) ); ?>"><?php echo esc_html( $pair[0] . ' to ' . $pair[1] ); ?></a>
                            <?php endforeach; ?>
                        </div>
                    </div>
                    <div class="exchange-footer-col">
                        <h2>Cross rates</h2>
                        <div class="exchange-footer-links exchange-footer-pair-links">
                            <?php foreach ( $cross as $pair ) : ?>
                                <a href="<?php echo esc_url( self::pair_url( $pair[0], $pair[1] ) ); ?>"><?php echo esc_html( $pair[0] . ' to ' . $pair[1] ); ?></a>
                            <?php endforeach; ?>
                        </div>
                    </div>
                    <div class="exchange-footer-col">
                        <h2>Tools</h2>
                        <div class="exchange-footer-links exchange-footer-tool-links">
                            <?php foreach ( $tools as $tool ) : ?>
                                <a href="<?php echo esc_url( $tool[1] ); ?>"><?php echo esc_html( $tool[0] ); ?></a>
                            <?php endforeach; ?>
                        </div>
                    </div>
                </div>
                <div class="exchange-footer-bottom">
                    <span>Built for exchange-rate comparison and reference.</span>
                    <span>Not financial advice.</span>
                </div>
            </div>
        </footer>
        <script>
            function setTranslateCookie(value) {
                var maxAge = value ? '; max-age=31536000' : '; expires=Thu, 01 Jan 1970 00:00:00 GMT';
                document.cookie = 'googtrans=' + (value || '') + '; path=/' + maxAge;
                if (location.hostname.indexOf('.') !== -1) {
                    document.cookie = 'googtrans=' + (value || '') + '; path=/; domain=.' + location.hostname + maxAge;
                }
            }
            function applyTranslation(lang) {
                var combo = document.querySelector('.goog-te-combo');
                if (lang === 'en') {
                    setTranslateCookie('');
                    location.reload();
                    return;
                }
                setTranslateCookie('/en/' + lang);
                if (combo) {
                    combo.value = lang;
                    combo.dispatchEvent(new Event('change'));
                } else {
                    location.reload();
                }
            }
            function initTranslateMenu() {
                document.querySelectorAll('.exchange-translate-widget').forEach(function(widget) {
                    if (widget.dataset.translateReady === '1') return;
                    widget.dataset.translateReady = '1';
                    var toggle = widget.querySelector('.exchange-translate-toggle');
                    toggle.addEventListener('click', function(event) {
                        event.stopPropagation();
                        var open = !widget.classList.contains('is-open');
                        document.querySelectorAll('.exchange-translate-widget.is-open').forEach(function(item) { item.classList.remove('is-open'); });
                        widget.classList.toggle('is-open', open);
                        toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
                    });
                    widget.querySelectorAll('[data-lang]').forEach(function(button) {
                        button.addEventListener('click', function() { applyTranslation(button.dataset.lang); });
                    });
                });
                document.addEventListener('click', function() {
                    document.querySelectorAll('.exchange-translate-widget.is-open').forEach(function(widget) {
                        widget.classList.remove('is-open');
                        var toggle = widget.querySelector('.exchange-translate-toggle');
                        if (toggle) toggle.setAttribute('aria-expanded', 'false');
                    });
                });
            }
            function googleTranslateElementInit() {
                new google.translate.TranslateElement({ pageLanguage: 'en', autoDisplay: false, layout: google.translate.TranslateElement.InlineLayout.HORIZONTAL }, 'google_translate_element');
                initTranslateMenu();
            }
            document.addEventListener('DOMContentLoaded', initTranslateMenu);
        </script>
        <script src="https://translate.google.com/translate_a/element.js?cb=googleTranslateElementInit"></script>
        <?php
        return ob_get_clean();
    }

    public static function load_json_file( $path ) {
        if ( ! file_exists( $path ) ) {
            return null;
        }
        $json = file_get_contents( $path );
        $data = json_decode( $json, true );
        return is_array( $data ) ? $data : null;
    }

    public static function load_index( $uploads_dir ) {
        $index = self::load_json_file( trailingslashit( $uploads_dir ) . 'rates/index.json' );
        return is_array( $index ) && isset( $index['pairs'] ) ? $index : [ 'pairs' => [] ];
    }

    public static function load_pair_entries( $uploads_dir, $base, $target ) {
        $path = trailingslashit( $uploads_dir ) . 'rates/' . self::pair_key( $base, $target ) . '.json';
        $data = self::load_json_file( $path );
        return is_array( $data ) ? $data : [];
    }

    public static function load_all_entries( $uploads_dir ) {
        $index = self::load_index( $uploads_dir );
        $entries = [];
        foreach ( $index['pairs'] as $pair ) {
            if ( empty( $pair['file'] ) ) {
                continue;
            }
            $data = self::load_json_file( trailingslashit( $uploads_dir ) . 'rates/' . basename( $pair['file'] ) );
            if ( is_array( $data ) ) {
                $entries = array_merge( $entries, $data );
            }
        }
        return $entries;
    }

    public static function add_entry_to_usd_table( &$table, $entry ) {
        if ( empty( $entry['base'] ) || empty( $entry['target'] ) || empty( $entry['rate'] ) ) {
            return;
        }
        $base = strtoupper( $entry['base'] );
        $target = strtoupper( $entry['target'] );
        $rate = (float) $entry['rate'];
        if ( 'USD' === $base ) {
            $table[ $target ] = $rate;
        } elseif ( 'USD' === $target && 0.0 !== $rate ) {
            $table[ $base ] = 1 / $rate;
        }
    }

    public static function derive_rate_from_usd_table( $base, $target, $table ) {
        $base = strtoupper( $base );
        $target = strtoupper( $target );
        $base_per_usd = 'USD' === $base ? 1.0 : ( $table[ $base ] ?? null );
        $target_per_usd = 'USD' === $target ? 1.0 : ( $table[ $target ] ?? null );
        if ( ! $base_per_usd || ! $target_per_usd ) {
            return null;
        }
        return (float) $target_per_usd / (float) $base_per_usd;
    }

    public static function derive_history( $uploads_dir, $base, $target ) {
        $base = strtoupper( $base );
        $target = strtoupper( $target );
        if ( $base === $target ) {
            return [
                [
                    'ts' => time(),
                    'base' => $base,
                    'target' => $target,
                    'rate' => 1.0,
                ],
            ];
        }

        $direct = self::load_pair_entries( $uploads_dir, $base, $target );
        if ( $direct ) {
            return $direct;
        }

        $by_ts = [];
        foreach ( self::load_all_entries( $uploads_dir ) as $entry ) {
            $ts = isset( $entry['ts'] ) ? (int) $entry['ts'] : 0;
            if ( ! isset( $by_ts[ $ts ] ) ) {
                $by_ts[ $ts ] = [];
            }
            self::add_entry_to_usd_table( $by_ts[ $ts ], $entry );
        }

        ksort( $by_ts );
        $history = [];
        foreach ( $by_ts as $ts => $table ) {
            $rate = self::derive_rate_from_usd_table( $base, $target, $table );
            if ( null !== $rate ) {
                $history[] = [
                    'ts' => $ts,
                    'base' => $base,
                    'target' => $target,
                    'rate' => $rate,
                ];
            }
        }
        return $history;
    }

    public static function build_model( $uploads_dir, $base, $target ) {
        $base = strtoupper( $base );
        $target = strtoupper( $target );
        $history = self::derive_history( $uploads_dir, $base, $target );
        $latest = $history ? end( $history ) : null;
        $rates = array_map(
            function ( $entry ) {
                return (float) $entry['rate'];
            },
            $history
        );

        $stats = null;
        if ( $rates ) {
            $first = $rates[0];
            $previous = count( $rates ) > 1 ? $rates[ count( $rates ) - 2 ] : $rates[0];
            $latest_rate = $rates[ count( $rates ) - 1 ];
            $change = $latest_rate - $first;
            $change_pct = $first ? ( $change / $first * 100 ) : 0;
            $previous_change = $latest_rate - $previous;
            $previous_change_pct = $previous ? ( $previous_change / $previous * 100 ) : 0;
            $direction = $change_pct > 0.01 ? 'up' : ( $change_pct < -0.01 ? 'down' : 'flat' );
            $avg = array_sum( $rates ) / count( $rates );
            $stats = [
                'points' => count( $rates ),
                'high' => max( $rates ),
                'low' => min( $rates ),
                'average' => $avg,
                'updated' => $latest ? (int) $latest['ts'] : null,
                'first' => $first,
                'change' => $change,
                'change_pct' => $change_pct,
                'previous_change' => $previous_change,
                'previous_change_pct' => $previous_change_pct,
                'direction' => $direction,
            ];
        }

        return [
            'base' => $base,
            'target' => $target,
            'history' => $history,
            'latest' => $latest,
            'stats' => $stats,
            'amounts' => [ 1, 5, 10, 25, 50, 100, 500, 1000, 5000, 10000 ],
            'reverse_rate' => $rates && end( $rates ) ? 1 / end( $rates ) : null,
        ];
    }

    public static function render_pair_page( $model ) {
        $base = esc_html( $model['base'] );
        $target = esc_html( $model['target'] );
        $latest = $model['latest'];
        $rate = $latest ? (float) $latest['rate'] : null;
        $updated = $latest ? gmdate( 'Y-m-d H:i \U\T\C', (int) $latest['ts'] ) : '';
        $title = "{$base} to {$target} Exchange Rate";
        $reverse_rate = $model['reverse_rate'];
        ob_start();
        ?>
        <?php echo self::render_site_header( $base, $target ); ?>
        <article class="exchange-pair-page">
            <header class="exchange-pair-header">
                <h1><?php echo esc_html( $title ); ?></h1>
                <?php if ( null !== $rate ) : ?>
                    <p class="exchange-rate-lede">1 <?php echo $base; ?> = <strong><?php echo esc_html( self::format_rate( $rate ) ); ?> <?php echo $target; ?></strong></p>
                    <p class="exchange-updated">Updated <?php echo esc_html( $updated ); ?>. Mid-market rate for informational use only.</p>
                <?php else : ?>
                    <p>Exchange rate data is not available yet.</p>
                <?php endif; ?>
            </header>

            <section class="exchange-converter">
                <h2><?php echo $base; ?> to <?php echo $target; ?> converter</h2>
                <?php if ( $updated ) : ?>
                    <p class="exchange-updated">Converter updated <?php echo esc_html( $updated ); ?>.</p>
                <?php endif; ?>
                <table>
                    <thead><tr><th><?php echo $base; ?></th><th><?php echo $target; ?></th></tr></thead>
                    <tbody>
                    <?php foreach ( $model['amounts'] as $amount ) : ?>
                        <tr>
                            <td><?php echo esc_html( number_format( $amount ) . ' ' . $base ); ?></td>
                            <td><?php echo esc_html( null === $rate ? '-' : self::format_amount( $amount * $rate ) . ' ' . $target ); ?></td>
                        </tr>
                    <?php endforeach; ?>
                    </tbody>
                </table>
            </section>

            <section class="exchange-chart-section">
                <h2><?php echo $base; ?> to <?php echo $target; ?> chart</h2>
                <div class="exchange-tabs exchange-single-chart" data-pair-history="<?php echo esc_attr( wp_json_encode( $model['history'] ) ); ?>">
                    <canvas class="exchange-chart" width="900" height="360"></canvas>
                </div>
            </section>

            <?php if ( $model['stats'] ) : ?>
                <section class="exchange-summary">
                    <h2><?php echo $base; ?> to <?php echo $target; ?> market summary</h2>
                    <p>
                        Over the available data window, <?php echo $base; ?> to <?php echo $target; ?> is
                        <?php echo 'up' === $model['stats']['direction'] ? 'higher' : ( 'down' === $model['stats']['direction'] ? 'lower' : 'mostly unchanged' ); ?>
                        by <?php echo esc_html( self::format_rate( $model['stats']['change'] ) ); ?> <?php echo $target; ?> per 1 <?php echo $base; ?>
                        (<?php echo esc_html( number_format( $model['stats']['change_pct'], 4 ) ); ?>%).
                        The latest move from the previous point is <?php echo esc_html( self::format_rate( $model['stats']['previous_change'] ) ); ?> <?php echo $target; ?>
                        (<?php echo esc_html( number_format( $model['stats']['previous_change_pct'], 4 ) ); ?>%).
                    </p>
                    <?php if ( $reverse_rate ) : ?>
                        <p>The reverse rate is 1 <?php echo $target; ?> = <?php echo esc_html( self::format_rate( $reverse_rate ) ); ?> <?php echo $base; ?>.</p>
                    <?php endif; ?>
                </section>

                <section class="exchange-stats">
                    <h2><?php echo $base; ?> to <?php echo $target; ?> statistics</h2>
                    <dl>
                        <dt>High</dt><dd><?php echo esc_html( self::format_rate( $model['stats']['high'] ) ); ?></dd>
                        <dt>Low</dt><dd><?php echo esc_html( self::format_rate( $model['stats']['low'] ) ); ?></dd>
                        <dt>Average</dt><dd><?php echo esc_html( self::format_rate( $model['stats']['average'] ) ); ?></dd>
                        <dt>Data points</dt><dd><?php echo esc_html( $model['stats']['points'] ); ?></dd>
                    </dl>
                </section>
            <?php endif; ?>

            <section class="exchange-reverse-converter">
                <h2><?php echo $target; ?> to <?php echo $base; ?> quick conversion</h2>
                <table>
                    <thead><tr><th><?php echo $target; ?></th><th><?php echo $base; ?></th></tr></thead>
                    <tbody>
                    <?php foreach ( $model['amounts'] as $amount ) : ?>
                        <tr>
                            <td><?php echo esc_html( number_format( $amount ) . ' ' . $target ); ?></td>
                            <td><?php echo esc_html( null === $reverse_rate ? '-' : self::format_amount( $amount * $reverse_rate ) . ' ' . $base ); ?></td>
                        </tr>
                    <?php endforeach; ?>
                    </tbody>
                </table>
            </section>

            <section class="exchange-explainer">
                <h2>How to read this <?php echo $base; ?> to <?php echo $target; ?> page</h2>
                <p>The converter uses the latest stored rate, while the chart shows how the rate has moved across the available update points. A rising <?php echo $base; ?> to <?php echo $target; ?> chart means 1 <?php echo $base; ?> buys more <?php echo $target; ?>. A falling chart means 1 <?php echo $base; ?> buys less <?php echo $target; ?>.</p>
                <p>For very small rates, such as VND pairs, the raw number may look flat even when small changes are present. In that case, compare the percentage change, high, low, and reverse rate to understand the move more clearly.</p>
            </section>

            <section class="exchange-faq">
                <h2><?php echo $base; ?> to <?php echo $target; ?> FAQ</h2>
                <h3>What is the <?php echo $base; ?> to <?php echo $target; ?> exchange rate today?</h3>
                <p><?php echo null === $rate ? 'The latest rate is not available yet.' : 'The latest rate is 1 ' . $base . ' = ' . esc_html( self::format_rate( $rate ) ) . ' ' . $target . '.'; ?></p>
                <h3>Is <?php echo $base; ?> stronger or weaker against <?php echo $target; ?>?</h3>
                <p><?php echo $model['stats'] ? 'Across the current data window, ' . $base . ' is ' . ( 'up' === $model['stats']['direction'] ? 'stronger' : ( 'down' === $model['stats']['direction'] ? 'weaker' : 'mostly stable' ) ) . ' against ' . $target . ', based on a ' . esc_html( number_format( $model['stats']['change_pct'], 4 ) ) . '% move.' : 'There is not enough history yet to describe the trend.'; ?></p>
                <h3>Why can small exchange rates look like zero?</h3>
                <p>Some currency pairs have very small decimal values. The page keeps extra decimal places in labels and tooltips so small rates remain readable instead of being rounded to zero.</p>
                <h3>How often is this exchange rate updated?</h3>
                <p>The rate files are refreshed by the configured fetcher schedule. This site is currently designed for frequent updates from the stored market data.</p>
                <h3>Can I use this rate for money transfers?</h3>
                <p>This page is for informational purposes only. Banks, brokers, and transfer providers may use different rates and fees.</p>
            </section>
        </article>
        <?php echo self::render_site_footer(); ?>
        <?php
        return ob_get_clean();
    }

    public static function json_ld( $model, $url ) {
        $base = $model['base'];
        $target = $model['target'];
        $rate = $model['latest'] ? self::format_rate( $model['latest']['rate'] ) : '';
        $title = "{$base} to {$target} Exchange Rate Today";
        $description = $rate
            ? "{$base} to {$target} exchange rate today with converter, chart, statistics, trend notes, and practical {$base}/{$target} context. Latest: 1 {$base} = {$rate} {$target}."
            : "{$base} to {$target} exchange rate today with converter, chart, statistics, trend notes, and practical {$base}/{$target} context.";
        $nav = [];
        foreach ( self::MENU_GROUPS as $nav_base => $targets ) {
            foreach ( $targets as $nav_target ) {
                $nav[] = [
                    '@type' => 'SiteNavigationElement',
                    'name' => $nav_base . '/' . $nav_target,
                    'url' => self::pair_url( $nav_base, $nav_target ),
                ];
            }
        }
        $faq = [
            [
                '@type' => 'Question',
                'name' => "What is the {$base} to {$target} exchange rate today?",
                'acceptedAnswer' => [
                    '@type' => 'Answer',
                    'text' => $rate ? "1 {$base} equals {$rate} {$target}." : 'The latest rate is not available yet.',
                ],
            ],
            [
                '@type' => 'Question',
                'name' => "Can I use this {$base} to {$target} rate for money transfers?",
                'acceptedAnswer' => [
                    '@type' => 'Answer',
                    'text' => 'This page is for informational comparison only. Providers may use different rates and fees.',
                ],
            ],
        ];
        return [
            '@context' => 'https://schema.org',
            '@graph' => array_merge(
                [
                    [
                        '@type' => 'Organization',
                        '@id' => home_url( '/#organization' ),
                        'name' => 'ExchangeHub',
                        'url' => home_url( '/' ),
                    ],
                    [
                        '@type' => 'WebSite',
                        '@id' => home_url( '/#website' ),
                        'name' => 'ExchangeHub',
                        'url' => home_url( '/' ),
                        'publisher' => [ '@id' => home_url( '/#organization' ) ],
                        'inLanguage' => 'en',
                    ],
                    [
                        '@type' => 'WebPage',
                        '@id' => $url . '#webpage',
                        'url' => $url,
                        'name' => $title,
                        'description' => $description,
                        'isPartOf' => [ '@id' => home_url( '/#website' ) ],
                        'breadcrumb' => [ '@id' => $url . '#breadcrumb' ],
                        'publisher' => [ '@id' => home_url( '/#organization' ) ],
                        'inLanguage' => 'en',
                    ],
                    [
                        '@type' => 'BreadcrumbList',
                        '@id' => $url . '#breadcrumb',
                        'itemListElement' => [
                            [ '@type' => 'ListItem', 'position' => 1, 'name' => 'Exchange Rates', 'item' => home_url( '/' ) ],
                            [ '@type' => 'ListItem', 'position' => 2, 'name' => "{$base} pairs", 'item' => $url ],
                            [ '@type' => 'ListItem', 'position' => 3, 'name' => "{$base} to {$target}" ],
                        ],
                    ],
                ],
                array_slice( $nav, 0, 36 ),
                [
                    [
                        '@type' => 'FAQPage',
                        '@id' => $url . '#faq',
                        'mainEntity' => $faq,
                    ],
                ]
            ),
        ];
    }
}
