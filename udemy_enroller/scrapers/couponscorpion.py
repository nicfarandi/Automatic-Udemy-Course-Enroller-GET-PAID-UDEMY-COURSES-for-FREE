"""CouponScorpion scraper - requires Selenium for redirect resolution."""

import re
import time
from typing import List, Optional

import requests
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from udemy_enroller.logger import get_logger
from udemy_enroller.scrapers.selenium_base_scraper import SeleniumBaseScraper

logger = get_logger()


class CouponScorpionScraper(SeleniumBaseScraper):
    """Contains any logic related to scraping of data from couponscorpion.com."""

    DOMAIN = "https://couponscorpion.com"

    def __init__(self, enabled, max_pages=None):
        """Initialize."""
        super().__init__()
        self.scraper_name = "couponscorpion"
        if not enabled:
            self.set_state_disabled()
        self.max_pages = max_pages
        self.last_page = None

    @SeleniumBaseScraper.time_run
    async def run(self) -> List:
        """
        Gathers the udemy links.

        :return: List of udemy course links
        """
        try:
            links = await self.get_links()
            logger.info(
                f"Page: {self.current_page} of {self.last_page} scraped from couponscorpion.com"
            )
            self.max_pages_reached()
            return links
        finally:
            # Clean up driver after scraping is complete
            if self.is_complete() or self.is_disabled():
                self.close_driver()

    async def get_links(self) -> List:
        """
        Scrape udemy links from couponscorpion.com.

        :return: List of udemy course urls
        """
        self.current_page += 1

        # Initialize driver if needed
        self.init_driver()

        if not self.driver:
            logger.error("Cannot scrape couponscorpion.com without Selenium driver")
            return []

        # Build the page URL
        page_url = (
            self.DOMAIN if self.current_page == 1 
            else f"{self.DOMAIN}/page/{self.current_page}"
        )

        try:
            # Get post links from the listing page using requests (faster)
            post_links = self._get_post_links(page_url)
            logger.debug(
                f"Found {len(post_links)} posts on page {self.current_page}"
            )

            # Get coupon links from each post
            udemy_links = self.gather_udemy_course_links(post_links)

            for counter, course in enumerate(udemy_links):
                logger.debug(f"Received Link {counter + 1} : {course}")

            return udemy_links

        except Exception as e:
            logger.error(f"Error scraping page {self.current_page}: {e}")
            return []

    def _get_post_links(self, page_url: str) -> List[str]:
        """
        Get post links from the listing page using requests.

        :param str page_url: The listing page URL
        :return: List of post URLs
        """
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            )
        }

        try:
            resp = requests.get(page_url, headers=headers, timeout=10)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            # Find all article elements with the offer_grid class
            articles = soup.find_all("article", class_=re.compile(r"^col_item offer_grid"))

            post_links = []
            for article in articles:
                a = article.find("a", href=True)
                if a:
                    post_links.append(a["href"])

            # Parse pagination to find last page
            if self.last_page is None:
                pagination = soup.find("ul", class_="page-numbers")
                if pagination:
                    page_links = pagination.find_all("a")
                    page_numbers = []
                    for link in page_links:
                        text = link.text.strip()
                        if text.isdigit():
                            page_numbers.append(int(text))
                    if page_numbers:
                        self.last_page = max(page_numbers)
                    else:
                        self.last_page = self.current_page
                else:
                    # No pagination found, assume single page
                    self.last_page = 1

            return post_links

        except Exception as e:
            logger.debug(f"Error getting post links from {page_url}: {e}")
            return []

    def _get_coupon_redirect_links(self, post_url: str) -> List[str]:
        """
        Get coupon redirect links from a post page using requests.

        :param str post_url: The post URL
        :return: List of redirect URLs
        """
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            )
        }

        try:
            resp = requests.get(post_url, headers=headers, timeout=10)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            # Find all button wrappers
            spans = soup.find_all("span", class_="rh_button_wrapper")

            links = []
            for span in spans:
                a = span.find("a", href=True)
                if a:
                    links.append(a["href"])

            return links

        except Exception as e:
            logger.debug(f"Error getting coupon links from {post_url}: {e}")
            return []

    def _resolve_redirect(self, url: str) -> Optional[str]:
        """
        Resolve redirect URL to final Udemy URL using Selenium.

        :param str url: The redirect URL
        :return: Final Udemy URL or None
        """
        if not self.driver:
            return None

        try:
            self.driver.get(url)
            time.sleep(2)  # Wait for redirect

            # Get the final URL after redirect
            final_url = self.driver.current_url

            # Validate it's a proper Udemy coupon URL
            validated = self.validate_coupon_url(final_url)
            if validated:
                return validated

        except Exception as e:
            logger.debug(f"Error resolving redirect for {url}: {e}")

        return None

    def gather_udemy_course_links(self, post_links: List[str]) -> List[str]:
        """
        Fetch the udemy course links from couponscorpion.com posts.

        :param list post_links: A list of couponscorpion.com post links
        :return: list of udemy links
        """
        udemy_links = []

        for post_url in post_links:
            # Get redirect links from the post
            redirect_links = self._get_coupon_redirect_links(post_url)

            # Resolve each redirect to get the final Udemy URL
            for redirect_url in redirect_links:
                final_url = self._resolve_redirect(redirect_url)
                if final_url:
                    udemy_links.append(final_url)

        return udemy_links