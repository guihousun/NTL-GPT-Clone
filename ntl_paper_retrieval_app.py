"""NTL Paper Retrieval Web App - Enhanced with multiple academic sources."""

import base64
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[0]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

load_dotenv()


def load_config(config_path: str = "config/paper_retrieval_config.json") -> dict:
    config_file = ROOT_DIR / config_path
    if not config_file.exists():
        return {}
    with open(config_file, "r", encoding="utf-8") as f:
        return json.load(f)


def sanitize_filename(title: str) -> str:
    title = re.sub(r"[^\w\s\-]", "", title)
    title = re.sub(r"\s+", "_", title)
    return title[:100]


def compute_paper_hash(paper: dict) -> str:
    import hashlib
    key = f"{paper.get('doi', '')}{paper.get('title', '')}"
    return hashlib.md5(key.encode()).hexdigest()[:12]


def normalize_title(title: str) -> str:
    return re.sub(r"\s+", " ", title.lower().strip())


def is_duplicate(new_paper: dict, existing_papers: list[dict]) -> bool:
    new_norm = normalize_title(new_paper.get("title", ""))
    new_doi = new_paper.get("doi", "").lower().strip()

    for paper in existing_papers:
        if new_doi and paper.get("doi", "").lower().strip() == new_doi:
            return True
        existing_norm = normalize_title(paper.get("title", ""))
        if existing_norm and new_norm:
            if existing_norm == new_norm:
                return True
    return False


def search_arxiv(keywords: list[str], config: dict, progress_bar, status_text) -> list[dict]:
    results = []
    arxiv_config = config.get("arxiv", {})
    max_results = arxiv_config.get("max_results", 30)

    headers = {"User-Agent": "NTL-Paper-Retriever/1.0"}

    total = len(keywords)
    for idx, keyword in enumerate(keywords):
        progress_bar.progress((idx / total), text=f"arXiv: {keyword}")
        status_text.text(f"Searching arXiv: {keyword}")

        query = f"all:{keyword}"
        url = (
            f"http://export.arxiv.org/api/query?search_query={query}"
            f"&start=0&max_results={max_results}&sortBy=relevance"
        )

        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            entries = re.findall(
                r"<entry>.*?<title>(.*?)</title>.*?<summary>(.*?)</summary>.*?"
                r"<link.*?href=\"(.*?)\".*?</link>.*?"
                r"<published>(.*?)</published>.*?"
                r"(?:<arxiv:doi>(.*?)</arxiv:doi>)?.*?"
                r"</entry>",
                response.text,
                re.DOTALL
            )

            for entry in entries:
                title, summary, link, published, doi = entry
                paper = {
                    "title": title.strip(),
                    "abstract": summary.strip(),
                    "year": published[:4] if published else "",
                    "source": "arXiv",
                    "url": link.strip(),
                    "pdf_url": link.strip().replace("abs", "pdf"),
                    "doi": doi.strip() if doi else "",
                    "authors": [],
                    "venue": "arXiv"
                }
                results.append(paper)

        except Exception as e:
            st.error(f"arXiv error: {e}")

        time.sleep(2)

    return results


def search_semantic_scholar(keywords: list[str], config: dict, progress_bar, status_text) -> list[dict]:
    results = []
    ss_config = config.get("semantic_scholar", {})
    api_key = os.getenv(ss_config.get("api_key_env", "SEMANTIC_SCHOLAR_API_KEY"))
    fields = ss_config.get("fields", "title,authors,year,abstract,url,doi,venue")
    max_results = config.get("retrieval", {}).get("max_results_per_keyword", 20)

    headers = {"User-Agent": "NTL-Paper-Retriever/1.0"}
    if api_key:
        headers["x-api-key"] = api_key

    total = len(keywords)
    for idx, keyword in enumerate(keywords):
        progress_bar.progress((idx / total), text=f"Semantic Scholar: {keyword}")
        status_text.text(f"Searching Semantic Scholar: {keyword}")

        url = (
            f"https://api.semanticscholar.org/graph/v1/paper/search"
            f"?query={keyword}&fields={fields}&limit={max_results}"
        )

        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()

            for item in data.get("data", []):
                authors = [a.get("name", "") for a in item.get("authors", [])]
                paper = {
                    "title": item.get("title", ""),
                    "abstract": item.get("abstract", ""),
                    "year": str(item.get("year", "")),
                    "source": "Semantic Scholar",
                    "url": item.get("url", ""),
                    "pdf_url": "",
                    "doi": item.get("doi", ""),
                    "authors": authors,
                    "venue": item.get("venue", "")
                }
                results.append(paper)

        except Exception as e:
            st.error(f"Semantic Scholar error: {e}")

        time.sleep(1)

    return results


def search_openreview(keywords: list[str], progress_bar, status_text) -> list[dict]:
    results = []
    total = len(keywords)

    for idx, keyword in enumerate(keywords):
        progress_bar.progress((idx / total), text=f"OpenReview: {keyword}")
        status_text.text(f"Searching OpenReview: {keyword}")

        url = f"https://api.openreview.net/notes?search={keyword}&limit=20"

        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()

            for note in data.get("notes", []):
                paper = {
                    "title": note.get("content", {}).get("title", {}).get("value", ""),
                    "abstract": note.get("content", {}).get("abstract", {}).get("value", "")[:500],
                    "year": note.get("cdate", "")[:4] if note.get("cdate") else "",
                    "source": "OpenReview",
                    "url": f"https://openreview.net/forum?id={note.get('id', '')}",
                    "pdf_url": f"https://openreview.net/pdf?id={note.get('id', '')}",
                    "doi": "",
                    "authors": [a.get("name", "") for a in note.get("writers", [])],
                    "venue": note.get("venue", "")
                }
                if paper["title"]:
                    results.append(paper)

        except Exception as e:
            st.error(f"OpenReview error: {e}")

        time.sleep(1)

    return results


def search_google_scholar(keywords: list[str], progress_bar, status_text) -> list[dict]:
    results = []
    total = len(keywords)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    for idx, keyword in enumerate(keywords):
        progress_bar.progress((idx / total), text=f"Google Scholar: {keyword}")
        status_text.text(f"Searching Google Scholar: {keyword}")

        url = f"https://scholar.google.com/scholar?q={keyword}&hl=en&as_sdt=0,5"

        try:
            response = requests.get(url, headers=headers, timeout=30)
            if response.status_code == 200:
                st.info("Google Scholar requires manual verification (captcha)")
        except Exception as e:
            st.error(f"Google Scholar error: {e}")

        time.sleep(1)

    return results


def search_ieee(keywords: list[str], progress_bar, status_text) -> list[dict]:
    results = []
    total = len(keywords)
    api_key = os.getenv("IEEE_API_KEY", "")

    if not api_key:
        st.info("IEEE API key not configured - skipping IEEE Xplore")
        return results

    for idx, keyword in enumerate(keywords):
        progress_bar.progress((idx / total), text=f"IEEE: {keyword}")
        status_text.text(f"Searching IEEE Xplore: {keyword}")

        url = f"https://ieeexploreapi.ieee.org/api/v1/search/articles?apikey={api_key}&keyword={keyword}&max_records=20"

        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()

            for article in data.get("articles", []):
                paper = {
                    "title": article.get("article_title", ""),
                    "abstract": article.get("abstract", "")[:500],
                    "year": article.get("publication_year", ""),
                    "source": "IEEE Xplore",
                    "url": article.get("doi", ""),
                    "pdf_url": "",
                    "doi": article.get("doi", ""),
                    "authors": [a.get("full_name", "") for a in article.get("authors", [])],
                    "venue": article.get("publication_title", "")
                }
                results.append(paper)

        except Exception as e:
            st.error(f"IEEE error: {e}")

        time.sleep(1)

    return results


def search_pubmed(keywords: list[str], progress_bar, status_text) -> list[dict]:
    results = []
    total = len(keywords)

    for idx, keyword in enumerate(keywords):
        progress_bar.progress((idx / total), text=f"PubMed: {keyword}")
        status_text.text(f"Searching PubMed: {keyword}")

        url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term={keyword}&retmode=json&retmax=20"

        try:
            search_response = requests.get(url, timeout=30)
            search_data = search_response.json()

            id_list = search_data.get("esearchresult", {}).get("idlist", [])
            if id_list:
                ids = ",".join(id_list[:10])
                fetch_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id={ids}&retmode=json"

                fetch_response = requests.get(fetch_url, timeout=30)
                fetch_data = fetch_response.json()

                for uid, info in fetch_data.get("result", {}).items():
                    if uid == "uids":
                        continue
                    paper = {
                        "title": info.get("title", ""),
                        "abstract": "",
                        "year": info.get("pubdate", "")[:4] if info.get("pubdate") else "",
                        "source": "PubMed",
                        "url": f"https://pubmed.ncbi.nlm.nih.gov/{info.get('uid', '')}/",
                        "pdf_url": "",
                        "doi": info.get("doi", ""),
                        "authors": [a.get("name", "") for a in info.get("authors", [])],
                        "venue": info.get("source", "")
                    }
                    results.append(paper)

        except Exception as e:
            st.error(f"PubMed error: {e}")

        time.sleep(1)

    return results


def deduplicate_papers(papers: list[dict]) -> list[dict]:
    unique_papers = []
    for paper in papers:
        if not is_duplicate(paper, unique_papers):
            unique_papers.append(paper)
    return unique_papers


def download_pdf(pdf_url: str, output_dir: Path, filename: str) -> str | None:
    if not pdf_url:
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    filepath = output_dir / f"{filename}.pdf"

    if filepath.exists():
        return str(filepath)

    try:
        response = requests.get(pdf_url, timeout=60, stream=True)
        response.raise_for_status()

        with open(filepath, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        return str(filepath)

    except Exception as e:
        return None


def save_metadata(papers: list[dict], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata_file = output_dir / "metadata.json"

    existing = []
    if metadata_file.exists():
        with open(metadata_file, "r", encoding="utf-8") as f:
            existing = json.load(f)

    existing.extend(papers)

    with open(metadata_file, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)


st.set_page_config(
    page_title="NTL Paper Retrieval Hub",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)


def inject_custom_css():
    st.markdown("""
        <style>
        .main-header {
            font-size: 2.2rem;
            font-weight: 800;
            background: linear-gradient(90deg, #1E3A5F, #2E5077);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.5rem;
        }
        .source-badge {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: 600;
            margin-right: 4px;
        }
        .source-arxiv { background: #FF6B6B; color: white; }
        .source-semantic { background: #4ECDC4; color: white; }
        .source-ieee { background: #0066CC; color: white; }
        .source-pubmed { background: #2ECC71; color: white; }
        .source-openreview { background: #9B59B6; color: white; }
        .paper-card {
            background-color: #f8f9fa;
            border-left: 4px solid #1E3A5F;
            padding: 1rem;
            margin-bottom: 0.75rem;
            border-radius: 6px;
        }
        .metric-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 1rem;
            border-radius: 8px;
            color: white;
            text-align: center;
        }
        </style>
    """, unsafe_allow_html=True)


inject_custom_css()


def main():
    config = load_config()

    st.markdown('<div class="main-header">📚 NTL Paper Retrieval Hub</div>', unsafe_allow_html=True)
    st.markdown("### Nighttime Light Remote Sensing - Academic Paper Discovery")

    with st.sidebar:
        st.header("⚙️ Search Configuration")

        st.subheader("🔍 Keywords")
        default_keywords = config.get("retrieval", {}).get("keywords", [
            "nighttime light", "VIIRS", "DMSP-OLS", "VNP46A2", "SDGSAT"
        ])
        keywords_input = st.text_area(
            "Search terms (one per line)",
            value="\n".join(default_keywords[:6]),
            height=140
        )
        keywords = [k.strip() for k in keywords_input.split("\n") if k.strip()]

        st.subheader("📂 Data Sources")
        source_options = {
            "arXiv": "Open access preprints",
            "Semantic Scholar": "AI-powered academic search",
            "OpenReview": "Open peer review platform",
            "PubMed": "Biomedical literature",
            "IEEE Xplore": "Engineering & technology"
        }

        selected_sources = []
        for source, desc in source_options.items():
            if st.checkbox(f"{source}", value=(source in ["arXiv", "Semantic Scholar"]),
                          help=desc):
                selected_sources.append(source)

        st.subheader("📥 Options")
        download_pdfs = st.checkbox("Download available PDFs", value=False)
        max_per_keyword = st.slider("Max results per keyword", 5, 50, 15)

        st.subheader("💾 Output")
        output_dir = st.text_input(
            "Save directory",
            value=str(ROOT_DIR / "RAG" / "paper_retrieval")
        )

        st.divider()
        st.markdown("""
        **Quick Tips:**
        - Use specific keywords for better results
        - arXiv provides immediate PDF access
        - Semantic Scholar has best abstract coverage
        """)

    col1, col2, col3, col4 = st.columns(4, gap="medium")

    with col1:
        with st.container(border=True):
            st.metric("Keywords", len(keywords) if keywords else 0)

    with col2:
        with st.container(border=True):
            st.metric("Sources", len(selected_sources))

    with col3:
        with st.container(border=True):
            st.metric("Max/Keyword", max_per_keyword)

    with col4:
        with st.container(border=True):
            output_path = Path(output_dir)
            existing_count = 0
            if (output_path / "metadata.json").exists():
                try:
                    with open(output_path / "metadata.json") as f:
                        existing_count = len(json.load(f))
                except:
                    pass
            st.metric("Existing Papers", existing_count)

    st.divider()

    if not keywords:
        st.warning("Please enter at least one search keyword")
        return

    if not selected_sources:
        st.warning("Please select at least one data source")
        return

    if st.button("🔍 Start Search", type="primary", use_container_width=True):
        all_papers = []

        progress_bar = st.progress(0, text="Initializing...")
        status_text = st.empty()

        for source in selected_sources:
            if source == "arXiv":
                with st.spinner("Searching arXiv..."):
                    results = search_arxiv(keywords, config, progress_bar, status_text)
                    all_papers.extend(results)
                    st.success(f"arXiv: Found {len(results)} papers")

            elif source == "Semantic Scholar":
                with st.spinner("Searching Semantic Scholar..."):
                    results = search_semantic_scholar(keywords, config, progress_bar, status_text)
                    all_papers.extend(results)
                    st.success(f"Semantic Scholar: Found {len(results)} papers")

            elif source == "OpenReview":
                with st.spinner("Searching OpenReview..."):
                    results = search_openreview(keywords, progress_bar, status_text)
                    all_papers.extend(results)
                    st.success(f"OpenReview: Found {len(results)} papers")

            elif source == "PubMed":
                with st.spinner("Searching PubMed..."):
                    results = search_pubmed(keywords, progress_bar, status_text)
                    all_papers.extend(results)
                    st.success(f"PubMed: Found {len(results)} papers")

            elif source == "IEEE Xplore":
                with st.spinner("Searching IEEE Xplore..."):
                    results = search_ieee(keywords, progress_bar, status_text)
                    all_papers.extend(results)
                    st.success(f"IEEE Xplore: Found {len(results)} papers")

        progress_bar.empty()
        status_text.empty()

        unique_papers = deduplicate_papers(all_papers)

        for paper in unique_papers:
            paper["paper_hash"] = compute_paper_hash(paper)
            paper["filename"] = sanitize_filename(paper["title"])

        base_dir = Path(output_dir)
        raw_dir = base_dir / "raw"
        metadata_dir = base_dir / "metadata"

        if download_pdfs:
            with st.spinner("Downloading PDFs..."):
                dl_progress = st.progress(0)
                pdf_count = sum(1 for p in unique_papers if p.get("pdf_url"))
                dl_idx = 0

                for paper in unique_papers:
                    if paper.get("pdf_url"):
                        dl_idx += 1
                        dl_progress.progress(dl_idx / pdf_count, text=f"PDF {dl_idx}/{pdf_count}")
                        filename = paper.get("filename", paper.get("paper_hash", ""))
                        pdf_path = download_pdf(paper["pdf_url"], raw_dir, filename)
                        paper["local_pdf"] = pdf_path
                dl_progress.empty()

        save_metadata(unique_papers, metadata_dir)

        st.session_state["search_results"] = unique_papers
        st.session_state["output_dir"] = output_dir

        st.balloons()

    if "search_results" in st.session_state:
        results = st.session_state["search_results"]

        st.markdown("---")
        st.subheader(f"📋 Search Results ({len(results)} papers)")

        source_counts = {}
        year_counts = {}
        for p in results:
            source_counts[p.get("source", "Unknown")] = source_counts.get(p.get("source", "Unknown"), 0) + 1
            year = p.get("year", "Unknown")
            if year:
                year_counts[year] = year_counts.get(year, 0) + 1

        col_s1, col_s2 = st.columns(2)

        with col_s1:
            with st.container(border=True):
                st.markdown("**Papers by Source**")
                for source, count in sorted(source_counts.items(), key=lambda x: -x[1]):
                    st.write(f"{source}: **{count}**")

        with col_s2:
            with st.container(border=True):
                st.markdown("**Papers by Year**")
                for year, count in sorted(year_counts.items(), reverse=True)[:5]:
                    st.write(f"{year}: **{count}**")

        df = pd.DataFrame([{
            "Title": p.get("title", "")[:80] + "..." if len(p.get("title", "")) > 80 else p.get("title", ""),
            "Year": p.get("year", "-"),
            "Source": p.get("source", "-"),
            "DOI": p.get("doi", "-")[:30] + "..." if len(p.get("doi", "")) > 30 else p.get("doi", "-"),
            "PDF": "✓" if p.get("pdf_url") or p.get("local_pdf") else "—"
        } for p in results])

        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            height=300
        )

        with st.expander("📄 View All Paper Details"):
            for idx, paper in enumerate(results):
                with st.container(border=True):
                    st.markdown(f"**{idx+1}. {paper.get('title', 'N/A')}**")
                    col_a, col_b = st.columns(2)
                    with col_a:
                        st.caption(f"📅 Year: {paper.get('year', 'N/A')} | 🏛 Source: {paper.get('source', 'N/A')}")
                    with col_b:
                        if paper.get("url"):
                            st.markdown(f"[🔗 View]({paper.get('url')})", unsafe_allow_html=True)

                    authors = paper.get("authors", [])
                    if authors:
                        st.caption(f"👥 Authors: {', '.join(authors[:4])}{'...' if len(authors) > 4 else ''}")

                    abstract = paper.get("abstract", "")
                    if abstract:
                        with st.expander("📝 Abstract"):
                            st.write(abstract[:800] + "..." if len(abstract) > 800 else abstract)

        col_d1, col_d2 = st.columns(2)

        with col_d1:
            csv = df.to_csv(index=False)
            st.download_button(
                "📊 Download CSV",
                data=csv,
                file_name="ntl_papers.csv",
                mime="text/csv",
                use_container_width=True
            )

        with col_d2:
            json_data = json.dumps(results, ensure_ascii=False, indent=2)
            st.download_button(
                "📋 Download JSON",
                data=json_data,
                file_name="ntl_papers.json",
                mime="application/json",
                use_container_width=True
            )


if __name__ == "__main__":
    main()
