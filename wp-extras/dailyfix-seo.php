<?php
/**
 * Plugin Name: DailyFix SEO Basics
 * Description: Adds a meta description and Open Graph / Twitter card tags (link previews for Threads, Pinterest, messengers). No external dependencies.
 * Version: 1.0
 *
 * Install as a must-use plugin: wp-content/mu-plugins/dailyfix-seo.php
 */

if (!defined('ABSPATH')) {
    exit;
}

function dailyfix_seo_clean($text) {
    $text = wp_strip_all_tags((string) $text);
    $text = html_entity_decode($text, ENT_QUOTES, 'UTF-8');
    return trim(preg_replace('/\s+/u', ' ', $text));
}

function dailyfix_seo_first_paragraph($html) {
    if (preg_match_all('/<p[^>]*>(.*?)<\/p>/is', (string) $html, $matches)) {
        foreach ($matches[1] as $candidate) {
            $clean = dailyfix_seo_clean($candidate);
            if (mb_strlen($clean) >= 60) {
                return $clean;
            }
        }
    }
    return '';
}

function dailyfix_seo_trim($text, $limit = 150) {
    if (mb_strlen($text) <= $limit) {
        return $text;
    }
    return mb_substr($text, 0, $limit - 1) . '…';
}

add_action('wp_head', function () {
    if (is_admin() || is_feed() || is_404()) {
        return;
    }

    $site_name = get_bloginfo('name');
    $title = wp_get_document_title();
    $description = '';
    $image = '';
    $url = home_url('/');
    $type = 'website';

    if (is_singular()) {
        $post = get_queried_object();
        if (!($post instanceof WP_Post)) {
            return;
        }
        $url = get_permalink($post);
        $type = is_singular('post') ? 'article' : 'website';
        if (has_excerpt($post)) {
            $description = dailyfix_seo_clean(get_the_excerpt($post));
        }
        if ($description === '') {
            $description = dailyfix_seo_first_paragraph($post->post_content);
        }
        $thumb = get_the_post_thumbnail_url($post, 'large');
        if ($thumb) {
            $image = $thumb;
        } elseif (preg_match('/<img[^>]+src=["\']([^"\']+)["\']/i', $post->post_content, $m)) {
            $image = $m[1];
        }
    }

    if ($description === '') {
        $description = dailyfix_seo_clean(get_bloginfo('description'));
    }
    $description = dailyfix_seo_trim($description);

    if ($description !== '') {
        echo '<meta name="description" content="' . esc_attr($description) . '">' . "\n";
    }
    echo '<meta property="og:locale" content="ko_KR">' . "\n";
    echo '<meta property="og:type" content="' . esc_attr($type) . '">' . "\n";
    echo '<meta property="og:site_name" content="' . esc_attr($site_name) . '">' . "\n";
    echo '<meta property="og:title" content="' . esc_attr($title) . '">' . "\n";
    echo '<meta property="og:url" content="' . esc_url($url) . '">' . "\n";
    if ($description !== '') {
        echo '<meta property="og:description" content="' . esc_attr($description) . '">' . "\n";
    }
    if ($image !== '') {
        echo '<meta property="og:image" content="' . esc_url($image) . '">' . "\n";
        echo '<meta name="twitter:card" content="summary_large_image">' . "\n";
    } else {
        echo '<meta name="twitter:card" content="summary">' . "\n";
    }
}, 5);
