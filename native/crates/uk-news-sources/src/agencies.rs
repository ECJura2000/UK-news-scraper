use uk_news_core::Agency;

fn gov(name_zh: &str, name_en: &str, short: &str, slug: &str, topics: &[&str]) -> Agency {
    let home = format!("https://www.gov.uk/government/organisations/{slug}");
    Agency {
        name_zh: name_zh.into(),
        name_en: name_en.into(),
        short_name: short.into(),
        homepage: home.clone(),
        feeds: vec![format!("{home}.atom")],
        news_pages: vec![],
        topics: topics.iter().map(|x| (*x).into()).collect(),
        link_include_patterns: vec![
            "/government/news/",
            "/guidance/",
            "/government/publications/",
            "/government/consultations/",
            "/government/research/",
            "/government/statistics/",
        ]
        .into_iter()
        .map(Into::into)
        .collect(),
        official_pages: vec![home],
    }
}

pub fn agencies() -> Vec<Agency> {
    vec![
    gov("商業、創新、科學及貿易部","Department for Business, Innovation, Science and Trade","BIST","department-for-business-innovation-science-and-trade",&["Science & Technology","AI","半導體/量子技術"]),
    gov("數位、文化、媒體及體育部","Department for Digital, Culture, Media and Sport","DCMS","department-for-culture-media-and-sport",&["資料治理/隱私/數位身份","數位平台","網路安全/資安"]),
    gov("人工智慧安全研究所","AI Security Institute","AISI","ai-safety-institute",&["AI"]),
    Agency{name_zh:"英國資訊專員辦公室".into(),name_en:"Information Commissioner's Office".into(),short_name:"ICO".into(),homepage:"https://ico.org.uk/about-the-ico/media-centre/news-and-blogs/".into(),feeds:vec![],news_pages:vec!["https://ico.org.uk/about-the-ico/media-centre/news-and-blogs/".into()],topics:vec!["AI".into(),"資料治理/隱私/數位身份".into()],link_include_patterns:vec![],official_pages:vec!["https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/".into()]},
    gov("競爭與市場管理局","Competition and Markets Authority","CMA","competition-and-markets-authority",&["AI","數位平台"]),
    gov("英國智財局","UK Intellectual Property Office","UK IPO","intellectual-property-office",&["AI"]),
    gov("政府數位服務團隊","Government Digital Service","GDS","government-digital-service",&["AI","資料治理/隱私/數位身份"]),
    Agency{name_zh:"英國通訊管理局".into(),name_en:"Office of Communications".into(),short_name:"Ofcom".into(),homepage:"https://www.ofcom.org.uk/".into(),feeds:vec!["https://www.ofcom.org.uk/news-centre/rss".into()],news_pages:vec!["https://www.ofcom.org.uk/news-and-updates".into()],topics:vec!["數位平台".into()],link_include_patterns:vec![],official_pages:vec!["https://www.ofcom.org.uk/news-and-updates".into()]},
    Agency{name_zh:"國家網路安全中心".into(),name_en:"National Cyber Security Centre".into(),short_name:"NCSC".into(),homepage:"https://www.ncsc.gov.uk/".into(),feeds:vec!["https://www.ncsc.gov.uk/api/1/services/v1/all-rss-feed.xml".into()],news_pages:vec![],topics:vec!["數位平台".into(),"網路安全/資安".into()],link_include_patterns:vec![],official_pages:vec!["https://www.ncsc.gov.uk/collection/what-to-do-when-cyber-attacks-disrupt-your-organisation","https://www.ncsc.gov.uk/collection/what-to-do-when-cyber-attacks-disrupt-your-organisation/recovering","https://www.ncsc.gov.uk/collection/what-to-do-when-cyber-attacks-disrupt-your-organisation/recovering/immediate-activities","https://www.ncsc.gov.uk/collection/what-to-do-when-cyber-attacks-disrupt-your-organisation/recovering/recovering-ongoing-investigations","https://www.ncsc.gov.uk/collection/what-to-do-when-cyber-attacks-disrupt-your-organisation/recovering/rebuild"].into_iter().map(Into::into).collect()},
    Agency{name_zh:"英國選舉委員會".into(),name_en:"Electoral Commission".into(),short_name:"Electoral Commission".into(),homepage:"https://www.electoralcommission.org.uk/".into(),feeds:vec![],news_pages:vec!["https://www.electoralcommission.org.uk/news-and-views/media-centre".into()],topics:vec!["數位平台".into()],link_include_patterns:vec![],official_pages:vec!["https://www.electoralcommission.org.uk/news-and-views/media-centre".into()]},
    gov("英國內閣辦公室","Cabinet Office","Cabinet Office","cabinet-office",&["AI","網路安全/資安"]),
    Agency{name_zh:"國家保護安全局".into(),name_en:"National Protective Security Authority".into(),short_name:"NPSA".into(),homepage:"https://www.npsa.gov.uk/".into(),feeds:vec![],news_pages:vec!["https://www.npsa.gov.uk/blog".into()],topics:vec!["網路安全/資安".into()],link_include_patterns:vec![],official_pages:vec!["https://www.npsa.gov.uk/blog".into()]},
    Agency{name_zh:"英國研究與創新總署".into(),name_en:"UK Research and Innovation".into(),short_name:"UKRI".into(),homepage:"https://www.ukri.org/".into(),feeds:vec!["https://www.ukri.org/feed/".into()],news_pages:vec![],topics:vec!["半導體/量子技術".into()],link_include_patterns:vec![],official_pages:vec!["https://www.ukri.org/news/".into(),"https://www.ukri.org/who-we-are/how-we-are-doing/evaluation-reports/browse/".into(),"https://www.ukri.org/what-we-do/what-we-have-funded/investment-and-outputs-publication/".into()]},
]
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn registry_contains_split_dsit_successors() {
        let values = agencies();
        assert_eq!(values.len(), 13);
        assert!(values.iter().any(|agency| agency.short_name == "BIST"));
        assert!(values.iter().any(|agency| agency.short_name == "DCMS"));
        assert!(!values.iter().any(|agency| agency.short_name == "DSIT"));
        assert!(!values.iter().any(|agency| agency.short_name == "DBT"));
        assert!(values
            .iter()
            .all(|agency| agency.homepage.starts_with("https://")));
        assert!(values.iter().all(|agency| {
            !agency.feeds.is_empty()
                || !agency.news_pages.is_empty()
                || !agency.official_pages.is_empty()
        }));
        let ncsc = values
            .iter()
            .find(|agency| agency.short_name == "NCSC")
            .unwrap();
        assert_eq!(ncsc.official_pages.len(), 5);
    }
}
