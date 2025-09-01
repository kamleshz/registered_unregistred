# app.py
import datetime as dt
import io
import json
import ssl
from typing import List, Dict

import pandas as pd
import requests
import streamlit as st

# -----------------------------
# Streamlit page setup
# -----------------------------
st.set_page_config(page_title="CPCB EPR Dashboard Scraper", page_icon="♻️", layout="wide")
st.title("♻️ CPCB EPR Dashboard Scraper")
st.caption("Fetches PIBO application details by Applicant Type and Status from CPCB EPR Plastic dashboard API.")

# -----------------------------
# Networking setup (suppress SSL warnings since verify=False)
# -----------------------------
requests.packages.urllib3.disable_warnings()  # type: ignore[attr-defined]

# -----------------------------
# Constants & helpers
# -----------------------------
API_URL = "https://eprplastic.cpcb.gov.in/epr/api/v1.0/pibo/fetch_pibo_application_details_by_status"

APPLICANT_TYPES = ["Brand Owner", "Producer", "Importer"]
STATUSES_UI = ["In Process", "Not Approved", "Registered"]

STATUS_MAP = {
    "In Process": ("InProgress", "In Process"),
    "Not Approved": ("notApproved", "Not Approved"),
    "Registered": ("registered", "Registered"),
}

PREFIX_MAP = {
    "Brand Owner": "BO-",
    "Producer": "Pro-",
    "Importer": "Imp-",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Content-Type": "application/json",
}

def build_payload(status_api: str, status_text: str, applicant_type: str, count_value: int) -> str:
    return json.dumps(
        {
            "status": status_api,
            "countValue": int(count_value),
            "statusText": status_text,
            "applicantType": applicant_type,
        }
    )

def tidy_rows(rows: List[Dict], category_label: str) -> List[Dict]:
    out = []
    for row in rows:
        out.append(
            {
                "Name": row.get("company", "") or "",
                "Address": row.get("address", "") or "",
                "Email": row.get("email", "") or "",
                "Category": category_label,
            }
        )
    return out

@st.cache_data(show_spinner=False)
def scrape(selected_types: List[str], selected_statuses: List[str], count_value: int) -> pd.DataFrame:
    collected: List[Dict] = []

    total_jobs = len(selected_types) * len(selected_statuses)
    job_i = 0

    for applicant in selected_types:
        for status_ui in selected_statuses:
            job_i += 1
            status_api, status_text = STATUS_MAP[status_ui]
            cat_prefix = PREFIX_MAP[applicant]
            category_label = f"{cat_prefix}{status_text}"

            payload = build_payload(status_api, status_text, applicant, count_value)

            try:
                resp = requests.post(
                    API_URL,
                    headers=HEADERS,
                    data=payload,
                    verify=False,   # keeping this to match your original code
                    timeout=60,
                )
                resp.raise_for_status()
                data = resp.json()

                # defensive parsing
                rows = (
                    data.get("data", {})
                    .get("tableData", {})
                    .get("bodyContent", [])
                )

                collected.extend(tidy_rows(rows, category_label))

            except requests.RequestException as e:
                # Insert a row noting the error so you still see context in the table
                collected.append(
                    {
                        "Name": "",
                        "Address": "",
                        "Email": "",
                        "Category": f"{category_label} (ERROR: {e})",
                    }
                )

    df = pd.DataFrame(collected, columns=["Name", "Address", "Email", "Category"])
    # De-duplicate if needed
    df = df.drop_duplicates().reset_index(drop=True)
    return df

def to_excel_bytes(df: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        df.to_excel(writer, sheet_name="Scraped", index=False)
    return buffer.getvalue()

# -----------------------------
# Sidebar controls
# -----------------------------
with st.sidebar:
    st.header("Filters")
    sel_types = st.multiselect("Applicant Type", APPLICANT_TYPES, default=APPLICANT_TYPES)
    sel_status = st.multiselect("Status", STATUSES_UI, default=STATUSES_UI)
    count_value = st.number_input("Max records per API call (countValue)", min_value=1, max_value=200000, value=100000, step=1000)

    st.markdown("---")
    run = st.button("🚀 Scrape Now", use_container_width=True)

# -----------------------------
# Main area
# -----------------------------
if run:
    if not sel_types or not sel_status:
        st.warning("Please select at least one **Applicant Type** and one **Status**.")
        st.stop()

    with st.spinner("Fetching data from CPCB API..."):
        df = scrape(sel_types, sel_status, count_value)

    # KPIs
    left, mid, right = st.columns(3)
    with left:
        st.metric("Total Rows", f"{len(df):,}")
    with mid:
        st.metric("Unique Companies", f"{df['Name'].nunique():,}")
    with right:
        st.metric("Downloaded On", dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    st.markdown("### Preview")
    st.dataframe(df, use_container_width=True, height=480)

    # Downloads
    st.markdown("### Download")
    excel_bytes = to_excel_bytes(df)
    st.download_button(
        label="⬇️ Download Excel",
        data=excel_bytes,
        file_name="Scraped_dashboard.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    st.download_button(
        label="⬇️ Download CSV",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name="Scraped_dashboard.csv",
        mime="text/csv",
    )

else:
    st.info("Set your filters in the sidebar and click **Scrape Now** to start.")

# -----------------------------
# Footnote
# -----------------------------
st.caption(
    "Note: This tool calls an official CPCB endpoint. Keep the request rate reasonable. "
    "SSL verification is disabled here to mirror your script; enable certificate verification in production if possible."
)
