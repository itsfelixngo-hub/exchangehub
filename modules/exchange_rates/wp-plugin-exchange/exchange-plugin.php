<?php
/**
 * Plugin Name: Exchange Rates Tabs
 * Description: Display exchange rate tabs on homepage and provide custom pages for each currency pair.
 * Version: 0.1
 * Author: Auto-generated
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

require_once __DIR__ . '/includes/exchange-rate-core.php';

class Exchange_Rates_Tabs {
    public function __construct() {
        add_action( 'init', [ $this, 'register_post_type' ] );
        add_action( 'init', [ $this, 'register_rewrites' ] );
        add_action( 'wp_enqueue_scripts', [ $this, 'enqueue_assets' ] );
        add_filter( 'query_vars', [ $this, 'query_vars' ] );
        add_filter( 'document_title_parts', [ $this, 'document_title_parts' ] );
        add_action( 'wp_head', [ $this, 'seo_head' ] );
        add_action( 'template_redirect', [ $this, 'render_virtual_pair_page' ] );
        add_shortcode( 'exchange_rates_tabs', [ $this, 'shortcode_tabs' ] );
        add_shortcode( 'exchange_rate_pair', [ $this, 'shortcode_pair' ] );
        add_shortcode( 'exchange_rate_chart', [ $this, 'shortcode_chart' ] );
    }

    public function register_post_type() {
        $labels = [
            'name' => 'Exchange Pages',
            'singular_name' => 'Exchange Page',
            'add_new_item' => 'Add Exchange Page',
            'edit_item' => 'Edit Exchange Page',
        ];
        register_post_type( 'exchange_page', [
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
        // plugin assets
        $base = plugin_dir_url(__FILE__);
        wp_register_style('exchange-style', $base . 'assets/exchange-style.css');
        wp_register_script('chartjs', 'https://cdn.jsdelivr.net/npm/chart.js', [], null, true);
        wp_register_script('exchange-tabs', $base . 'assets/exchange-tabs.js', ['chartjs','jquery'], null, true );
        wp_enqueue_style('exchange-style');
        wp_enqueue_script('exchange-tabs');
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
        $uploads = wp_get_upload_dir();
        $index_url = $uploads['baseurl'] . '/rates/index.json';

        ob_start();
        ?>
        <div class="exchange-tabs" data-rates-index="<?php echo esc_attr($index_url); ?>">
            <div class="tabs-list"></div>
            <div class="tabs-content">
                <canvas class="exchange-chart" width="800" height="300"></canvas>
                <div class="exchange-info"></div>
            </div>
        </div>
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
        return Exchange_Rate_Core::render_pair_page( $model );
    }

    public function shortcode_chart($atts) {
        $uploads = wp_get_upload_dir();
        $index_url = $uploads['baseurl'] . '/rates/index.json';

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

register_activation_hook( __FILE__, [ 'Exchange_Rates_Tabs', 'activate' ] );
register_deactivation_hook( __FILE__, [ 'Exchange_Rates_Tabs', 'deactivate' ] );

new Exchange_Rates_Tabs();
