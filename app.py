import asyncio
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import pandas as pd
import streamlit as st


async def fetch_links(client: httpx.AsyncClient, url: str) -> pd.DataFrame:
    try:
        response = await client.get(url)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        parent_title = soup.title.text if soup.title else "No Title Found"

        links = [
            {
                "Status": "200 OK - Success",
                "Text": a.text.strip(),
                "URL": urljoin(url, a.get("href")),
                "Parent URL": url,
                "Parent Title": parent_title,  # Include parent title
            }
            for a in soup.find_all("a", href=True)
            if "razer.com" in urljoin(url, a.get("href"))
        ]
        return pd.DataFrame(links).drop_duplicates()

    except httpx.HTTPStatusError as e:
        error_message = get_friendly_http_error_message(e.response.status_code)
        return pd.DataFrame(
            [
                {
                    "Status": error_message,
                    "Text": "Failed to fetch",
                    "URL": "",
                    "Parent URL": url,
                    "Parent Title": "Failed to fetch",
                }
            ]
        )
    except Exception:
        return pd.DataFrame(
            [
                {
                    "Status": "Error - Could not fetch data",
                    "Text": "Failed to fetch",
                    "URL": "",
                    "Parent URL": url,
                    "Parent Title": "Failed to fetch",
                }
            ]
        )


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


async def crawl(start_url: str, max_depth: int) -> pd.DataFrame:
    async with httpx.AsyncClient() as client:
        to_visit = [(start_url, 0)]
        seen_urls = set()
        results = pd.DataFrame()

        while to_visit:
            current_url, current_depth = to_visit.pop(0)
            if current_url in seen_urls or current_depth > max_depth:
                continue

            seen_urls.add(current_url)
            with st.spinner(f"Checking link {current_url} ..."):
                links_df = await fetch_links(client, current_url)
                results = pd.concat([results, links_df], ignore_index=True)

                for _, row in links_df.iterrows():
                    if row["URL"] not in seen_urls and "razer.com" in row["URL"]:
                        to_visit.append((row["URL"], current_depth + 1))

        return results.drop_duplicates(subset=["URL"])


def app():
    st.title("Razer Link Checker")

    start_url = st.text_input("Enter start URL", value="https://www.razer.com/")
    max_depth = st.number_input("Max crawl depth", value=3, min_value=1)

    if st.button("Start Checking..."):
        results = asyncio.run(crawl(start_url, max_depth))
        if not results.empty:
            st.dataframe(results)
        else:
            st.write("No links found or all fetch attempts failed.")


if __name__ == "__main__":
    app()
