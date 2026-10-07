/// Agency landing pages are not dated articles, even when a feed timestamps them.
pub fn is_agency_homepage(link: &str, homepage: &str) -> bool {
    let Ok(parsed) = url::Url::parse(link) else {
        return false;
    };
    let host = parsed.host_str().unwrap_or("").trim_start_matches("www.");
    let path = parsed.path().trim_end_matches('/');
    let parts = path.trim_matches('/').split('/').collect::<Vec<_>>();
    if host == "gov.uk" && parts.len() == 3 && parts[..2] == ["government", "organisations"] {
        return true;
    }
    url::Url::parse(homepage).is_ok_and(|home| {
        !host.is_empty()
            && host == home.host_str().unwrap_or("").trim_start_matches("www.")
            && path == home.path().trim_end_matches('/')
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn excludes_landing_pages_but_preserves_articles() {
        assert!(is_agency_homepage(
            "https://www.gov.uk/government/organisations/bist/?utm_source=rss#top",
            ""
        ));
        assert!(is_agency_homepage(
            "https://official.example/?utm_source=rss",
            "https://www.official.example"
        ));
        assert!(!is_agency_homepage(
            "https://www.gov.uk/government/organisations/bist/about/research",
            ""
        ));
        assert!(!is_agency_homepage(
            "https://www.gov.uk/government/news/ai-policy",
            ""
        ));
        assert!(!is_agency_homepage(
            "https://other.example/government/organisations/bist",
            ""
        ));
    }
}
