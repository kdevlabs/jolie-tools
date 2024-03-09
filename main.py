from typing import List, Optional, Tuple
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from queue import Queue
import streamlit as st
import time
import pandas as pd


def fetch_links(url: str) -> Tuple[List[dict], Optional[str], Optional[str]]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
    }

    attempts = 0
    max_attempts = 3

    with st.status(f"Fetching link {url}..."):
        while attempts < max_attempts:
            try:
                # Using Streamlit's status to display current fetching status

                response = requests.get(url, headers=headers, timeout=5)
                response.raise_for_status()  # This will raise an error for 4xx and 5xx status codes

                # Process successful response
                soup = BeautifulSoup(response.content, "html.parser")
                title = soup.find("title").text if soup.find("title") else "No Title"
                links = [
                    {"Text": a.text.strip(), "URL": urljoin(url, a.get("href"))}
                    for a in soup.find_all("a", href=True)
                    if "razer.com" in urljoin(url, a.get("href"))
                ]

                st.dataframe(pd.DataFrame(links))

                return links, None, title
            except requests.HTTPError as http_err:
                error_message = f"HTTP error occurred: {http_err}, Status Code: {http_err.response.status_code}"
                attempts += 1
                # Update status to indicate error and retry attempt
                if attempts < max_attempts:
                    st.warning(
                        f"Error fetching {url}: {error_message}. Retrying... Attempt {attempts+1}/{max_attempts}"
                    )
                else:
                    st.error(
                        f"Error fetching {url}: {error_message}. All attempts failed."
                    )
                    return [], error_message, None
            except Exception as err:
                error_message = f"Other error occurred: {err}"
                attempts += 1
                if attempts < max_attempts:
                    st.warning(
                        f"Error fetching {url}: {error_message}. Retrying... Attempt {attempts+1}/{max_attempts}"
                    )
                else:
                    st.error(
                        f"Error fetching {url}: {error_message}. All attempts failed."
                    )
                    return [], error_message, None
            finally:
                # Wait a bit before retrying to be polite to the server and to manage rate limiting
                if attempts < max_attempts:
                    time.sleep(1)

        # If all attempts fail, return an empty list with a general error message
        return [], "Failed to fetch links after several attempts.", None


def crawl(
    start_url: str, max_depth: int, links_list: list, errors: list
) -> Tuple[List[dict], List[Tuple[str, str]]]:
    q = Queue()
    q.put((start_url, 0, "Root Page"))  # Include a default title for the root
    seen_urls = set()  # Tracks URLs that have been seen

    while not q.empty():
        current_url, current_depth, parent_title = q.get()

        if current_url not in seen_urls:
            seen_urls.add(current_url)  # Mark the current URL as seen

            links, error, current_title = fetch_links(current_url)
            if error:
                errors.append((current_url, error))
            else:
                for link in links:
                    if link["URL"] not in seen_urls:
                        links_list.append(
                            {
                                "Parent URL": current_url,
                                "Parent Title": parent_title,
                                **link,
                            }
                        )
                        if current_depth + 1 < max_depth:
                            q.put(
                                (link["URL"], current_depth + 1, current_title)
                            )  # Pass the current title as the parent title for the next level

            time.sleep(0.3)  # Be polite by sleeping before making the next request

    return links_list, errors


def app():
    st.title("Website Link Crawler")

    # Initialize or get the existing list and errors list from the state
    if "links_list" not in st.session_state:
        st.session_state["links_list"] = []
    if "errors" not in st.session_state:
        st.session_state["errors"] = []

    start_url = st.sidebar.text_input(
        "Enter start URL", value="https://www.razer.com/sitemap"
    )
    max_depth = st.sidebar.number_input(
        "Max Crawl Depth", min_value=1, max_value=10, value=1
    )

    if st.sidebar.button("Crawl!"):
        crawl(
            start_url,
            max_depth,
            st.session_state["links_list"],
            st.session_state["errors"],
        )

    # Display links
    if st.session_state["links_list"]:
        st.write(pd.DataFrame(st.session_state["links_list"]))

    # Display errors
    if st.session_state["errors"]:
        with st.expander("Errors"):
            for url, error in st.session_state["errors"]:
                st.error(f"{url}: {error}")

    if st.sidebar.button("Reset"):
        st.session_state["links_list"] = []
        st.session_state["errors"] = []
        st.experimental_rerun()


if __name__ == "__main__":
    app()
