from __future__ import annotations

import os
from pathlib import Path
import sys

from .models import TopicRule


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
            "digital sovereignty",
            "open data",
            "data reuse",
            "data reuse policy",
            "Open Government Data Framework",
            "Digital ID",
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
            "social media",
            "social media ban",
            "deepfake",
            "deepfakes",
            "illegal intimate images",
            "recommendation algorithm",
            "algorithm transparency",
            "media plurality",
            "media green paper",
            "broadcast impartiality",
            "online influence transparency",
            "disinformation",
            "misinformation",
            "foreign information manipulation",
            "electoral information manipulation",
            "digital markets",
            "mobile platform",
            "mobile platforms",
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


# Topic definitions must be available before strict registry validation.
from .organisation_registry import load_organisation_registry  # noqa: E402

ORGANISATION_REGISTRY = load_organisation_registry(
    known_topics={rule.name for rule in TOPIC_RULES},
)
AGENCIES = ORGANISATION_REGISTRY.agencies
SOURCE_HEALTH_MIN_ITEMS = ORGANISATION_REGISTRY.minimum_items
SOURCE_HEALTH_MAX_AGE_DAYS = ORGANISATION_REGISTRY.maximum_age_days
