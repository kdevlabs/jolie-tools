import { PuppeteerCrawler, Dataset, log, enqueueLinks } from 'crawlee';

// Define the function to extract product details
const extractProductDetails = async ({ page, request }) => {
    log.info(`Processing ${request.url}`);

    // Use page.evaluate to access the page's content and extract product details
    const products = await page.evaluate(() => {
        const productElements = document.querySelectorAll('.product-item');
        const productDetails = [];

        productElements.forEach((product) => {
            const name = product.querySelector('.product-name')?.textContent.trim();
            const price = product.querySelector('.product-price')?.textContent.trim();
            const description = product.querySelector('.product-description')?.textContent.trim();
            if (name) {
                productDetails.push({ name, price, description });
            }
        });

        return productDetails;
    });

    // Log the extracted product details
    console.log(products);

    // Save the extracted data
    await Dataset.pushData({ url: request.url, products });
    await enqueueLinks({ request, selector: 'a.product-name' });
};

// Initialize PuppeteerCrawler
const crawler = new PuppeteerCrawler({
    requestHandler: extractProductDetails,
    failedRequestHandler({ request }) {
        log.error(`Request ${request.url} failed too many times.`);
    },
    // Optionally set other options like maxConcurrency, requestQueue, etc.
});

// Define starting URLs. You might want to start from specific product listing pages
const startUrls = [
    { url: 'https://www.razer.com/store' }, // Adjust this URL based on the actual product listing page
    // Add more URLs or use enqueueLinks to dynamically find and follow links
];

// Function to start the crawler
const runCrawler = async () => {
    await crawler.addRequests(startUrls);
    await crawler.run();
    log.info('Crawler has finished.');
};

runCrawler().catch(log.error);
