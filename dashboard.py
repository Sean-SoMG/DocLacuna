"""
Policy Coherence Dashboard — IM2026
Reads from policy_coherence.runs and policy_coherence.findings in Supabase.
"""

import json
import os
import sys
import streamlit as st
import pandas as pd
from datetime import datetime

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Doc Lacuna · IM2026",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Styles ─────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stAppViewContainer"] { background: #f5f6f8; }
[data-testid="stSidebar"]          { background: #ffffff; border-right: 1px solid #e2e5ea; }

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

.card-summary {
    font-size: 0.88rem;
    color: #4b5563;
    line-height: 1.55;
    margin-bottom: 10px;
}

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

.scope-tag {
    font-size: 0.73rem;
    color: #6b7280;
    margin-left: 8px;
}

.empty-state {
    text-align: center;
    padding: 48px 24px;
    color: #9ca3af;
    font-size: 0.92rem;
}

.welcome-box {
    border: 1px solid #e2e5ea;
    border-radius: 8px;
    background: #ffffff;
    padding: 40px 48px;
    max-width: 620px;
    margin: 60px auto 0 auto;
    text-align: center;
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

KNOWN_LABELS = {
    "farm-household-allowance-guidelines-effective-from-1-july-2024": "FHA Guidelines",
    "fha-program-factsheet":           "FHA Program Factsheet",
    "fha-assets-test-factsheet":       "FHA Assets Test Factsheet",
    "fha-income-test-factsheet":       "FHA Income Test Factsheet",
    "guide-farm-financial-assessment": "Farm Financial Assessment Guide",
}

DEFAULT_RUN_ID = "05c02529-9e82-4696-b502-90454602a26c"

# Session state keys
_KEY_LOADED_RUN_ID = "loaded_run_id"   # set ONLY by the View findings button
_KEY_LOADED_POLICY = "loaded_policy"
_KEY_LOADED_DEPT   = "loaded_dept"
_KEY_FINDINGS_DF   = "findings_df"     # cached DataFrame — survives all rerenders


# ── Supabase — fresh client per call, never cached ────────────────────────────
def make_supabase():
    try:
        from supabase import create_client
        url = st.secrets.get("SUPABASE_URL", "")
        key = st.secrets.get("SUPABASE_KEY", "")
        if url and key:
            return create_client(url, key)
    except Exception as e:
        print(f"make_supabase: {e}", file=sys.stderr)
    return None


# ── Data loading ───────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def load_runs() -> pd.DataFrame:
    client = make_supabase()
    if not client:
        print("load_runs: no client", file=sys.stderr)
        return pd.DataFrame()
    try:
        # First: get all distinct run_ids that have at least one finding
        runs_with_findings = (
            client
            .schema("policy_coherence")
            .table("findings")
            .select("run_id")
            .execute()
        )
        if not runs_with_findings.data:
            print("load_runs: no findings in database", file=sys.stderr)
            return pd.DataFrame()

        valid_run_ids = list({row["run_id"] for row in runs_with_findings.data})

        # Second: fetch complete runs and filter to only those with findings
        resp = (
            client
            .schema("policy_coherence")
            .table("runs")
            .select("id, department_name, policy_name, status, created_at, total_cost_usd")
            .eq("status", "complete")
            .in_("id", valid_run_ids)
            .order("created_at", desc=True)
            .execute()
        )
        if resp.data:
            return pd.DataFrame(resp.data)
        print("load_runs: no complete runs with findings", file=sys.stderr)
    except Exception as e:
        import traceback
        print(f"load_runs: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
    return pd.DataFrame()


def fetch_findings(run_id: str) -> pd.DataFrame:
    """
    Fetch findings from Supabase for a given run_id.
    NOT decorated with @st.cache_data — called only from the button handler,
    so caching is managed via st.session_state[_KEY_FINDINGS_DF] instead.
    This means the call is never triggered by a rerender.
    """
    client = make_supabase()
    if not client:
        print(f"fetch_findings: no client for run_id={run_id}", file=sys.stderr)
        return pd.DataFrame()
    try:
        print(f"fetch_findings: querying run_id={run_id}", file=sys.stderr)
        resp = (
            client
            .schema("policy_coherence")
            .table("findings")
            .select(
                "id, run_id, risk_level, finding_type, comparison_scope, "
                "finding_text, source_chain, pass3_outcome, "
                "jurisdiction_a, jurisdiction_b, created_at"
            )
            .eq("run_id", run_id)
            .eq("is_duplicate", False)
            .execute()
        )
        if resp.data is None:
            print(f"fetch_findings: resp.data is None for run_id={run_id}", file=sys.stderr)
            return pd.DataFrame()
        if len(resp.data) == 0:
            print(f"fetch_findings: 0 rows for run_id={run_id}", file=sys.stderr)
            return pd.DataFrame()
        print(f"fetch_findings: {len(resp.data)} rows for run_id={run_id}", file=sys.stderr)
        return _parse_rows(resp.data)
    except Exception as e:
        import traceback
        print(f"fetch_findings: exception for run_id={run_id}: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
    return pd.DataFrame()


# ── Parsing helpers ────────────────────────────────────────────────────────────
def _safe_json(val, fallback):
    if val is None:
        return fallback
    if isinstance(val, dict):
        return val
    try:
        return json.loads(val)
    except Exception:
        return fallback


def _label_from_url(url: str) -> str:
    if not url:
        return ""
    from urllib.parse import urlparse
    import os as _os
    parsed   = urlparse(url)
    basename = _os.path.basename(parsed.path)
    stem     = _os.path.splitext(basename)[0].lower()
    if stem in KNOWN_LABELS:
        return KNOWN_LABELS[stem]
    if stem:
        return stem.replace("-", " ").replace("_", " ").title()
    return parsed.netloc or url


def _replace_labels(text: str, a: str, b: str) -> str:
    for find, replace in [
        ("Chunk A", a), ("chunk A", a), ("Source A", a), ("source A", a),
        ("Chunk B", b), ("chunk B", b), ("Source B", b), ("source B", b),
    ]:
        if replace:
            text = text.replace(find, replace)
    return text


def _parse_rows(rows: list) -> pd.DataFrame:
    records = []
    for r in rows:
        ft = _safe_json(r.get("finding_text"), {})
        sc = _safe_json(r.get("source_chain"),  {})
        sa = sc.get("source_a", {})
        sb = sc.get("source_b", {})

        la = _label_from_url(sa.get("source_url", ""))
        lb = _label_from_url(sb.get("source_url", ""))
        aa = sa.get("agency", "") or la
        ab = sb.get("agency", "") or lb

        raw    = _replace_labels(ft.get("summary", ""),        la, lb)
        detail = _replace_labels(ft.get("detail", ""),         la, lb)
        rec    = _replace_labels(ft.get("recommendation", ""), la, lb)

        dot = raw.find(". ")
        if dot != -1 and dot < 160:
            title   = raw[:dot + 1].strip()
            summary = raw[dot + 2:].strip()
        else:
            title   = raw.strip()
            summary = ""

        records.append({
            "id":               r.get("id"),
            "risk_level":       (r.get("risk_level") or "").capitalize(),
            "finding_type":     r.get("finding_type", ""),
            "comparison_scope": r.get("comparison_scope", ""),
            "title":            title,
            "summary":          summary,
            "detail":           detail,
            "recommendation":   rec,
            "agency_a":         aa,
            "agency_b":         ab,
            "url_a":            sa.get("source_url", ""),
            "url_b":            sb.get("source_url", ""),
            "excerpt_a":        sa.get("text_excerpt", ""),
            "excerpt_b":        sb.get("text_excerpt", ""),
            "pass3_outcome":    r.get("pass3_outcome", ""),
            "jurisdiction_a":   r.get("jurisdiction_a", ""),
            "jurisdiction_b":   r.get("jurisdiction_b", ""),
        })

    df = pd.DataFrame(records)
    if not df.empty:
        df["_risk_order"] = df["risk_level"].map(RISK_ORDER).fillna(9)
        df = df.sort_values("_risk_order").reset_index(drop=True)
    return df


# ── Filter helper ──────────────────────────────────────────────────────────────
def apply_filter(df: pd.DataFrame, col: str, selected: list) -> pd.Series:
    """Empty selection = no filter applied (show all rows)."""
    if not selected:
        return pd.Series(True, index=df.index)
    return df[col].isin(selected)


def apply_jurisdiction_filter(df: pd.DataFrame, selected: list) -> pd.Series:
    """
    A finding passes if jurisdiction_a OR jurisdiction_b is in the selected list.
    Empty selection = no filter (show all).
    """
    if not selected:
        return pd.Series(True, index=df.index)
    mask_a = df["jurisdiction_a"].isin(selected)
    mask_b = df["jurisdiction_b"].isin(selected)
    return mask_a | mask_b


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

def pass3_pill(outcome: str) -> str:
    if not outcome or outcome == "skipped":
        return ""
    label = outcome.replace("_", " ").title()
    return (
        f'<span style="display:inline-block;padding:2px 8px;border-radius:3px;'
        f'font-size:0.73rem;font-weight:500;background:#eef0f3;color:#4b5563;'
        f'border:1px solid #d1d5db;margin-left:6px;">P3: {label}</span>'
    )


def jurisdiction_tag(ja: str, jb: str) -> str:
    values = [v.strip() for v in [ja, jb] if v and v.strip()]
    if not values:
        return ""
    unique = list(dict.fromkeys(values))
    label  = " · ".join(unique)
    return (
        f'<span style="font-size:0.73rem;color:#9ca3af;margin-left:8px;">'
        f'{label}</span>'
    )

def render_url(url: str) -> str:
    if url:
        short = url.replace("https://", "").replace("http://", "")
        return f'<a href="{url}" target="_blank" style="color:#2563eb;font-size:0.8rem;">{short} ↗</a>'
    return '<span style="color:#9ca3af;font-size:0.8rem;">No URL recorded</span>'


def render_finding(row, idx: int):
    level = row["risk_level"]
    key   = f"expand_{row['id']}_{idx}"

    if key not in st.session_state:
        st.session_state[key] = False

    summary_html = f'<p class="card-summary">{row["summary"]}</p>' if row["summary"] else ""
    st.markdown(f"""
<div class="card card-{level.lower()}">
  <div style="display:flex;align-items:center;gap:4px;margin-bottom:8px;flex-wrap:wrap;">
    {badge(level)}{type_pill(row['finding_type'])}{pass3_pill(row.get('pass3_outcome',''))}{jurisdiction_tag(row.get('jurisdiction_a',''), row.get('jurisdiction_b',''))}{scope_tag(row['comparison_scope'])}
  </div>
  <p class="card-title">{row['title']}</p>
  {summary_html}
</div>
""", unsafe_allow_html=True)

    col_btn, _ = st.columns([1, 8])
    with col_btn:
        btn_label = "▲ Less" if st.session_state[key] else "▼ Detail"
        if st.button(btn_label, key=f"btn_{key}", use_container_width=True):
            st.session_state[key] = not st.session_state[key]
            st.rerun()

    if st.session_state[key]:
        with st.container():
            if row["detail"]:
                st.markdown('<p class="section-label">Detail</p>', unsafe_allow_html=True)
                st.markdown(f'<p class="section-body">{row["detail"]}</p>', unsafe_allow_html=True)
            if row["recommendation"]:
                st.markdown('<p class="section-label">Recommendation</p>', unsafe_allow_html=True)
                st.markdown(f'<p class="section-body">{row["recommendation"]}</p>', unsafe_allow_html=True)

            st.markdown(
                '<p class="section-label" style="margin-top:18px;">Sources compared</p>',
                unsafe_allow_html=True,
            )
            c1, c2 = st.columns(2)
            for col, agency, url, excerpt in [
                (c1, row["agency_a"], row["url_a"], row["excerpt_a"]),
                (c2, row["agency_b"], row["url_b"], row["excerpt_b"]),
            ]:
                with col:
                    ex_html = f"<div class='excerpt'>{excerpt}</div>" if excerpt else ""
                    st.markdown(f"""
<div class="source-block">
  <span class="source-label">{agency or 'Unknown'}</span><br>
  {render_url(url)}
  {ex_html}
</div>
""", unsafe_allow_html=True)

    st.markdown("<div style='margin-bottom:4px'></div>", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# LAYOUT
#
# Architecture: findings are stored in st.session_state[_KEY_FINDINGS_DF]
# and are ONLY loaded when the user clicks "View findings". Every other
# rerender (filter changes, expand/collapse, Streamlit's startup double-pass)
# reads from session state and never calls fetch_findings.
#
# Execution order every render:
#   1. Load runs list (cached, cheap)
#   2. Render sidebar — mode selector, run selector, search, button, filters
#   3. If button was just clicked — fetch findings, store in session state
#   4. Read findings from session state (may be empty on first load)
#   5. Render header + main content
# ══════════════════════════════════════════════════════════════════════════════

# ── 1. Load runs (cached) ─────────────────────────────────────────────────────
df_runs = load_runs()

# ── Connection badge (computed once, used in header) ──────────────────────────
_connected = make_supabase() is not None
conn_html  = (
    '<span style="background:#d1fae5;color:#065f46;padding:2px 8px;border-radius:3px;'
    'font-size:0.75rem;font-weight:600;">● Supabase connected</span>'
    if _connected else
    '<span style="background:#fee2e2;color:#991b1b;padding:2px 8px;border-radius:3px;'
    'font-size:0.75rem;font-weight:600;">✕ Not connected</span>'
)

# ── 2. Sidebar ────────────────────────────────────────────────────────────────
with st.sidebar:

    st.markdown("## 🔍 Policy Coherence")
    st.caption("IM2026 · Build a Bureaucrat Bot")
    st.divider()

    # ── Mode selector ──────────────────────────────────────────────────────────
    st.markdown("### Mode")
    mode = st.radio(
        "mode",
        options=["View existing report", "Run new analysis"],
        index=0,
        label_visibility="collapsed",
    )

    st.divider()

    if mode == "Run new analysis":
        st.info("New analysis is not yet available in this version. Select 'View existing report' to review findings from a completed run.")

    else:
        # ── View existing report ───────────────────────────────────────────────
        st.markdown("### Select report")

        if df_runs.empty:
            st.warning("No complete runs found in Supabase.")
        else:
            # Build run list
            run_ids    = df_runs["id"].tolist()
            AUD_RATE = 1.6

            run_labels = []
            for _, r in df_runs.iterrows():
                try:
                    ts = datetime.fromisoformat(
                        str(r.get("created_at", "")).replace("Z", "+00:00")
                    ).strftime("%d %b %Y %H:%M")
                except Exception:
                    ts = "?"

                cost = r.get("total_cost_usd")
                try:
                    cost = float(cost)
                except (TypeError, ValueError):
                    cost = None

                if cost:
                    aud = cost * AUD_RATE
                    cost_str = f" — USD ${cost:.2f} (~AUD ${aud:.2f})"
                else:
                    cost_str = ""

                run_labels.append(
                    f"{r.get('policy_name', 'Unknown')} — "
                    f"{r.get('department_name', 'Unknown')} ({ts}){cost_str}"
                )

            # Search box to filter the dropdown
            search = st.text_input(
                "Search reports",
                placeholder="Type to filter...",
                label_visibility="collapsed",
            )

            # Filter run list by search term
            if search.strip():
                term = search.strip().lower()
                filtered = [
                    (i, label) for i, label in enumerate(run_labels)
                    if term in label.lower()
                ]
            else:
                filtered = list(enumerate(run_labels))

            if not filtered:
                st.warning("No reports match your search.")
                sel_run_id = None
            else:
                filtered_indices = [i for i, _ in filtered]
                filtered_labels  = [label for _, label in filtered]

                # Pre-select DEFAULT_RUN_ID if it's in the filtered list,
                # otherwise pre-select the first item.
                if DEFAULT_RUN_ID in run_ids:
                    default_pos = run_ids.index(DEFAULT_RUN_ID)
                    if default_pos in filtered_indices:
                        dropdown_default = filtered_indices.index(default_pos)
                    else:
                        dropdown_default = 0
                else:
                    dropdown_default = 0

                sel_pos = st.selectbox(
                    "Report",
                    options=range(len(filtered_labels)),
                    format_func=lambda i: filtered_labels[i],
                    index=dropdown_default,
                    label_visibility="collapsed",
                )
                sel_run_id = run_ids[filtered_indices[sel_pos]]

            # View findings button — the ONLY place fetch_findings is called
            if st.button(
                "View findings",
                type="primary",
                use_container_width=True,
                disabled=(not filtered or sel_run_id is None),
            ):
                with st.spinner("Loading findings..."):
                    df_fetched = fetch_findings(sel_run_id)

                # Store in session state — this is the commit point.
                # From here, every rerender reads from session state,
                # never from the selectbox or fetch_findings.
                st.session_state[_KEY_FINDINGS_DF]   = df_fetched
                st.session_state[_KEY_LOADED_RUN_ID] = sel_run_id

                # Store display metadata from the run row
                run_row = df_runs[df_runs["id"] == sel_run_id].iloc[0]
                st.session_state[_KEY_LOADED_POLICY] = run_row.get("policy_name") or "Unknown policy"
                st.session_state[_KEY_LOADED_DEPT]   = run_row.get("department_name") or "Unknown department"

                st.rerun()

        st.divider()

        # ── Filters — only shown when findings are loaded ──────────────────────
        findings_loaded = _KEY_FINDINGS_DF in st.session_state

        if findings_loaded:
            st.markdown("### Filters")

            sel_risk = st.multiselect(
                "Risk level",
                options=["High", "Medium", "Low", "Dismissed"],
                default=["High", "Medium"],
            )

            _df_f = st.session_state[_KEY_FINDINGS_DF]
            _non_broken = _df_f[_df_f["finding_type"] != "broken_link"] if not _df_f.empty else _df_f

            available_types = (
                sorted(_non_broken["finding_type"].dropna().unique().tolist())
                if not _non_broken.empty and "finding_type" in _non_broken.columns
                else []
            )
            sel_types = st.multiselect(
                "Finding type",
                options=available_types,
                default=available_types,
                format_func=lambda t: TYPE_LABELS.get(t, t.replace("_", " ").title()),
                key=f"types_{st.session_state.get(_KEY_LOADED_RUN_ID, 'none')}",
            )

            available_scopes = (
                sorted(_non_broken["comparison_scope"].dropna().unique().tolist())
                if not _non_broken.empty and "comparison_scope" in _non_broken.columns
                else []
            )
            sel_scopes = st.multiselect(
                "Scope",
                options=available_scopes,
                default=available_scopes,
                format_func=lambda s: SCOPE_LABELS.get(s, s.replace("_", " ").title()),
                key=f"scopes_{st.session_state.get(_KEY_LOADED_RUN_ID, 'none')}",
            )

            available_jurisdictions = sorted(set(
                _non_broken["jurisdiction_a"].dropna().tolist() +
                _non_broken["jurisdiction_b"].dropna().tolist()
            )) if not _non_broken.empty else []
            available_jurisdictions = [j for j in available_jurisdictions if j.strip()]

            sel_jurisdictions = st.multiselect(
                "Jurisdiction",
                options=available_jurisdictions,
                default=available_jurisdictions,
                key=f"jurisdictions_{st.session_state.get(_KEY_LOADED_RUN_ID, 'none')}",
            )

            st.markdown(
                "<p style='font-size:0.75rem;color:#9ca3af;margin-top:8px;'>"
                "Low risk findings hidden by default. "
                "Clearing any filter shows all options.</p>",
                unsafe_allow_html=True,
            )
        else:
            sel_risk          = []
            sel_types         = []
            sel_scopes        = []
            sel_jurisdictions = []

# ── 3 & 4. Read findings from session state ───────────────────────────────────
# fetch_findings is NEVER called here. This block executes on every rerender
# including filter changes and expand/collapse — it only reads, never fetches.

df_all = st.session_state.get(_KEY_FINDINGS_DF, pd.DataFrame())

EMPTY_COLS = [
    "id", "risk_level", "finding_type", "comparison_scope",
    "title", "summary", "detail", "recommendation",
    "agency_a", "agency_b", "url_a", "url_b", "excerpt_a", "excerpt_b",
    "pass3_outcome", "jurisdiction_a", "jurisdiction_b",
]

if df_all.empty:
    df_findings = pd.DataFrame(columns=EMPTY_COLS)
    df_broken   = pd.DataFrame(columns=EMPTY_COLS)
else:
    is_broken   = df_all["finding_type"] == "broken_link"
    df_findings = df_all[~is_broken].copy()
    df_broken   = df_all[is_broken].copy()

findings_loaded   = not df_findings.empty or not df_broken.empty
selected_policy   = st.session_state.get(_KEY_LOADED_POLICY, "")
selected_dept     = st.session_state.get(_KEY_LOADED_DEPT, "")

# ── 5. Header ──────────────────────────────────────────────────────────────────
h1, h2 = st.columns([6, 1])
with h1:
    st.markdown("## 🔍 Doc Lacuna · IM2026")
    st.caption("AI coherence check for APS websites and policy documents")
    st.caption("IM2026 · Build a Bureaucrat Bot")
    if findings_loaded:
        st.caption(
            f"{selected_policy} · {selected_dept} · "
            f"Refreshed {datetime.now().strftime('%d %b %Y %H:%M')}"
        )
    
with h2:
    st.markdown(
        f"<div style='padding-top:28px;text-align:right'>{conn_html}</div>",
        unsafe_allow_html=True,
    )

# ── Mode gate — nothing below renders for "Run new analysis" ──────────────────
if mode == "Run new analysis":
    st.markdown("""
<div class="welcome-box">
  <p style="font-size:2rem;margin:0 0 12px 0;">⚙️</p>
  <p style="font-size:1.1rem;font-weight:600;color:#111827;margin:0 0 8px 0;">
    New analysis coming soon
  </p>
  <p style="font-size:0.9rem;color:#6b7280;margin:0;">
    This feature is under development. Switch to
    <strong>View existing report</strong> to review completed findings.
  </p>
</div>
""", unsafe_allow_html=True)
    st.stop()

# ── Welcome screen (no findings loaded yet) ───────────────────────────────────
if not findings_loaded:
    st.markdown("""
<div class="welcome-box">
  <p style="font-size:2rem;margin:0 0 12px 0;">🔍</p>
  <p style="font-size:1.1rem;font-weight:600;color:#111827;margin:0 0 8px 0;">
    Select a report to get started
  </p>
  <p style="font-size:0.9rem;color:#6b7280;margin:0;">
    Choose an existing report from the sidebar and click
    <strong>View findings</strong> to load the analysis.
  </p>
</div>
""", unsafe_allow_html=True)
    st.stop()

# ── Metrics ────────────────────────────────────────────────────────────────────
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

# ── Tabs ───────────────────────────────────────────────────────────────────────
tab_main, tab_broken = st.tabs([
    f"Findings ({n_total})",
    f"Broken Links ({len(df_broken)})",
])

with tab_main:
    if df_findings.empty:
        st.info("No findings recorded for this run.")
    else:
        mask = (
            apply_filter(df_findings, "risk_level",         sel_risk)
            & apply_filter(df_findings, "finding_type",     sel_types)
            & apply_filter(df_findings, "comparison_scope", sel_scopes)
            & apply_jurisdiction_filter(df_findings,        sel_jurisdictions)
        )
        df_view = df_findings[mask]

        if df_view.empty:
            st.markdown(
                "<div class='empty-state'>No findings match the selected filters.</div>",
                unsafe_allow_html=True,
            )
        else:
            n_shown  = len(df_view)
            n_hidden = n_total - n_shown
            caption  = f"**{n_shown} finding{'s' if n_shown != 1 else ''}**"
            if n_hidden > 0:
                caption += f" · {n_hidden} hidden by filters"
            st.markdown(caption)
            st.markdown("")
            for i, (_, row) in enumerate(df_view.iterrows()):
                render_finding(row, i)

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