from __future__ import annotations

from pathlib import Path

from .models import Agency, TopicRule


DEFAULT_DAYS_BACK = 14
DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_MAX_WORKERS = 6
DEFAULT_RETRY_TOTAL = 2
DEFAULT_OUTPUT_DIR = Path.home() / "Desktop" / "UK新聞抓取" / "新聞放置區"
DEFAULT_TIMEZONE = "Asia/Taipei"
SOURCE_HEALTH_MIN_ITEMS = {
    "DSIT": 1,
    "Ofcom": 1,
    "Cabinet Office": 1,
    "DBT": 1,
}
SOURCE_HEALTH_MAX_AGE_DAYS = {
    "DSIT": 14,
    "Ofcom": 14,
    "Cabinet Office": 14,
    "DBT": 14,
}
USER_AGENT = (
    "Mozilla/5.0 (compatible; UK-news-observation-scraper/1.0; "
    "+https://www.gov.uk/)"
)


TOPIC_RULES: tuple[TopicRule, ...] = (
    TopicRule(
        name="Science & Technology",
        subtopics=(
            "科學研究",
            "技術發展",
            "創新政策",
            "研發",
        ),
        keywords=(
            "science",
            "scientific",
            "science and technology",
            "sci tech",
            "technology",
            "technological",
            "innovation",
            "research and development",
            "R&D",
        ),
    ),
    TopicRule(
        name="AI",
        subtopics=(
            "AI法",
            "模型評估",
            "演算法問責",
            "自動化決策",
            "AI與著作權",
        ),
        keywords=(
            "artificial intelligence",
            "AI",
            "machine learning",
            "foundation model",
            "frontier model",
            "generative AI",
            "automated decision",
            "algorithm",
            "explainability",
            "fairness",
            "AI Safety Institute",
            "model evaluation",
            "copyright",
            "text and data mining",
            "TDM",
        ),
    ),
    TopicRule(
        name="資料治理/隱私/數位身份",
        subtopics=(
            "跨境資料流通",
            "資料主權",
            "資料開放與再利用",
            "個人資料保護",
            "數位身份",
        ),
        keywords=(
            "data protection",
            "UK GDPR",
            "GDPR",
            "Data Protection Act",
            "international data transfer",
            "adequacy",
            "standard contractual clauses",
            "data use",
            "data access",
            "open data",
            "data reuse",
            "digital identity",
            "trust framework",
            "GOV.UK One Login",
            "One Login",
        ),
    ),
    TopicRule(
        name="數位平台",
        subtopics=(
            "平台責任",
            "內容審查",
            "推薦演算法",
            "媒體多元與資訊操縱",
            "競爭規範",
        ),
        keywords=(
            "online safety",
            "Online Safety Act",
            "platform",
            "illegal content",
            "child safety",
            "recommendation algorithm",
            "algorithm transparency",
            "media plurality",
            "disinformation",
            "misinformation",
            "foreign information manipulation",
            "digital markets",
            "Digital Markets Competition and Consumers Act",
            "Strategic Market Status",
            "SMS",
        ),
    ),
    TopicRule(
        name="網路安全/資安",
        subtopics=(
            "NIS2/關鍵基礎設施保護",
            "產品資安",
            "漏洞揭露義務",
            "SBOM",
            "供應鏈安全",
            "資安產品認證",
            "實體與數位融合保護",
        ),
        keywords=(
            "cyber",
            "cybersecurity",
            "network and information systems",
            "NIS",
            "critical infrastructure",
            "critical national infrastructure",
            "product security",
            "telecommunications infrastructure",
            "vulnerability",
            "coordinated vulnerability disclosure",
            "secure by design",
            "secure-by-design",
            "SBOM",
            "software bill of materials",
            "supply chain",
            "Cyber Essentials",
            "incident response",
            "resilience",
            "protective security",
            "hybrid threat",
        ),
    ),
    TopicRule(
        name="半導體/量子技術",
        subtopics=("半導體", "量子技術"),
        keywords=(
            "semiconductor",
            "National Semiconductor Strategy",
            "chip",
            "microelectronics",
            "export control",
            "quantum",
            "National Quantum Strategy",
            "quantum technologies",
            "quantum computing",
        ),
    ),
)


AGENCIES: tuple[Agency, ...] = (
    Agency(
        name_zh="科學、創新和技術部",
        name_en="Department for Science, Innovation and Technology",
        short_name="DSIT",
        homepage="https://www.gov.uk/government/organisations/department-for-science-innovation-and-technology",
        feeds=("https://www.gov.uk/government/organisations/department-for-science-innovation-and-technology.atom",),
        topics=("AI", "資料治理/隱私/數位身份", "網路安全/資安", "半導體/量子技術"),
        link_include_patterns=("/government/news/",),
    ),
    Agency(
        name_zh="人工智慧安全機構",
        name_en="AI Safety Institute",
        short_name="AISI",
        homepage="https://www.gov.uk/government/organisations/ai-safety-institute",
        feeds=("https://www.gov.uk/government/organisations/ai-safety-institute.atom",),
        topics=("AI",),
        link_include_patterns=("/government/news/",),
    ),
    Agency(
        name_zh="英國資訊專員辦公室",
        name_en="Information Commissioner's Office",
        short_name="ICO",
        homepage="https://ico.org.uk/about-the-ico/media-centre/news-and-blogs/",
        news_pages=("https://ico.org.uk/about-the-ico/media-centre/news-and-blogs/",),
        topics=("AI", "資料治理/隱私/數位身份"),
    ),
    Agency(
        name_zh="競爭與市場管理局",
        name_en="Competition and Markets Authority",
        short_name="CMA",
        homepage="https://www.gov.uk/government/organisations/competition-and-markets-authority",
        feeds=("https://www.gov.uk/government/organisations/competition-and-markets-authority.atom",),
        topics=("AI", "數位平台"),
        link_include_patterns=("/government/news/",),
    ),
    Agency(
        name_zh="英國智財局",
        name_en="UK Intellectual Property Office",
        short_name="UK IPO",
        homepage="https://www.gov.uk/government/organisations/intellectual-property-office",
        feeds=("https://www.gov.uk/government/organisations/intellectual-property-office.atom",),
        topics=("AI",),
        link_include_patterns=("/government/news/",),
    ),
    Agency(
        name_zh="政府數位服務團隊",
        name_en="Government Digital Service",
        short_name="GDS",
        homepage="https://www.gov.uk/government/organisations/government-digital-service",
        feeds=("https://www.gov.uk/government/organisations/government-digital-service.atom",),
        topics=("資料治理/隱私/數位身份",),
        link_include_patterns=("/government/news/",),
    ),
    Agency(
        name_zh="英國通訊管理局",
        name_en="Office of Communications",
        short_name="Ofcom",
        homepage="https://www.ofcom.org.uk/",
        feeds=("https://www.ofcom.org.uk/news-centre/rss",),
        news_pages=("https://www.ofcom.org.uk/news-and-updates",),
        topics=("數位平台",),
    ),
    Agency(
        name_zh="國家網路安全中心",
        name_en="National Cyber Security Centre",
        short_name="NCSC",
        homepage="https://www.ncsc.gov.uk/",
        feeds=("https://www.ncsc.gov.uk/api/1/services/v1/all-rss-feed.xml",),
        topics=("數位平台", "網路安全/資安"),
    ),
    Agency(
        name_zh="英國選舉委員會",
        name_en="Electoral Commission",
        short_name="Electoral Commission",
        homepage="https://www.electoralcommission.org.uk/",
        news_pages=("https://www.electoralcommission.org.uk/news-and-views/media-centre",),
        topics=("數位平台",),
    ),
    Agency(
        name_zh="英國內閣辦公室",
        name_en="Cabinet Office",
        short_name="Cabinet Office",
        homepage="https://www.gov.uk/government/organisations/cabinet-office",
        feeds=("https://www.gov.uk/government/organisations/cabinet-office.atom",),
        topics=("網路安全/資安",),
        link_include_patterns=("/government/news/",),
    ),
    Agency(
        name_zh="國家保護安全局",
        name_en="National Protective Security Authority",
        short_name="NPSA",
        homepage="https://www.npsa.gov.uk/",
        news_pages=("https://www.npsa.gov.uk/blog",),
        topics=("網路安全/資安",),
    ),
    Agency(
        name_zh="商業及貿易部",
        name_en="Department for Business and Trade",
        short_name="DBT",
        homepage="https://www.gov.uk/government/organisations/department-for-business-and-trade",
        feeds=("https://www.gov.uk/government/organisations/department-for-business-and-trade.atom",),
        topics=("半導體/量子技術",),
        link_include_patterns=("/government/news/",),
    ),
    Agency(
        name_zh="英國研究與創新總署",
        name_en="UK Research and Innovation",
        short_name="UKRI",
        homepage="https://www.ukri.org/",
        feeds=("https://www.ukri.org/feed/",),
        topics=("半導體/量子技術",),
    ),
)
