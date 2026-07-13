<?php
/**
 * Plugin Name: RateHubFX Exchange Rates
 * Plugin URI: https://www.ratehubfx.com/
 * Description: Display exchange-rate converters, charts, tables, and SEO-friendly currency-pair pages from RateHubFX data files.
 * Version: 1.0.0
 * Requires at least: 5.8
 * Requires PHP: 7.4
 * Author: RateHubFX
 * Author URI: https://www.ratehubfx.com/
 * License: GPLv2 or later
 * License URI: https://www.gnu.org/licenses/gpl-2.0.html
 * Text Domain: ratehubfx-exchange-rates
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

require_once __DIR__ . '/includes/exchange-rate-core.php';

class RateHubFX_Exchange_Rates {
    const VERSION = '1.0.0';
    const OPTION_NAME = 'ratehubfx_exchange_settings';
    const SHORTCODES = [
        'exchange_rates_tabs',
        'exchange_rate_pair',
        'exchange_rate_chart',
    ];

    public function __construct() {
        add_action( 'init', [ $this, 'register_post_type' ] );
        add_action( 'init', [ $this, 'register_rewrites' ] );
        add_action( 'wp_enqueue_scripts', [ $this, 'enqueue_assets' ] );
        add_action( 'admin_menu', [ $this, 'admin_menu' ] );
        add_action( 'admin_init', [ $this, 'register_settings' ] );
        add_filter( 'query_vars', [ $this, 'query_vars' ] );
        add_filter( 'document_title_parts', [ $this, 'document_title_parts' ] );
        add_filter( 'plugin_action_links_' . plugin_basename( __FILE__ ), [ $this, 'plugin_action_links' ] );
        add_action( 'wp_head', [ $this, 'seo_head' ] );
        add_action( 'template_redirect', [ $this, 'render_virtual_pair_page' ] );
        add_shortcode( 'exchange_rates_tabs', [ $this, 'shortcode_tabs' ] );
        add_shortcode( 'exchange_rate_pair', [ $this, 'shortcode_pair' ] );
        add_shortcode( 'exchange_rate_chart', [ $this, 'shortcode_chart' ] );
    }

    public static function default_settings() {
        return [
            'rates_base_url' => '',
            'show_attribution' => '1',
        ];
    }

    public function settings() {
        $settings = get_option( self::OPTION_NAME, [] );
        return wp_parse_args( is_array( $settings ) ? $settings : [], self::default_settings() );
    }

    public function admin_menu() {
        add_options_page(
            __( 'RateHubFX Exchange Rates', 'ratehubfx-exchange-rates' ),
            __( 'RateHubFX Rates', 'ratehubfx-exchange-rates' ),
            'manage_options',
            'ratehubfx-exchange-rates',
            [ $this, 'render_settings_page' ]
        );
    }

    public function register_settings() {
        register_setting(
            'ratehubfx_exchange_rates',
            self::OPTION_NAME,
            [ $this, 'sanitize_settings' ]
        );
    }

    public function sanitize_settings( $input ) {
        $input = is_array( $input ) ? $input : [];
        $settings = self::default_settings();
        $settings['rates_base_url'] = isset( $input['rates_base_url'] )
            ? untrailingslashit( esc_url_raw( trim( wp_unslash( $input['rates_base_url'] ) ) ) )
            : '';
        $settings['show_attribution'] = empty( $input['show_attribution'] ) ? '0' : '1';
        return $settings;
    }

    public function render_settings_page() {
        $settings = $this->settings();
        $uploads = wp_get_upload_dir();
        $default_url = trailingslashit( $uploads['baseurl'] ) . 'rates';
        ?>
        <div class="wrap">
            <h1><?php esc_html_e( 'RateHubFX Exchange Rates', 'ratehubfx-exchange-rates' ); ?></h1>
            <p><?php esc_html_e( 'Configure where the plugin reads exchange-rate JSON files and how public widgets are attributed.', 'ratehubfx-exchange-rates' ); ?></p>
            <form method="post" action="options.php">
                <?php settings_fields( 'ratehubfx_exchange_rates' ); ?>
                <table class="form-table" role="presentation">
                    <tr>
                        <th scope="row"><label for="ratehubfx-rates-base-url"><?php esc_html_e( 'Rates base URL', 'ratehubfx-exchange-rates' ); ?></label></th>
                        <td>
                            <input id="ratehubfx-rates-base-url" class="regular-text code" type="url" name="<?php echo esc_attr( self::OPTION_NAME ); ?>[rates_base_url]" value="<?php echo esc_attr( $settings['rates_base_url'] ); ?>" placeholder="<?php echo esc_attr( $default_url ); ?>">
                            <p class="description"><?php esc_html_e( 'Leave empty to use wp-content/uploads/rates. The URL should contain index.json and per-pair JSON files.', 'ratehubfx-exchange-rates' ); ?></p>
                        </td>
                    </tr>
                    <tr>
                        <th scope="row"><?php esc_html_e( 'Attribution', 'ratehubfx-exchange-rates' ); ?></th>
                        <td>
                            <label>
                                <input type="checkbox" name="<?php echo esc_attr( self::OPTION_NAME ); ?>[show_attribution]" value="1" <?php checked( $settings['show_attribution'], '1' ); ?>>
                                <?php esc_html_e( 'Show a small "Rates by RateHubFX" link below widgets.', 'ratehubfx-exchange-rates' ); ?>
                            </label>
                        </td>
                    </tr>
                </table>
                <?php submit_button(); ?>
            </form>
        </div>
        <?php
    }

    public function plugin_action_links( $links ) {
        $settings_link = '<a href="' . esc_url( admin_url( 'options-general.php?page=ratehubfx-exchange-rates' ) ) . '">' . esc_html__( 'Settings', 'ratehubfx-exchange-rates' ) . '</a>';
        array_unshift( $links, $settings_link );
        return $links;
    }

    public function register_post_type() {
        $labels = [
            'name' => __( 'Exchange Pages', 'ratehubfx-exchange-rates' ),
            'singular_name' => __( 'Exchange Page', 'ratehubfx-exchange-rates' ),
            'add_new_item' => __( 'Add Exchange Page', 'ratehubfx-exchange-rates' ),
            'edit_item' => __( 'Edit Exchange Page', 'ratehubfx-exchange-rates' ),
        ];
        register_post_type( 'ratehubfx_exchange_page', [
            'labels' => $labels,
            'public' => true,
            'has_archive' => false,
            'show_in_rest' => true,
            'rewrite' => ['slug' => 'exchange'],
            'supports' => ['title','editor','thumbnail'],
        ] );
    }

    public function register_rewrites() {
        add_rewrite_rule( '^([a-z]{3})-([a-z]{3})/?$', 'index.php?exchange_pair=$matches[1]-$matches[2]', 'top' );
        add_rewrite_rule( '^exchange/([a-z]{3})-([a-z]{3})/?$', 'index.php?exchange_pair=$matches[1]-$matches[2]&exchange_legacy=1', 'top' );
    }

    public function query_vars( $vars ) {
        $vars[] = 'exchange_pair';
        $vars[] = 'exchange_legacy';
        return $vars;
    }

    public function enqueue_assets() {
        $base = plugin_dir_url( __FILE__ );
        wp_register_style( 'ratehubfx-exchange-style', $base . 'assets/exchange-style.css', [], self::VERSION );
        wp_register_script( 'ratehubfx-chartjs', 'https://cdn.jsdelivr.net/npm/chart.js@4.4.9/dist/chart.umd.min.js', [], '4.4.9', true );
        wp_register_script( 'ratehubfx-exchange-tabs', $base . 'assets/exchange-tabs.js', [ 'ratehubfx-chartjs' ], self::VERSION, true );

        if ( ! $this->should_enqueue_assets() ) {
            return;
        }

        wp_enqueue_style( 'ratehubfx-exchange-style' );
        wp_enqueue_script( 'ratehubfx-exchange-tabs' );
    }

    private function should_enqueue_assets() {
        if ( get_query_var( 'exchange_pair' ) ) {
            return true;
        }

        if ( ! is_singular() ) {
            return false;
        }

        $post = get_post();
        if ( ! $post || empty( $post->post_content ) ) {
            return false;
        }

        foreach ( self::SHORTCODES as $shortcode ) {
            if ( has_shortcode( $post->post_content, $shortcode ) ) {
                return true;
            }
        }

        return false;
    }

    private function get_pair_from_query() {
        $pair = get_query_var( 'exchange_pair' );
        if ( ! $pair || ! preg_match( '/^([a-z]{3})-([a-z]{3})$/', strtolower( $pair ), $matches ) ) {
            return null;
        }
        return [ strtoupper( $matches[1] ), strtoupper( $matches[2] ) ];
    }

    private function uploads_basedir() {
        $uploads = wp_get_upload_dir();
        return $uploads['basedir'];
    }

    private function rates_base_url() {
        $settings = $this->settings();
        if ( ! empty( $settings['rates_base_url'] ) ) {
            return untrailingslashit( $settings['rates_base_url'] );
        }
        $uploads = wp_get_upload_dir();
        return untrailingslashit( trailingslashit( $uploads['baseurl'] ) . 'rates' );
    }

    private function rates_index_url() {
        return trailingslashit( $this->rates_base_url() ) . 'index.json';
    }

    private function render_attribution() {
        $settings = $this->settings();
        if ( '1' !== $settings['show_attribution'] ) {
            return '';
        }
        return '<p class="ratehubfx-attribution">Rates by <a href="https://www.ratehubfx.com/" rel="nofollow noopener" target="_blank">RateHubFX</a></p>';
    }

    private function pair_model_from_query() {
        $pair = $this->get_pair_from_query();
        if ( ! $pair ) {
            return null;
        }
        return Exchange_Rate_Core::build_model( $this->uploads_basedir(), $pair[0], $pair[1] );
    }

    public function document_title_parts( $parts ) {
        $model = $this->pair_model_from_query();
        if ( ! $model ) {
            return $parts;
        }
        $parts['title'] = $model['base'] . ' to ' . $model['target'] . ' Exchange Rate Today';
        return $parts;
    }

    public function seo_head() {
        $model = $this->pair_model_from_query();
        if ( ! $model ) {
            return;
        }

        $base = esc_attr( $model['base'] );
        $target = esc_attr( $model['target'] );
        $rate = $model['latest'] ? Exchange_Rate_Core::format_rate( $model['latest']['rate'] ) : '';
        $description = $rate
            ? "Live {$base} to {$target} exchange rate, converter, chart, statistics, and common conversion amounts. Latest: 1 {$base} = {$rate} {$target}."
            : "Live {$base} to {$target} exchange rate, converter, chart, statistics, and common conversion amounts.";
        $url = Exchange_Rate_Core::pair_url( $base, $target );

        echo '<meta name="description" content="' . esc_attr( $description ) . '">' . "\n";
        echo '<link rel="canonical" href="' . esc_url( $url ) . '">' . "\n";
        echo '<meta name="robots" content="index,follow,max-snippet:-1,max-image-preview:large,max-video-preview:-1">' . "\n";
        echo '<meta property="og:type" content="website">' . "\n";
        echo '<meta property="og:site_name" content="ExchangeHub">' . "\n";
        echo '<meta property="og:title" content="' . esc_attr( $base . ' to ' . $target . ' Exchange Rate Today' ) . '">' . "\n";
        echo '<meta property="og:description" content="' . esc_attr( $description ) . '">' . "\n";
        echo '<meta property="og:url" content="' . esc_url( $url ) . '">' . "\n";
        echo '<meta name="twitter:card" content="summary">' . "\n";
        echo '<meta name="twitter:title" content="' . esc_attr( $base . ' to ' . $target . ' Exchange Rate Today' ) . '">' . "\n";
        echo '<meta name="twitter:description" content="' . esc_attr( $description ) . '">' . "\n";
        echo '<script type="application/ld+json">' . wp_json_encode( Exchange_Rate_Core::json_ld( $model, $url ) ) . '</script>' . "\n";
    }

    public function render_virtual_pair_page() {
        $model = $this->pair_model_from_query();
        if ( ! $model ) {
            return;
        }

        $canonical_url = Exchange_Rate_Core::pair_url( $model['base'], $model['target'] );
        $request_path = isset( $_SERVER['REQUEST_URI'] ) ? strtok( sanitize_text_field( wp_unslash( $_SERVER['REQUEST_URI'] ) ), '?' ) : '';
        if ( get_query_var( 'exchange_legacy' ) || '/' === substr( $request_path, -1 ) ) {
            wp_redirect( $canonical_url, 301 );
            exit;
        }

        status_header( 200 );
        get_header();
        echo '<main id="primary" class="site-main exchange-page-shell">';
        echo Exchange_Rate_Core::render_pair_page( $model );
        echo '</main>';
        get_footer();
        exit;
    }

    public function shortcode_tabs($atts) {
        $atts = shortcode_atts(
            [
                'index_url' => '',
            ],
            $atts,
            'exchange_rates_tabs'
        );
        $index_url = $atts['index_url'] ? esc_url_raw( $atts['index_url'] ) : $this->rates_index_url();

        ob_start();
        ?>
        <div class="exchange-tabs" data-rates-index="<?php echo esc_attr($index_url); ?>">
            <div class="tabs-list"></div>
            <div class="tabs-content">
                <canvas class="exchange-chart" width="800" height="300"></canvas>
                <div class="exchange-info"></div>
            </div>
        </div>
        <?php echo $this->render_attribution(); ?>
        <?php
        return ob_get_clean();
    }

    public function shortcode_pair($atts) {
        $atts = shortcode_atts(
            [
                'base' => 'VND',
                'target' => 'USD',
            ],
            $atts,
            'exchange_rate_pair'
        );
        $model = Exchange_Rate_Core::build_model( $this->uploads_basedir(), strtoupper( $atts['base'] ), strtoupper( $atts['target'] ) );
        return Exchange_Rate_Core::render_pair_page( $model ) . $this->render_attribution();
    }

    public function shortcode_chart($atts) {
        $atts = shortcode_atts(
            [
                'index_url' => '',
            ],
            $atts,
            'exchange_rate_chart'
        );
        $index_url = $atts['index_url'] ? esc_url_raw( $atts['index_url'] ) : $this->rates_index_url();

        ob_start();
        ?>
        <div class="exchange-control-chart" data-rates-index="<?php echo esc_attr($index_url); ?>">
            <div class="exchange-controls">
                <label>Base <select class="exchange-base"></select></label>
                <label>Target <select class="exchange-target"></select></label>
                <button type="button" class="exchange-load">Load</button>
            </div>
            <div class="exchange-status"></div>
            <canvas class="exchange-chart" width="900" height="360"></canvas>
        </div>
        <?php echo $this->render_attribution(); ?>
        <?php
        return ob_get_clean();
    }

    public static function activate() {
        $plugin = new self();
        $plugin->register_rewrites();
        flush_rewrite_rules();
    }

    public static function deactivate() {
        flush_rewrite_rules();
    }
}

register_activation_hook( __FILE__, [ 'RateHubFX_Exchange_Rates', 'activate' ] );
register_deactivation_hook( __FILE__, [ 'RateHubFX_Exchange_Rates', 'deactivate' ] );

new RateHubFX_Exchange_Rates();
