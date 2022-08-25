class ScrapeConfig:
    """Scrape configuration"""
    pass


class ScrapeResult:
    """Class hosting the result of the scrape"""

    def data(self):
        """Return scraped data"""
        pass


class Scraper:
    """The scraper"""

    def scrape(self, cfg: ScrapeConfig) -> ScrapeResult:
        """Scrape data with some configuration options"""
        pass

    def save(self, cfg: ScrapeConfig, result: ScrapeResult):
        """Save the scraped data into a persistent system"""
        pass
