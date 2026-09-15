use uk_news_core::{load_organisation_registry, Agency, OrganisationRegistry};

pub fn organisation_registry() -> OrganisationRegistry {
    load_organisation_registry()
}
pub fn agencies() -> Vec<Agency> {
    organisation_registry().agencies()
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn registry_contains_split_dsit_successors() {
        let values = agencies();
        assert_eq!(values.len(), 14);
        assert!(values.iter().any(|agency| agency.short_name == "BIST"));
        assert!(values
            .iter()
            .any(|agency| agency.short_name == "DSIT Transition"));
        assert!(values
            .iter()
            .all(|agency| agency.homepage.starts_with("https://")));
    }
}
