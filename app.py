import streamlit as st
import requests
import pandas as pd

st.set_page_config(page_title="RunSignup API Tester", layout="wide")

st.title("RunSignup Results API Tester")

st.sidebar.header("API Settings")

race_id = st.sidebar.text_input("Race ID", value="85066")
event_id = st.sidebar.text_input("Event ID", value="")
result_set_id = st.sidebar.text_input("Individual Result Set ID", value="644802")

api_key = st.sidebar.text_input("API Key", type="password")
api_secret = st.sidebar.text_input("API Secret", type="password")

page = st.sidebar.number_input("Page", min_value=1, value=1)
results_per_page = st.sidebar.number_input("Results per page", min_value=1, max_value=1000, value=100)

def flatten_results(data):
    rows = []

    def walk(obj):
        if isinstance(obj, dict):
            # Common place where results may appear
            if "results" in obj and isinstance(obj["results"], list):
                return obj["results"]

            for value in obj.values():
                found = walk(value)
                if found:
                    return found

        if isinstance(obj, list):
            for item in obj:
                found = walk(item)
                if found:
                    return found

        return None

    results = walk(data)

    if not results:
        return pd.DataFrame()

    for item in results:
        if isinstance(item, dict):
            rows.append(pd.json_normalize(item).iloc[0].to_dict())
        else:
            rows.append({"value": item})

    return pd.DataFrame(rows)

if st.button("Query RunSignup API"):
    if not race_id or not event_id:
        st.error("Race ID and Event ID are required.")
        st.stop()

    url = f"https://api.runsignup.com/rest/race/{race_id}/results/get-results"

    params = {
        "format": "json",
        "event_id": event_id,
        "page": page,
        "results_per_page": results_per_page,
    }

    if result_set_id:
        params["individual_result_set_id"] = result_set_id

    if api_key and api_secret:
        params["api_key"] = api_key
        params["api_secret"] = api_secret

    try:
        response = requests.get(url, params=params, timeout=30)

        st.subheader("Status")
        st.write(response.status_code)

        if response.status_code != 200:
            st.subheader("Raw Error Response")
            st.code(response.text)
            st.stop()

        data = response.json()

        st.subheader("Raw JSON")
        with st.expander("View raw response"):
            st.json(data)

        df = flatten_results(data)

        st.subheader("Results Table")

        if df.empty:
            st.warning("No results table found in the response. Check event_id, result_set_id, or auth.")
        else:
            st.dataframe(df, use_container_width=True)
            st.download_button(
                "Download CSV",
                df.to_csv(index=False),
                file_name="runsignup_results.csv",
                mime="text/csv",
            )

    except Exception as e:
        st.error(f"Request failed: {e}")
