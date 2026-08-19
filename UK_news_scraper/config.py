from __future__ import annotations

import os
from pathlib import Path
import sys

from .models import Agency, TopicRule


DEFAULT_DAYS_BACK = 14
DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_MAX_WORKERS = 6
DEFAULT_RETRY_TOTAL = 2


def _default_output_dir() -> Path:
    configured = os.environ.get("UK_NEWS_OUTPUT_DIR")
    if configured:
        return Path(configured).expanduser()
    if getattr(sys, "frozen", False):
        return Path.home() / "Desktop" / "UK新聞抓取" / "新聞放置區"
    return Path(__file__).resolve().parent.parent / "新聞放置區"


DEFAULT_OUTPUT_DIR = _default_output_dir()
DEFAULT_TIMEZONE = "Asia/Taipei"
SOURCE_HEALTH_MIN_ITEMS = {
    "BIST": 1,
    "DCMS": 1,
    "Ofcom": 1,
    "Cabinet Office": 1,
}
SOURCE_HEALTH_MAX_AGE_DAYS = {
    "BIST": 14,
    "DCMS": 14,
    "Ofcom": 14,
    "Cabinet Office": 14,
    "CMA": 30,
    "NCSC": 30,
    "UK IPO": 45,
    "ICO": 45,
    "Electoral Commission": 45,
    "AISI": 60,
    "GDS": 60,
    "NPSA": 60,
    "UKRI": 60,
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
            "foundation models",
            "frontier model",
            "frontier AI",
            "generative AI",
            "automated decision",
            "automated decision-making",
            "algorithm",
            "algorithmic accountability",
            "explainability",
            "fairness",
            "AI Safety Institute",
            "AI Security Institute",
            "model evaluation",
            "evaluation",
            "copyright",
            "text and data mining",
            "TDM",
            "privacy-by-design",
            "AI and data protection",
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
            "data reuse policy",
            "Open Government Data Framework",
            "digital identity",
            "trust framework",
            "GOV.UK One Login",
            "One Login",
            "UK Digital Identity and Attributes Trust Framework",
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
            "broadcast impartiality",
            "online influence transparency",
            "disinformation",
            "misinformation",
            "foreign information manipulation",
            "electoral information manipulation",
            "digital markets",
            "Digital Markets Competition and Consumers Act",
            "Strategic Market Status",
            "SMS",
            "systemic risk",
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
            "government cyber security strategy",
            "Cyber Essentials",
            "incident response",
            "resilience",
            "protective security",
            "hybrid threat",
            "hybrid threat resilience",
            "critical infrastructure protection",
            "national cyber resilience",
        ),
    ),
    TopicRule(
        name="半導體/量子技術",
        subtopics=("半導體", "量子技術"),
        keywords=(
            "semiconductor",
            "National Semiconductor Strategy",
            "semiconductor strategy",
            "chip",
            "microelectronics",
            "export control",
            "quantum",
            "National Quantum Strategy",
            "quantum technologies",
            "quantum computing",
            "quantum R&D",
        ),
    ),
)


AGENCIES: tuple[Agency, ...] = (
    Agency(
        name_zh="商業、創新、科學及貿易部",
        name_en="Department for Business, Innovation, Science and Trade",
        short_name="BIST",
        homepage="https://www.gov.uk/government/organisations/department-for-business-innovation-science-and-trade",
        feeds=("https://www.gov.uk/government/organisations/department-for-business-innovation-science-and-trade.atom",),
        topics=("Science & Technology", "AI", "半導體/量子技術"),
        link_include_patterns=("/government/news/", "/guidance/", "/government/publications/", "/government/consultations/", "/government/research/", "/government/statistics/"),
        official_pages=("https://www.gov.uk/government/organisations/department-for-business-innovation-science-and-trade",),
    ),
    Agency(
        name_zh="數位、文化、媒體及體育部",
        name_en="Department for Digital, Culture, Media and Sport",
        short_name="DCMS",
        homepage="https://www.gov.uk/government/organisations/department-for-culture-media-and-sport",
        feeds=("https://www.gov.uk/government/organisations/department-for-culture-media-and-sport.atom",),
        topics=("資料治理/隱私/數位身份", "數位平台", "網路安全/資安"),
        link_include_patterns=("/government/news/", "/guidance/", "/government/publications/", "/government/consultations/", "/government/research/", "/government/statistics/"),
        official_pages=("https://www.gov.uk/government/organisations/department-for-culture-media-and-sport",),
    ),
    Agency(
        name_zh="人工智慧安全研究所",
        name_en="AI Security Institute",
        short_name="AISI",
        homepage="https://www.gov.uk/government/organisations/ai-safety-institute",
        feeds=("https://www.gov.uk/government/organisations/ai-safety-institute.atom",),
        topics=("AI",),
        link_include_patterns=("/government/news/", "/guidance/", "/government/publications/", "/government/consultations/", "/government/research/", "/government/statistics/"),
        official_pages=("https://www.gov.uk/government/organisations/ai-safety-institute",),
    ),
    Agency(
        name_zh="英國資訊專員辦公室",
        name_en="Information Commissioner's Office",
        short_name="ICO",
        homepage="https://ico.org.uk/about-the-ico/media-centre/news-and-blogs/",
        news_pages=("https://ico.org.uk/about-the-ico/media-centre/news-and-blogs/",),
        official_pages=("https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/",),
        topics=("AI", "資料治理/隱私/數位身份"),
    ),
    Agency(
        name_zh="競爭與市場管理局",
        name_en="Competition and Markets Authority",
        short_name="CMA",
        homepage="https://www.gov.uk/government/organisations/competition-and-markets-authority",
        feeds=("https://www.gov.uk/government/organisations/competition-and-markets-authority.atom",),
        topics=("AI", "數位平台"),
        link_include_patterns=("/government/news/", "/guidance/", "/government/publications/", "/government/consultations/", "/government/research/", "/government/statistics/"),
        official_pages=("https://www.gov.uk/government/organisations/competition-and-markets-authority",),
    ),
    Agency(
        name_zh="英國智財局",
        name_en="UK Intellectual Property Office",
        short_name="UK IPO",
        homepage="https://www.gov.uk/government/organisations/intellectual-property-office",
        feeds=("https://www.gov.uk/government/organisations/intellectual-property-office.atom",),
        topics=("AI",),
        link_include_patterns=("/government/news/", "/guidance/", "/government/publications/", "/government/consultations/", "/government/research/", "/government/statistics/"),
        official_pages=("https://www.gov.uk/government/organisations/intellectual-property-office",),
    ),
    Agency(
        name_zh="政府數位服務團隊",
        name_en="Government Digital Service",
        short_name="GDS",
        homepage="https://www.gov.uk/government/organisations/government-digital-service",
        feeds=("https://www.gov.uk/government/organisations/government-digital-service.atom",),
        topics=("AI", "資料治理/隱私/數位身份"),
        link_include_patterns=("/government/news/", "/guidance/", "/government/publications/", "/government/consultations/", "/government/research/", "/government/statistics/"),
        official_pages=("https://www.gov.uk/government/organisations/government-digital-service",),
    ),
    Agency(
        name_zh="英國通訊管理局",
        name_en="Office of Communications",
        short_name="Ofcom",
        homepage="https://www.ofcom.org.uk/",
        feeds=("https://www.ofcom.org.uk/news-centre/rss",),
        news_pages=("https://www.ofcom.org.uk/news-and-updates",),
        official_pages=("https://www.ofcom.org.uk/news-and-updates",),
        topics=("數位平台",),
    ),
    Agency(
        name_zh="國家網路安全中心",
        name_en="National Cyber Security Centre",
        short_name="NCSC",
        homepage="https://www.ncsc.gov.uk/",
        feeds=("https://www.ncsc.gov.uk/api/1/services/v1/all-rss-feed.xml",),
        official_pages=(
            "https://www.ncsc.gov.uk/collection/what-to-do-when-cyber-attacks-disrupt-your-organisation",
            "https://www.ncsc.gov.uk/collection/what-to-do-when-cyber-attacks-disrupt-your-organisation/recovering",
            "https://www.ncsc.gov.uk/collection/what-to-do-when-cyber-attacks-disrupt-your-organisation/recovering/immediate-activities",
            "https://www.ncsc.gov.uk/collection/what-to-do-when-cyber-attacks-disrupt-your-organisation/recovering/recovering-ongoing-investigations",
            "https://www.ncsc.gov.uk/collection/what-to-do-when-cyber-attacks-disrupt-your-organisation/recovering/rebuild",
        ),
        topics=("數位平台", "網路安全/資安"),
    ),
    Agency(
        name_zh="英國選舉委員會",
        name_en="Electoral Commission",
        short_name="Electoral Commission",
        homepage="https://www.electoralcommission.org.uk/",
        news_pages=("https://www.electoralcommission.org.uk/news-and-views/media-centre",),
        official_pages=("https://www.electoralcommission.org.uk/news-and-views/media-centre",),
        topics=("數位平台",),
    ),
    Agency(
        name_zh="英國內閣辦公室",
        name_en="Cabinet Office",
        short_name="Cabinet Office",
        homepage="https://www.gov.uk/government/organisations/cabinet-office",
        feeds=("https://www.gov.uk/government/organisations/cabinet-office.atom",),
        topics=("AI", "網路安全/資安"),
        link_include_patterns=("/government/news/", "/guidance/", "/government/publications/", "/government/consultations/", "/government/research/", "/government/statistics/"),
        official_pages=("https://www.gov.uk/government/organisations/cabinet-office",),
    ),
    Agency(
        name_zh="國家保護安全局",
        name_en="National Protective Security Authority",
        short_name="NPSA",
        homepage="https://www.npsa.gov.uk/",
        news_pages=("https://www.npsa.gov.uk/blog",),
        official_pages=("https://www.npsa.gov.uk/blog",),
        topics=("網路安全/資安",),
    ),
    Agency(
        name_zh="英國研究與創新總署",
        name_en="UK Research and Innovation",
        short_name="UKRI",
        homepage="https://www.ukri.org/",
        feeds=("https://www.ukri.org/feed/",),
        official_pages=(
            "https://www.ukri.org/news/",
            "https://www.ukri.org/who-we-are/how-we-are-doing/evaluation-reports/browse/",
            "https://www.ukri.org/what-we-do/what-we-have-funded/investment-and-outputs-publication/",
        ),
        topics=("半導體/量子技術",),
    ),
)
