import os
from datetime import date, timedelta

import pandas as pd
import requests
import streamlit as st


API_URL = "https://api.runsignup.com/rest/races"


st.set_page_config(page_title="RunSignup Upcoming Races", layout="wide")
st.title("RunSignup Upcoming Races Finder")
st.caption("Pull upcoming races from the RunSignup /rest/races API and export the results.")


def get_secret(name: str, default: str = "") -> str:
    """
    Reads a value from Streamlit secrets first, then environment variables.
    This keeps API credentials out of your public GitHub repo.
    """
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass

    return os.getenv(name, default)


def yn(value) -> str:
    """Convert RunSignup T/F values to Yes/No for display."""
    if value == "T":
        return "Yes"
    if value == "F":
        return "No"
    return value or ""


def flatten_race_item(item: dict) -> dict:
    """
    RunSignup returns each race inside an object like:
    {"race": {...}}
    This flattens the race fields and keeps a few useful nested address fields.
    """
    race = item.get("race", item)

    address = race.get("address") or {}

    row = {
        "race_id": race.get("race_id"),
        "name": race.get("name"),
        "next_date": race.get("next_date"),
        "next_end_date": race.get("next_end_date"),
        "city": address.get("city"),
        "state": address.get("state"),
        "zipcode": address.get("zipcode"),
        "country": address.get("country_code"),
        "timezone": race.get("timezone"),
        "registration_open": yn(race.get("is_registration_open")),
        "private_race": yn(race.get("is_private_race")),
        "draft_race": yn(race.get("is_draft_race")),
        "url": race.get("url"),
        "external_race_url": race.get("external_race_url"),
        "last_modified": race.get("last_modified"),
    }

    # If events=T is included, keep a simple summary of included events.
    events = race.get("events") or []
    if events:
        event_names = []
        event_distances = []

        for event_wrapper in events:
            event = event_wrapper.get("event", event_wrapper)
            event_name = event.get("name")
            if event_name:
                event_names.append(str(event_name))

            distance = event.get("distance")
            units = event.get("distance_units") or event.get("distance_unit")
            if distance:
                event_distances.append(f"{distance} {units or ''}".strip())

        row["events"] = "; ".join(event_names)
        row["event_distances"] = "; ".join(event_distances)

    return row


def fetch_races(
    api_key: str,
    api_secret: str,
    start_date: date,
    end_date: date | None,
    name: str,
    city: str,
    state: str,
    zipcode: str,
    radius: int,
    event_type: str,
    min_distance: float | None,
    max_distance: float | None,
    distance_units: str,
    include_events: bool,
    only_registration_open: bool,
    max_pages: int,
    results_per_page: int,
) -> pd.DataFrame:
    rows = []

    for page in range(1, max_pages + 1):
        params = {
            "format": "json",
            "api_key": api_key,
            "api_secret": api_secret,
            "start_date": start_date.isoformat(),
            "page": page,
            "results_per_page": results_per_page,
            "sort": "date ASC",
        }

        if end_date:
            params["end_date"] = end_date.isoformat()
        if name.strip():
            params["name"] = name.strip()
        if city.strip():
            params["city"] = city.strip()
        if state.strip():
            params["state"] = state.strip().upper()
        if zipcode.strip():
            params["zipcode"] = zipcode.strip()
            params["radius"] = radius
        if event_type.strip():
            params["event_type"] = event_type.strip()
        if min_distance is not None:
            params["min_distance"] = min_distance
        if max_distance is not None:
            params["max_distance"] = max_distance
        if distance_units:
            params["distance_units"] = distance_units
        if include_events:
            params["events"] = "T"

        response = requests.get(API_URL, params=params, timeout=30)

        if response.status_code != 200:
            raise RuntimeError(
                f"RunSignup returned HTTP {response.status_code}:\n\n{response.text[:2000]}"
            )

        data = response.json()
        page_races = data.get("races", [])

        if not page_races:
            break

        for item in page_races:
            row = flatten_race_item(item)
            if only_registration_open and row.get("registration_open") != "Yes":
                continue
            rows.append(row)

        if len(page_races) < results_per_page:
            break

    df = pd.DataFrame(rows)

    if not df.empty:
        df["next_date"] = pd.to_datetime(df["next_date"], errors="coerce").dt.date
        df = df.sort_values(["next_date", "state", "city", "name"], na_position="last")

    return df


with st.sidebar:
    st.header("API Credentials")

    default_api_key = get_secret("RUNSIGNUP_API_KEY")
    default_api_secret = get_secret("RUNSIGNUP_API_SECRET")

    api_key = st.text_input(
        "RunSignup API Key",
        value=default_api_key,
        type="password",
        help="Best practice: store this in Streamlit secrets as RUNSIGNUP_API_KEY.",
    )
    api_secret = st.text_input(
        "RunSignup API Secret",
        value=default_api_secret,
        type="password",
        help="Best practice: store this in Streamlit secrets as RUNSIGNUP_API_SECRET.",
    )

    st.divider()
    st.header("Search Filters")

    start_date = st.date_input("Start date", value=date.today())
    use_end_date = st.checkbox("Use end date", value=True)
    end_date = None

    if use_end_date:
        end_date = st.date_input("End date", value=date.today() + timedelta(days=365))

    name = st.text_input("Race name contains", value="")
    city = st.text_input("City", value="")
    state = st.text_input("State", value="")
    zipcode = st.text_input("Zip code", value="")
    radius = st.number_input("Radius miles, if zip code is used", min_value=1, max_value=500, value=50)

    event_type = st.text_input(
        "Event type",
        value="",
        help="Optional. Leave blank unless you know RunSignup's event_type value you want.",
    )

    distance_units = st.selectbox("Distance units", ["M", "K"], index=0)
    use_distance_filter = st.checkbox("Use distance filter", value=False)

    min_distance = None
    max_distance = None
    if use_distance_filter:
        min_distance = st.number_input("Minimum distance", min_value=0.0, value=13.0, step=0.1)
        max_distance = st.number_input("Maximum distance", min_value=0.0, value=14.0, step=0.1)

    include_events = st.checkbox("Include event details", value=True)
    only_registration_open = st.checkbox("Only show races with registration open", value=False)

    st.divider()
    st.header("Pagination")

    results_per_page = st.number_input("Results per page", min_value=1, max_value=1000, value=1000)
    max_pages = st.number_input(
        "Max pages to pull",
        min_value=1,
        max_value=50,
        value=5,
        help="RunSignup allows up to 1,000 races per page. 5 pages = up to 5,000 races.",
    )


if not api_key or not api_secret:
    st.warning(
        "Enter your RunSignup API key and secret in the sidebar, or add them to Streamlit secrets."
    )

    st.code(
        """
# .streamlit/secrets.toml
RUNSIGNUP_API_KEY = "your_api_key_here"
RUNSIGNUP_API_SECRET = "your_api_secret_here"
""".strip(),
        language="toml",
    )

    st.stop()


if st.button("Pull upcoming races", type="primary"):
    with st.spinner("Querying RunSignup..."):
        try:
            df = fetch_races(
                api_key=api_key,
                api_secret=api_secret,
                start_date=start_date,
                end_date=end_date,
                name=name,
                city=city,
                state=state,
                zipcode=zipcode,
                radius=radius,
                event_type=event_type,
                min_distance=min_distance,
                max_distance=max_distance,
                distance_units=distance_units,
                include_events=include_events,
                only_registration_open=only_registration_open,
                max_pages=max_pages,
                results_per_page=results_per_page,
            )
        except Exception as exc:
            st.error("The RunSignup request failed.")
            st.code(str(exc))
            st.stop()

    st.success(f"Pulled {len(df):,} race rows.")

    if df.empty:
        st.info("No races matched your filters.")
    else:
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "url": st.column_config.LinkColumn("RunSignup URL"),
                "external_race_url": st.column_config.LinkColumn("External URL"),
            },
        )

        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download races CSV",
            data=csv,
            file_name="runsignup_upcoming_races.csv",
            mime="text/csv",
        )
else:
    st.info("Set your filters, then click **Pull upcoming races**.")
