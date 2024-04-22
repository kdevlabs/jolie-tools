import asyncio
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import pandas as pd
import streamlit as st
from collections import deque

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

def crawl(start_url: str, max_depth: int, progress_bar, status_text, max_concurrent: int = 10):

    # Initialize Streamlit session state if not already set
    if 'total_urls_processed' not in st.session_state:
        st.session_state.total_urls_processed = 0
    if 'total_urls_to_process' not in st.session_state:
        st.session_state.total_urls_to_process = 1  # Start with the initial URL

    async def async_crawl():
        async with httpx.AsyncClient() as client:
            to_visit = deque([(start_url, 0)])
            seen_urls = set()
            success_results = pd.DataFrame()
            error_results = pd.DataFrame()
            link_log = pd.DataFrame()
            semaphore = asyncio.Semaphore(max_concurrent)  # Semaphore to control concurrency

            async def process_url(current_url, current_depth):
                async with semaphore:
                    if current_url in seen_urls or current_depth > max_depth:
                        return pd.DataFrame(), pd.DataFrame()  # Return empty DataFrames instead of None
                    seen_urls.add(current_url)

                    # Local status update for this task
                    status_text.text(f"Crawling {current_url} at depth {current_depth}... ({st.session_state.total_urls_processed}/{st.session_state.total_urls_to_process})")
                    success_links_df, error_links_df = await fetch_links(client, current_url, status_text)

                    # Update the state counters
                    st.session_state.total_urls_processed += 1
                    progress_bar.progress(st.session_state.total_urls_processed / st.session_state.total_urls_to_process)

                    # Discover new URLs
                    if success_links_df is not None:
                        for _, row in success_links_df.iterrows():
                            if row["URL"] not in seen_urls and current_depth + 1 <= max_depth:
                                to_visit.append((row["URL"], current_depth + 1))
                                st.session_state.total_urls_to_process += 1
                    return success_links_df, error_links_df

            while to_visit:
                tasks = []
                while to_visit and len(tasks) < max_concurrent:
                    current_url, current_depth = to_visit.popleft()
                    tasks.append(process_url(current_url, current_depth))

                results = await asyncio.gather(*tasks)
                for success_links_df, error_links_df in results:
                    success_results = pd.concat([success_results, success_links_df], ignore_index=True)
                    error_results = pd.concat([error_results, error_links_df], ignore_index=True)
                    
                    link_log = pd.concat([link_log, pd.DataFrame([{
                        "URL": current_url,
                        "Status": "Fetched",
                        "Depth": current_depth
                    }])], ignore_index=True)

            return success_results.drop_duplicates(subset=["URL"]), error_results.drop_duplicates(subset=["URL"]), link_log

    # Run the async part of the crawl function
    return asyncio.run(async_crawl())

# This implementation assumes Streamlit is correctly set up and

def app():
    st.title("Razer Link Checker")
    
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

if __name__ == "__main__":
    st.set_page_config(layout="wide") 
    app()
