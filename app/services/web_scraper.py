import base64
import logging
import re
import time
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class WebScraper:
    """Service for scraping content from websites."""

    @staticmethod
    def scrape_url(url: str, max_pages: int = 50) -> str | None:
        """
        Scrape text content from a website URL and all its internal pages.

        Args:
            url: The base URL to scrape (will crawl entire site)
            max_pages: Maximum number of pages to scrape (default: 50)

        Returns:
            Extracted text content from all pages or None if scraping fails

        """
        try:
            # Validate and normalize URL
            parsed = urlparse(url)
            if not parsed.netloc:
                logger.error(f"Invalid URL format: {url}")
                return None

            # Add scheme if missing
            if not parsed.scheme:
                url = f"https://{url}"
                parsed = urlparse(url)

            base_url = f"{parsed.scheme}://{parsed.netloc}"
            base_domain = parsed.netloc.replace("www.", "")

            # Set headers to mimic a browser
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",  # noqa: E501
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate",
                "Connection": "keep-alive",
            }

            # Track visited URLs to avoid duplicates
            visited_urls: set[str] = set()
            urls_to_visit: list[str] = [url]
            all_content: list[str] = []

            logger.info(f"Starting to scrape website: {base_url} (max {max_pages} pages)")

            # Crawl the website
            while urls_to_visit and len(visited_urls) < max_pages:
                current_url = urls_to_visit.pop(0)

                # Normalize URL (remove fragments, trailing slashes)
                parsed_current = urlparse(current_url)
                normalized_url = urlunparse(
                    (
                        parsed_current.scheme,
                        parsed_current.netloc,
                        parsed_current.path.rstrip("/") or "/",
                        parsed_current.params,
                        parsed_current.query,
                        "",  # Remove fragment
                    )
                )

                # Skip if already visited
                if normalized_url in visited_urls:
                    continue

                # Skip external URLs
                if parsed_current.netloc.replace("www.", "") != base_domain:
                    continue

                # Skip non-HTML files
                if any(
                    normalized_url.lower().endswith(ext)
                    for ext in [
                        ".pdf",
                        ".jpg",
                        ".jpeg",
                        ".png",
                        ".gif",
                        ".css",
                        ".js",
                        ".zip",
                        ".doc",
                        ".docx",
                    ]
                ):
                    continue

                try:
                    logger.info(f"Scraping page {len(visited_urls) + 1}/{max_pages}: {normalized_url}")

                    # Fetch the page
                    response = requests.get(normalized_url, headers=headers, timeout=30, allow_redirects=True)
                    response.raise_for_status()

                    # Check if it's HTML
                    content_type = response.headers.get("Content-Type", "").lower()
                    if "text/html" not in content_type:
                        visited_urls.add(normalized_url)
                        continue

                    # Parse HTML
                    soup = BeautifulSoup(response.content, "html.parser")

                    # Extract page content
                    page_content = WebScraper._extract_page_content(soup, normalized_url)
                    if page_content:
                        all_content.append(page_content)

                    # Mark as visited
                    visited_urls.add(normalized_url)

                    # Find and add new links to visit
                    if len(visited_urls) < max_pages:
                        links = WebScraper._extract_internal_links(soup, base_url, base_domain)
                        for link in links:
                            if link not in visited_urls and link not in urls_to_visit:
                                urls_to_visit.append(link)

                    # Be polite - add a small delay between requests
                    time.sleep(0.5)

                except requests.exceptions.RequestException as e:
                    logger.warning(f"Error fetching {normalized_url}: {e}")
                    visited_urls.add(normalized_url)  # Mark as visited to avoid retrying
                    continue
                except Exception as e:
                    logger.warning(f"Error processing {normalized_url}: {e}")
                    visited_urls.add(normalized_url)
                    continue

            # Combine all content
            if not all_content:
                logger.warning(f"No content scraped from {base_url}")
                return None

            # Parenthesised deliberately: the separator has to JOIN the pages.
            # Without the parentheses the separator is prepended once to the
            # whole document and the pages run together with only a blank line.
            separator = "\n\n" + "=" * 80 + "\n\n"
            full_text = separator.join(all_content)
            logger.info(
                f"Successfully scraped {len(visited_urls)} pages, {len(full_text)} characters from {base_url}"
            )
            return full_text

        except Exception as e:
            logger.error(f"Error scraping website {url}: {e}")
            return None

    # Placeholder Joomla renders in place of a cloaked address. Without decoding
    # we would scrape this sentence instead of the actual email.
    SPAMBOT_PLACEHOLDER = "This email address is being protected from spambots"

    @staticmethod
    def _reveal_cloaked_emails(soup: BeautifulSoup) -> int:
        """Replace JavaScript-cloaked email addresses with the real address.

        Many Joomla sites (etiedu.org included) hide addresses behind
        <joomla-hidden-mail> tags carrying base64 attributes, or behind a
        mailto: link whose visible text is a "protected from spambots" notice.
        The address is present in the HTML, just encoded - no browser needed.

        Substitution happens in place so the address stays next to the person or
        department it belongs to, which is what makes it retrievable later.
        """
        revealed = 0

        # 1. <joomla-hidden-mail first="base64" last="base64" text="base64">
        for tag in soup.find_all("joomla-hidden-mail"):
            email = None
            encoded_text = tag.get("text")
            if encoded_text:
                try:
                    decoded = base64.b64decode(encoded_text).decode("utf-8", "ignore")
                    if "@" in decoded:
                        email = decoded
                except Exception:  # nosec B110 - a malformed cloaked address is skipped, not fatal
                    pass
            if not email and tag.get("first") and tag.get("last"):
                try:
                    user = base64.b64decode(tag.get("first")).decode("utf-8", "ignore")
                    domain = base64.b64decode(tag.get("last")).decode("utf-8", "ignore")
                    if user and domain:
                        email = f"{user}@{domain}"
                except Exception:  # nosec B110 - a malformed cloaked address is skipped, not fatal
                    pass
            if email:
                tag.replace_with(email)
                revealed += 1

        # 2. <a href="mailto:someone@example.com">…placeholder text…</a>
        for anchor in soup.find_all("a", href=True):
            href = anchor["href"]
            if not href.lower().startswith("mailto:"):
                continue
            email = href[7:].split("?")[0].strip()
            if "@" not in email:  # type: ignore[operator]  # bs4 attrs are untyped; str here
                continue
            if (
                WebScraper.SPAMBOT_PLACEHOLDER.lower() in anchor.get_text().lower()
                or not anchor.get_text().strip()
            ):
                anchor.string = email
                revealed += 1

        return revealed

    @staticmethod
    def _extract_page_content(soup: BeautifulSoup, url: str) -> str | None:
        """Extract text content from a single page."""
        try:
            # Decode cloaked emails BEFORE anything is stripped - contact details
            # frequently live in the header/footer that gets removed below.
            try:
                revealed = WebScraper._reveal_cloaked_emails(soup)
                if revealed:
                    logger.info(f"Revealed {revealed} cloaked email address(es) on {url}")
            except Exception as e:
                logger.warning(f"Could not reveal cloaked emails on {url}: {e}")

            # Collect every address on the page before stripping sections, so the
            # contact block survives even when it sits in a removed footer.
            page_emails = sorted(
                {
                    m.group(0)
                    for m in re.finditer(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", str(soup))
                }
            )

            # Remove script and style elements
            for element in soup(["script", "style", "nav", "header", "footer", "aside"]):
                element.decompose()

            text_parts = []

            # Extract URL and title
            parsed = urlparse(url)
            page_path = parsed.path.strip("/") or "homepage"
            text_parts.append(f"URL: {url}")
            text_parts.append(f"Page: {page_path}")

            # Extract title
            title = soup.find("title")
            if title:
                text_parts.append(f"Title: {title.get_text().strip()}")

            # Extract meta description
            meta_desc = soup.find("meta", attrs={"name": "description"})
            if meta_desc and meta_desc.get("content"):
                text_parts.append(f"Description: {meta_desc.get('content').strip()}")

            # Try to find main content area
            main_content = (
                soup.find("main")
                or soup.find("article")
                or soup.find("div", class_=re.compile(r"content|main|body", re.I))
            )

            if main_content:
                content_text = WebScraper._extract_text_from_element(main_content)
            else:
                # Fallback: extract from body
                body = soup.find("body")
                if body:
                    content_text = WebScraper._extract_text_from_element(body)
                else:
                    content_text = ""

            if content_text:
                text_parts.append(content_text)

            # Re-state any address that did not survive extraction (e.g. it lived
            # in the footer), so the page still carries its contact details.
            missing = [e for e in page_emails if e not in content_text]
            if missing:
                text_parts.append("Email addresses on this page: " + ", ".join(missing))

            # Combine all text
            page_text = "\n\n".join([part for part in text_parts if part.strip()])

            if len(page_text.strip()) < 50:
                return None

            return page_text

        except Exception as e:
            logger.warning(f"Error extracting content from {url}: {e}")
            return None

    @staticmethod
    def _extract_internal_links(soup: BeautifulSoup, base_url: str, base_domain: str) -> list[str]:
        """Extract all internal links from a page."""
        links = []
        try:
            for anchor in soup.find_all("a", href=True):
                href = anchor.get("href", "").strip()
                if not href:
                    continue

                # Skip mailto, tel, javascript links
                if href.startswith(("mailto:", "tel:", "javascript:", "#")):
                    continue

                # Convert relative URLs to absolute
                absolute_url = urljoin(base_url, href)
                parsed = urlparse(absolute_url)

                # Only include links from the same domain
                if parsed.netloc.replace("www.", "") == base_domain:
                    # Normalize URL
                    normalized = urlunparse(
                        (
                            parsed.scheme,
                            parsed.netloc,
                            parsed.path.rstrip("/") or "/",
                            parsed.params,
                            parsed.query,
                            "",  # Remove fragment
                        )
                    )
                    links.append(normalized)

        except Exception as e:
            logger.warning(f"Error extracting links: {e}")

        return links

    @staticmethod
    def _extract_text_from_element(element: Any) -> str:
        """Extract clean text from a BeautifulSoup element."""
        if not element:
            return ""

        # Get text and clean it up
        text: str = element.get_text(separator="\n", strip=True)

        # Remove excessive whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]+", " ", text)

        return text.strip()
