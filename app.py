import asyncio
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import pandas as pd
from collections import deque
import streamlit as st

def get_friendly_http_error_message(status_code: int) -> str:
    """
    Provides user-friendly explanations for common HTTP status codes.

    Args:
    status_code (int): The HTTP status code received from a web request.

    Returns:
    str: A non-technical explanation of the HTTP status code.
    """
    messages = {
        200: "200 OK - The request was successful.",
        301: "301 Moved Permanently - The resource has been moved permanently to a new location.",
        302: "302 Found - The resource was found, but at a different location.",
        400: "400 Bad Request - The server could not understand the request due to invalid syntax.",
        401: "401 Unauthorized - Access is denied due to invalid credentials.",
        403: "403 Forbidden - Access is denied, even with valid credentials.",
        404: "404 Not Found - The resource could not be found on the server.",
        405: "405 Method Not Allowed - The method specified in the request is not allowed.",
        408: "408 Request Timeout - The server timed out waiting for the request.",
        429: "429 Too Many Requests - You have sent too many requests in a given amount of time.",
        500: "500 Internal Server Error - The server encountered an unexpected condition.",
        502: "502 Bad Gateway - The server received an invalid response from the upstream server.",
        503: "503 Service Unavailable - The server is currently unavailable (overloaded or down).",
        504: "504 Gateway Timeout - The server did not receive a timely response from an upstream server."
    }
    return messages.get(status_code, f"{status_code} - Other error")

async def fetch_link(client: httpx.AsyncClient, url: str, status_text, parent_url="", link_text: str = "No text"):
    try:
        response = await client.get(url, follow_redirects=True)
        explain = get_friendly_http_error_message(response.status_code)
        if response.history:
            # There were redirects, handle accordingly by converting URL objects to strings
            redirects = " ===>>>  ".join([str(resp.url) for resp in response.history] + [str(response.url)])
            status_text.status(f"Redirected from {redirects}. Final URL: {response.url} - Result: {explain}")
        else:
            status_text.status(f"Checked URL [{url}] from [{parent_url}] - Result: {explain}")

        response.raise_for_status()
        return response
    except httpx.HTTPStatusError as e:
        # If an HTTP status error occurs, include the redirect history in the error message, if any
        redirects = " -> ".join([str(resp.url) for resp in e.response.history] + [str(e.request.url)])
        error_message = get_friendly_http_error_message(e.response.status_code)
        st.error(f"🚨 Error Link From Page: [{parent_url}] --- 🔥 Error Link: [{redirects}] ({url}) ---- \n \n ----- 🔥 Text: [{link_text}] --- \n 🔥 Error: {error_message}")
        return None
    except httpx.RequestError as e:
        # Handling network-related errors
        st.error(f"Network error when accessing {url}: {str(e)}")
        return None
    except Exception as e:
        # Generic error handling for any other unexpected issues
        st.error(f"An unexpected error occurred when fetching {url}: {str(e)}")
        return None


async def parse_links(client: httpx.AsyncClient, base_url: str, html_content: str, status_text):
    soup = BeautifulSoup(html_content, "html.parser")
    parent_title = soup.title.text if soup.title else "No Title Found"
    success_links = []
    error_links = []  # Separate list to collect error links

    for a in soup.find_all("a", href=True):
        link_url = urljoin(base_url, a.get("href"))
        if "razer.com" in link_url:
            link_text = a.text.strip() if a.text.strip() else (a.parent.text.strip() if a.parent else '')
            if not link_text:
                link_text = a.parent.parent.text.strip() if a.parent and a.parent.parent else 'No text available'

            response = await fetch_link(client, link_url, status_text, base_url, link_text)
            if response:
                if response.status_code == 200:
                    success_links.append({
                        "Status": f"{response.status_code} OK - Success",
                        "Text": link_text,
                        "URL": link_url,
                        "Parent URL": base_url,
                        "Parent Title": parent_title,
                    })
                else:
                    # Collect error links differently if the status code is not 200
                    error_links.append({
                        "Status": f"{response.status_code} - Error",
                        "Text": link_text,
                        "URL": link_url,
                        "Parent URL": base_url,
                        "Parent Title": parent_title,
                    })
            else:
                # Append to error links if response is None (indicating an error occurred in fetch_link)
                error_links.append({
                    "Status": "Fetch Error",
                    "Text": link_text,
                    "URL": link_url,
                    "Parent URL": base_url,
                    "Parent Title": parent_title,
                })

    return success_links, error_links


async def crawl_link(client: httpx.AsyncClient, url: str, status_text, semaphore):
    async with semaphore:
        status_text.text(f"Checking link: {url}")
        response = await fetch_link(client, url, status_text)
        if response:
            success_links, error_links = await parse_links(client, url, response.text, status_text)
            return success_links, error_links
        return [], []

async def crawl(start_url: str, max_depth: int, max_concurrent: int):
    async with httpx.AsyncClient() as client:
        semaphore = asyncio.Semaphore(max_concurrent)
        status_text = st.empty()
        progress_bar = st.progress(0)
        to_visit = deque([(start_url, 0)])
        seen_urls = set()
        all_success_links = []
        all_error_links = []

        while to_visit:
            tasks = []
            while to_visit and len(tasks) < max_concurrent:
                current_url, current_depth = to_visit.popleft()
                if current_url not in seen_urls and current_depth <= max_depth:
                    seen_urls.add(current_url)
                    tasks.append(crawl_link(client, current_url, status_text, semaphore))
            links_batch = await asyncio.gather(*tasks)
            for success_links, error_links in links_batch:
                all_success_links.extend(success_links)
                all_error_links.extend(error_links)
                for link in success_links:  # Assuming success_links contains dictionaries
                    if link["URL"] not in seen_urls:
                        to_visit.append((link["URL"], current_depth + 1))

        progress_bar.empty()
        status_text.empty()
        return pd.DataFrame(all_success_links), pd.DataFrame(all_error_links)


def app():
    st.title("Razer Link Checker")

    # Disable the form while processing to prevent multiple submissions
    with st.form(key='my_form'):
        start_url = st.text_input("Enter start URL", value="https://www.razer.com")
        max_depth = st.number_input("Max crawl depth", value=0, min_value=0)
        submit_button = st.form_submit_button("Start Checking...")

    if submit_button:
        # Disable UI components here if Streamlit supports dynamic updates in future releases
        with st.spinner('Checking in progress...'):
            success_df, error_df = asyncio.run(crawl(start_url, max_depth, 10))
            st.session_state['success_links'] = success_df
            st.session_state['error_links'] = error_df
        
        # Display results
        if not st.session_state['success_links'].empty:
            st.subheader("Successful Links")
            st.dataframe(st.session_state['success_links'])
        else:
            st.write("No successful links found.")
        
        if not st.session_state['error_links'].empty:
            st.subheader("Error Links")
            st.dataframe(st.session_state['error_links'])
        else:
            st.write("No error links encountered.")

if __name__ == "__main__":
    st.set_page_config(layout="wide")
    app()