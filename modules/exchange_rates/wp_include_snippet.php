<?php
// WP theme snippet: include the pre-rendered rates partial if present.
// Place this in your theme where you want the rates to appear.

$uploads = wp_get_upload_dir();
$path = $uploads['basedir'] . '/rates.html';
if ( file_exists( $path ) ) {
    // Output raw HTML (already rendered). Ensure it's trusted content.
    echo file_get_contents( $path );
} else {
    echo '<p>Exchange rates are not available.</p>';
}

?>
