import asyncio
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import pandas as pd
import streamlit as st


# Updating the fetch_links function to provide status updates for each link being checked

async def fetch_links(client: httpx.AsyncClient, url: str, status_text) -> (pd.DataFrame, pd.DataFrame):
    success_links = []
    error_links = []
    try:
        response = await client.get(url)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        parent_title = soup.title.text if soup.title else "No Title Found"

        for a in soup.find_all("a", href=True):
            link_url = urljoin(url, a.get("href"))
            if "razer.com" in link_url:
                try:
                    status_text.text(f"Checking link: {link_url}")  # Update status text for each link
                    link_response = await client.get(link_url)
                    if link_response.status_code == 200:
                        success_links.append({
                            "Status": f"{link_response.status_code} OK - Success",
                            "Text": a.text.strip(),
                            "URL": link_url,
                            "Parent URL": url,
                            "Parent Title": parent_title,
                        })
                    else:
                        error_links.append({
                            "Status": f"{link_response.status_code} - Error",
                            "Text": a.text.strip(),
                            "URL": link_url,
                            "Parent URL": url,
                            "Parent Title": parent_title,
                        })
                except httpx.HTTPStatusError as e:
                    error_message = get_friendly_http_error_message(e.response.status_code)
                    error_links.append({
                        "Status": error_message,
                        "Text": a.text.strip(),
                        "URL": link_url,
                        "Parent URL": url,
                        "Parent Title": parent_title,
                    })

        return pd.DataFrame(success_links), pd.DataFrame(error_links)

    except httpx.HTTPStatusError as e:
        error_message = get_friendly_http_error_message(e.response.status_code)
        return pd.DataFrame(), pd.DataFrame([{
            "Status": error_message,
            "Text": "Failed to fetch",
            "URL": "",
            "Parent URL": url,
            "Parent Title": "Failed to fetch",
        }])
    except Exception:
        return pd.DataFrame(), pd.DataFrame([{
            "Status": "Error - Could not fetch data",
            "Text": "Failed to fetch",
            "URL": "",
            "Parent URL": url,
            "Parent Title": "Failed to fetch",
        }])

# Now each link processed will update the status in the Streamlit app, enhancing the transparency and interactivity of the crawl.

def get_friendly_http_error_message(status_code: int) -> str:
    """Provides a non-technical explanation for common HTTP status codes."""
    if status_code == 404:
        return "404 Not Found - The page could not be found."
    elif status_code == 403:
        return "403 Forbidden - Access is denied."
    elif status_code == 500:
        return "500 Internal Server Error - The server encountered an unexpected condition."
    # Add more status codes as needed
    else:
        return f"{status_code} - Other error."

# Uncomment to test the function
# asyncio.run(fetch_links(httpx.AsyncClient(), "https://www.razer.com/"))
from collections import deque
# Correcting syntax error and enhancing the crawl function to log every link attempt with detailed status
# Enhancing the crawl function to include more detailed status updates during URL and link checking

async def crawl(start_url: str, max_depth: int, progress_bar, status_text) -> (pd.DataFrame, pd.DataFrame, pd.DataFrame):
    async with httpx.AsyncClient() as client:
        to_visit = deque([(start_url, 0)])
        seen_urls = set()
        success_results = pd.DataFrame()
        error_results = pd.DataFrame()
        link_log = pd.DataFrame()
        total_urls_processed = 0

        while to_visit:
            current_url, current_depth = to_visit.popleft()
            if current_url in seen_urls:
                link_log = pd.concat([link_log, pd.DataFrame([{
                    "URL": current_url,
                    "Status": "Skipped - Already Seen",
                    "Depth": current_depth
                }])], ignore_index=True)
                continue

            if current_depth > max_depth:
                link_log = pd.concat([link_log, pd.DataFrame([{
                    "URL": current_url,
                    "Status": "Skipped - Beyond Max Depth",
                    "Depth": current_depth
                }])], ignore_index=True)
                continue

            seen_urls.add(current_url)
            status_text.text(f"Crawling {current_url} at depth {current_depth}...")  # Status update for crawling
            success_links_df, error_links_df = await fetch_links(client, current_url, status_text)  # Pass status_text to fetch_links
            success_results = pd.concat([success_results, success_links_df], ignore_index=True)
            error_results = pd.concat([error_results, error_links_df], ignore_index=True)
            
            link_log = pd.concat([link_log, pd.DataFrame([{
                "URL": current_url,
                "Status": "Fetched",
                "Depth": current_depth
            }])], ignore_index=True)

            total_urls_processed += 1
            progress_bar.progress(total_urls_processed / (len(seen_urls) + len(to_visit)))

            for _, row in success_links_df.iterrows():
                if row["URL"] not in seen_urls and current_depth + 1 <= max_depth:
                    to_visit.append((row["URL"], current_depth + 1))

        return success_results.drop_duplicates(subset=["URL"]), error_results.drop_duplicates(subset=["URL"]), link_log

# The fetch_links function also needs to be updated to include status updates for each link checked.

def app():
    st.title("Razer Link Checker")
    st.set_page_config(layout="wide") 
    start_url = st.text_input("Enter start URL", value="https://www.razer.com/gaming-mice/razer-orochi-v2")
    max_depth = st.number_input("Max crawl depth", value=1, min_value=1)

    if st.button("Start Checking..."):
        if "http" not in start_url:
            start_url = "https://" + start_url
        
        try:
            progress_bar = st.progress(0)
            status_text = st.empty()

            success_results, error_results, link_log = asyncio.run(crawl(start_url, max_depth, progress_bar, status_text))
            progress_bar.empty()
            status_text.empty()

            if not success_results.empty:
                st.subheader("Successful Links")
                st.dataframe(success_results)
            else:
                st.write("No successful links found.")

            if not error_results.empty:
                st.subheader("Error Links")
                st.dataframe(error_results)
            else:
                st.write("No error links encountered.")

            if not link_log.empty:
                st.subheader("Link Log")
                st.dataframe(link_log)
            else:
                st.write("No link attempts logged.")
        except Exception as e:
            st.error(f"Failed to crawl due to an error: {e}")

# This adjusted function now displays a comprehensive log of all link attempts, enhancing transparency and tracking.

if __name__ == "__main__":
    app()
