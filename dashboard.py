"""
Policy Coherence Dashboard
Reads from policy_coherence.runs and policy_coherence.findings in Supabase.
"""

import json
import os
import streamlit as st
import pandas as pd
from datetime import datetime

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Policy Coherence Tool · IM2026",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Styles ─────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── Base ── */
[data-testid="stAppViewContainer"] { background: #f5f6f8; }
[data-testid="stSidebar"]          { background: #ffffff; border-right: 1px solid #e2e5ea; }

/* ── Risk badges ── */
.badge {
    display: inline-block;
    padding: 2px 9px;
    border-radius: 3px;
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
}
.badge-high   { background: #fde8e8; color: #9b1c1c; border: 1px solid #f5c6c6; }
.badge-medium { background: #fef3e2; color: #92400e; border: 1px solid #fbd89c; }
.badge-low    { background: #e8f0fe; color: #1e40af; border: 1px solid #bfcffa; }

/* ── Type pill ── */
.type-pill {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 3px;
    font-size: 0.73rem;
    font-weight: 500;
    background: #eef0f3;
    color: #4b5563;
    border: 1px solid #d1d5db;
    margin-left: 6px;
}

/* ── Finding cards ── */
.card {
    background: #ffffff;
    border: 1px solid #e2e5ea;
    border-radius: 6px;
    padding: 18px 22px 14px 22px;
    margin-bottom: 10px;
    border-left-width: 4px;
}
.card-high   { border-left-color: #dc2626; }
.card-medium { border-left-color: #d97706; }
.card-low    { border-left-color: #3b82f6; }

/* ── Card title ── */
.card-title {
    font-size: 0.97rem;
    font-weight: 600;
    color: #111827;
    margin: 8px 0 6px 0;
    line-height: 1.4;
    white-space: normal;
    word-wrap: break-word;
    overflow-wrap: break-word;
}

/* ── Card summary (collapsed) ── */
.card-summary {
    font-size: 0.88rem;
    color: #4b5563;
    line-height: 1.55;
    margin-bottom: 10px;
}

/* ── Source block ── */
.source-block {
    font-size: 0.8rem;
    color: #6b7280;
    border-top: 1px solid #f0f0f0;
    padding-top: 10px;
    margin-top: 10px;
    line-height: 1.6;
}
.source-label {
    font-weight: 600;
    color: #374151;
    text-transform: uppercase;
    font-size: 0.7rem;
    letter-spacing: 0.05em;
}

/* ── Excerpt block (expanded) ── */
.excerpt {
    background: #f8f9fa;
    border-left: 3px solid #d1d5db;
    padding: 8px 12px;
    font-size: 0.8rem;
    color: #374151;
    font-style: italic;
    margin: 4px 0 8px 0;
    border-radius: 0 4px 4px 0;
    line-height: 1.5;
}

/* ── Detail / recommendation sections ── */
.section-label {
    font-size: 0.7rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #6b7280;
    margin: 14px 0 4px 0;
}
.section-body {
    font-size: 0.87rem;
    color: #1f2937;
    line-height: 1.6;
    margin: 0 0 4px 0;
}

/* ── Scope tag ── */
.scope-tag {
    font-size: 0.73rem;
    color: #6b7280;
    margin-left: 8px;
}

/* ── Empty state ── */
.empty-state {
    text-align: center;
    padding: 48px 24px;
    color: #9ca3af;
    font-size: 0.92rem;
}
</style>
""", unsafe_allow_html=True)


# ── Constants ──────────────────────────────────────────────────────────────────
RISK_ORDER   = {"High": 0, "Medium": 1, "Low": 2}
RISK_COLOURS = {"High": "high", "Medium": "medium", "Low": "low"}

TYPE_LABELS = {
    "contradiction":  "Contradiction",
    "omission":       "Omission",
    "terminology":    "Terminology",
    "structural_gap": "Structural Gap",
    "broken_link":    "Broken Link",
    "stale_data":     "Stale Data",
}

SCOPE_LABELS = {
    "cross_agency":  "Cross-agency",
    "within_agency": "Within agency",
}


# ── Supabase connection ────────────────────────────────────────────────────────
@st.cache_resource
def get_supabase():
    try:
        from supabase import create_client
        url = st.secrets.get("SUPABASE_URL", os.environ.get("SUPABASE_URL", ""))
        key = st.secrets.get("SUPABASE_KEY", os.environ.get("SUPABASE_KEY", ""))
        if url and key:
            return create_client(url, key)
    except Exception:
        pass
    return None


# ── Runs query ─────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def load_runs() -> pd.DataFrame:
    """
    Fetch all complete runs from policy_coherence.runs, newest first.
    Returns an empty DataFrame if none found or connection fails.
    """
    client = get_supabase()
    if not client:
        return pd.DataFrame()
    try:
        resp = (
            client
            .schema("policy_coherence")
            .table("runs")
            .select("id, department_name, policy_name, status, created_at")
            .eq("status", "complete")
            .order("created_at", desc=True)
            .execute()
        )
        if resp.data:
            return pd.DataFrame(resp.data)
    except Exception as e:
        st.warning(f"Could not load runs: {e}")
    return pd.DataFrame()


def run_label(row) -> str:
    """
    Build a human-readable dropdown label for a run.
    Example: "Farm Household Allowance — DAFF (21 Jun 2026)"
    """
    policy = row.get("policy_name") or "Unknown policy"
    dept   = row.get("department_name") or "Unknown department"
    try:
        ts = datetime.fromisoformat(str(row.get("created_at", "")).replace("Z", "+00:00"))
        date_str = ts.strftime("%d %b %Y")
    except Exception:
        date_str = "unknown date"
    return f"{policy} — {dept} ({date_str})"


# ── Findings query ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def load_findings(run_id: str) -> pd.DataFrame:
    """
    Fetch all findings for a specific run_id from policy_coherence.findings.
    run_id is part of the cache key, so switching runs fetches fresh data
    without evicting cached results for other runs.
    """
    client = get_supabase()
    if not client:
        return pd.DataFrame()
    try:
        resp = (
            client
            .schema("policy_coherence")
            .table("findings")
            .select(
                "id, run_id, risk_level, finding_type, comparison_scope, "
                "finding_text, source_chain, created_at"
            )
            .eq("run_id", run_id)
            .execute()
        )
        if resp.data:
            return _parse_rows(resp.data)
    except Exception as e:
        st.warning(f"Could not load findings: {e}")
    return pd.DataFrame()


# ── Parsing helpers ────────────────────────────────────────────────────────────
def _safe_json(val, fallback):
    """Parse a value that may already be a dict, a JSON string, or None."""
    if val is None:
        return fallback
    if isinstance(val, dict):
        return val
    try:
        return json.loads(val)
    except Exception:
        return fallback


def _label_from_url(url: str) -> str:
    """
    Derive a human-readable source label from a URL filename.
    Known long filenames are mapped to short labels.
    Falls back to title-cased filename stem, then domain.
    """
    if not url:
        return ""

    KNOWN = {
        "farm-household-allowance-guidelines-effective-from-1-july-2024": "FHA Guidelines",
        "fha-program-factsheet":           "FHA Program Factsheet",
        "fha-assets-test-factsheet":       "FHA Assets Test Factsheet",
        "fha-income-test-factsheet":       "FHA Income Test Factsheet",
        "guide-farm-financial-assessment": "Farm Financial Assessment Guide",
    }

    from urllib.parse import urlparse
    import os as _os
    parsed   = urlparse(url)
    basename = _os.path.basename(parsed.path)
    stem     = _os.path.splitext(basename)[0].lower()

    if stem in KNOWN:
        return KNOWN[stem]
    if stem:
        return stem.replace("-", " ").replace("_", " ").title()
    return parsed.netloc or url


def _replace_chunk_labels(text: str, label_a: str, label_b: str) -> str:
    """
    Replace LLM-generated Chunk/Source A/B references with readable
    labels derived from source URLs.
    """
    if label_a:
        text = text.replace("Chunk A", label_a).replace("chunk A", label_a)
        text = text.replace("Source A", label_a).replace("source A", label_a)
    if label_b:
        text = text.replace("Chunk B", label_b).replace("chunk B", label_b)
        text = text.replace("Source B", label_b).replace("source B", label_b)
    return text


def _parse_rows(rows: list) -> pd.DataFrame:
    records = []
    for r in rows:
        ft = _safe_json(r.get("finding_text"), {})
        sc = _safe_json(r.get("source_chain"),  {})

        src_a = sc.get("source_a", {})
        src_b = sc.get("source_b", {})

        # agency field not populated by scraper — derive labels from URLs
        label_a  = _label_from_url(src_a.get("source_url", ""))
        label_b  = _label_from_url(src_b.get("source_url", ""))
        agency_a = src_a.get("agency", "") or label_a
        agency_b = src_b.get("agency", "") or label_b

        summary_full = _replace_chunk_labels(ft.get("summary", ""),       label_a, label_b)
        detail       = _replace_chunk_labels(ft.get("detail", ""),        label_a, label_b)
        recommendation = _replace_chunk_labels(ft.get("recommendation", ""), label_a, label_b)

        # First sentence (up to 160 chars) as card title; rest as collapsed body
        dot = summary_full.find(". ")
        if dot != -1 and dot < 160:
            title   = summary_full[:dot + 1].strip()
            summary = summary_full[dot + 2:].strip()
        else:
            title   = summary_full.strip()
            summary = ""

        records.append({
            "id":               r.get("id"),
            "risk_level":       (r.get("risk_level") or "").capitalize(),
            "finding_type":     r.get("finding_type", ""),
            "comparison_scope": r.get("comparison_scope", ""),
            "title":            title,
            "summary":          summary,
            "detail":           detail,
            "recommendation":   recommendation,
            "agency_a":         agency_a,
            "agency_b":         agency_b,
            "url_a":            src_a.get("source_url", ""),
            "url_b":            src_b.get("source_url", ""),
            "excerpt_a":        src_a.get("text_excerpt", ""),
            "excerpt_b":        src_b.get("text_excerpt", ""),
            "created_at":       r.get("created_at", ""),
        })

    df = pd.DataFrame(records)
    if not df.empty:
        df["_risk_order"] = df["risk_level"].map(RISK_ORDER).fillna(9)
        df = df.sort_values("_risk_order").reset_index(drop=True)
    return df


# ── Rendering helpers ──────────────────────────────────────────────────────────
def badge(level: str) -> str:
    cls = RISK_COLOURS.get(level, "low")
    return f'<span class="badge badge-{cls}">{level}</span>'


def type_pill(t: str) -> str:
    label = TYPE_LABELS.get(t, t.replace("_", " ").title())
    return f'<span class="type-pill">{label}</span>'


def scope_tag(s: str) -> str:
    label = SCOPE_LABELS.get(s, s.replace("_", " ").title())
    return f'<span class="scope-tag">· {label}</span>'


def card_css(level: str) -> str:
    return f'card card-{level.lower()}'


def render_url(url: str, label: str) -> str:
    if url:
        return f'<a href="{url}" target="_blank" style="color:#2563eb;font-size:0.8rem;">{label} ↗</a>'
    return f'<span style="color:#9ca3af;font-size:0.8rem;">{label} (no URL)</span>'


def render_finding(row, idx: int):
    level = row["risk_level"]
    key   = f"expand_{row['id']}_{idx}"

    if key not in st.session_state:
        st.session_state[key] = False

    # Card header — always visible
    summary_html = f'<p class="card-summary">{row["summary"]}</p>' if row["summary"] else ""
    st.markdown(f"""
<div class="{card_css(level)}">
  <div style="display:flex;align-items:center;gap:4px;margin-bottom:8px;">
    {badge(level)}{type_pill(row['finding_type'])}{scope_tag(row['comparison_scope'])}
  </div>
  <p class="card-title">{row['title']}</p>
  {summary_html}
</div>
""", unsafe_allow_html=True)

    # Expand toggle
    col_toggle, col_spacer = st.columns([1, 8])
    with col_toggle:
        btn_label = "▲ Less" if st.session_state[key] else "▼ Detail"
        if st.button(btn_label, key=f"btn_{key}", use_container_width=True):
            st.session_state[key] = not st.session_state[key]
            st.rerun()

    # Expanded detail view
    if st.session_state[key]:
        with st.container():
            if row["detail"]:
                st.markdown('<p class="section-label">Detail</p>', unsafe_allow_html=True)
                st.markdown(f'<p class="section-body">{row["detail"]}</p>', unsafe_allow_html=True)

            if row["recommendation"]:
                st.markdown('<p class="section-label">Recommendation</p>', unsafe_allow_html=True)
                st.markdown(f'<p class="section-body">{row["recommendation"]}</p>', unsafe_allow_html=True)

            # Sources
            src_label_a = row["agency_a"] or "Source A"
            src_label_b = row["agency_b"] or "Source B"
            st.markdown(
                '<p class="section-label" style="margin-top:18px;">Sources compared</p>',
                unsafe_allow_html=True,
            )
            c1, c2 = st.columns(2)
            with c1:
                excerpt_html = f"<div class='excerpt'>{row['excerpt_a']}</div>" if row["excerpt_a"] else ""
                st.markdown(f"""
<div class="source-block">
  <span class="source-label">{src_label_a}</span><br>
  {render_url(row['url_a'], row['url_a'] or 'No URL recorded')}
  {excerpt_html}
</div>
""", unsafe_allow_html=True)
            with c2:
                excerpt_html = f"<div class='excerpt'>{row['excerpt_b']}</div>" if row["excerpt_b"] else ""
                st.markdown(f"""
<div class="source-block">
  <span class="source-label">{src_label_b}</span><br>
  {render_url(row['url_b'], row['url_b'] or 'No URL recorded')}
  {excerpt_html}
</div>
""", unsafe_allow_html=True)

    st.markdown("<div style='margin-bottom:4px'></div>", unsafe_allow_html=True)


# ── Load runs ──────────────────────────────────────────────────────────────────
connected = get_supabase() is not None
conn_badge = (
    '<span style="background:#d1fae5;color:#065f46;padding:2px 8px;'
    'border-radius:3px;font-size:0.75rem;font-weight:600;">● Supabase connected</span>'
    if connected else
    '<span style="background:#fee2e2;color:#991b1b;padding:2px 8px;'
    'border-radius:3px;font-size:0.75rem;font-weight:600;">✕ Not connected</span>'
)

df_runs = load_runs()

# ── Sidebar — run selector and risk filter (before findings load) ──────────────
with st.sidebar:
    st.markdown("### Run")

    if df_runs.empty:
        st.warning("No complete runs found.")
        st.stop()

    run_labels  = [run_label(row) for _, row in df_runs.iterrows()]
    sel_run_idx = st.selectbox(
        "Select run",
        options=range(len(run_labels)),
        format_func=lambda i: run_labels[i],
        index=0,
        label_visibility="collapsed",
    )

    selected_run      = df_runs.iloc[sel_run_idx]
    selected_run_id   = selected_run["id"]
    selected_policy   = selected_run.get("policy_name") or "Unknown policy"
    selected_dept     = selected_run.get("department_name") or "Unknown department"

    st.divider()
    st.markdown("### Filters")

    sel_risk = st.multiselect(
        "Risk level",
        options=["High", "Medium", "Low"],
        default=["High", "Medium"],
    )
    # Type and scope options are populated after findings load (below)
    # Placeholders updated after df_findings is available
    

    st.divider()
    if st.button("🔄 Refresh data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.markdown(
        "<p style='font-size:0.75rem;color:#9ca3af;margin-top:12px;'>"
        "Low risk findings are hidden by default. "
        "Select 'Low' above to include them.</p>",
        unsafe_allow_html=True,
    )

# ── Load findings for selected run ────────────────────────────────────────────
df_all = load_findings(selected_run_id)

# ── Header ────────────────────────────────────────────────────────────────────
h1, h2 = st.columns([6, 1])
with h1:
    st.markdown("## 🔍 Policy Coherence Tool - IM2026")
    st.caption("IM2026 · Build a Bureaucrat Bot")
    st.caption(
        f"{selected_policy} · {selected_dept} · "
        f"Refreshed {datetime.now().strftime('%d %b %Y %H:%M')}"
    )
with h2:
    st.markdown(
        f"<div style='padding-top:18px;text-align:right'>{conn_badge}</div>",
        unsafe_allow_html=True,
    )

if df_all.empty:
    st.info("No findings recorded for this run.")
    st.stop()

# Split broken links from regular findings
is_broken   = df_all["finding_type"] == "broken_link"
df_findings = df_all[~is_broken].copy()
# ── Sidebar — type and scope filters (after findings load) ────────────────────
with st.sidebar:
    available_types = sorted(df_findings["finding_type"].dropna().unique().tolist())
    sel_types = st.multiselect(
        "Finding type",
        options=available_types,
        default=available_types,
        format_func=lambda t: TYPE_LABELS.get(t, t.replace("_", " ").title()),
        key=f"types_{selected_run_id}",
    )

    available_scopes = sorted(df_findings["comparison_scope"].dropna().unique().tolist())
    sel_scopes = st.multiselect(
        "Scope",
        options=available_scopes,
        default=available_scopes,
        format_func=lambda s: SCOPE_LABELS.get(s, s.replace("_", " ").title()),
        key=f"scopes_{selected_run_id}",
    )

    st.divider()
    if st.button("🔄 Refresh data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.markdown(
        "<p style='font-size:0.75rem;color:#9ca3af;margin-top:12px;'>"
        "Low risk findings are hidden by default. "
        "Select 'Low' above to include them.</p>",
        unsafe_allow_html=True,
    )
df_broken   = df_all[is_broken].copy()


# ── Summary metrics ───────────────────────────────────────────────────────────
n_high   = (df_findings["risk_level"] == "High").sum()
n_medium = (df_findings["risk_level"] == "Medium").sum()
n_low    = (df_findings["risk_level"] == "Low").sum()
n_total  = len(df_findings)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Total findings", n_total)
m2.metric("🔴 High risk",   n_high)
m3.metric("🟠 Medium risk", n_medium)
m4.metric("🔵 Low risk",    n_low)

st.divider()

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_main, tab_broken = st.tabs([
    f"Findings ({n_total})",
    f"Broken Links ({len(df_broken)})",
])

# ── Main findings tab ─────────────────────────────────────────────────────────
with tab_main:
    mask = (
        df_findings["risk_level"].isin(sel_risk) &
        df_findings["finding_type"].isin(sel_types) &
        df_findings["comparison_scope"].isin(sel_scopes)
    )
    df_view = df_findings[mask]

    if df_view.empty:
        st.markdown(
            "<div class='empty-state'>No findings match the selected filters.</div>",
            unsafe_allow_html=True,
        )
    else:
        n_filtered = len(df_view)
        n_hidden   = n_total - n_filtered
        caption    = f"**{n_filtered} finding{'s' if n_filtered != 1 else ''}**"
        if n_hidden > 0:
            caption += f" · {n_hidden} hidden by filters"
        st.markdown(caption)
        st.markdown("")

        for i, (_, row) in enumerate(df_view.iterrows()):
            render_finding(row, i)

# ── Broken links tab ──────────────────────────────────────────────────────────
with tab_broken:
    if df_broken.empty:
        st.markdown(
            "<div class='empty-state'>No broken links recorded.</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"**{len(df_broken)} broken link{'s' if len(df_broken) != 1 else ''}** detected."
        )
        st.markdown("")
        for i, (_, row) in enumerate(df_broken.iterrows()):
            render_finding(row, i + 1000)
