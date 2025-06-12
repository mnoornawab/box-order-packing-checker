import streamlit as st
import pandas as pd
import requests

st.set_page_config(page_title="Packing Checker Advanced", layout="wide")

def upload_page():
    st.title("📦 Order Packing Checker (Step 1: Upload Files)")
    st.write("""
    Upload your `orders.csv` (one order line per row), then either:
    - Paste one or more GitHub "raw" TXT file URLs for your box scans, **OR**
    - Upload your box scan TXT files directly.
    """)

    orders_file = st.file_uploader("Upload orders.csv", type=["csv"])
    box_file_contents = {}

    source = st.radio("How do you want to provide box files?", ["Paste GitHub raw URLs", "Upload TXT files"])

    if source == "Paste GitHub raw URLs":
        txt_urls = st.text_area("Paste one GitHub raw TXT URL per line (https://raw.githubusercontent.com/...):", height=120)
        if txt_urls:
            urls = [u.strip() for u in txt_urls.splitlines() if u.strip()]
            for url in urls:
                try:
                    r = requests.get(url)
                    if r.status_code == 200:
                        box_file_contents[url] = r.text
                        st.success(f"Loaded: {url}")
                    else:
                        st.error(f"Failed to fetch {url} (status {r.status_code})")
                except Exception as e:
                    st.error(f"Error loading {url}: {e}")
    else:
        uploaded_boxes = st.file_uploader("Upload box txt files", type=["txt"], accept_multiple_files=True)
        for uploaded_file in uploaded_boxes or []:
            box_file_contents[uploaded_file.name] = uploaded_file.read().decode('utf-8')

    ready = orders_file is not None and len(box_file_contents) > 0
    if ready:
        if st.button("Go to Results ➡️"):
            st.session_state['orders_file'] = orders_file
            st.session_state['box_file_contents'] = box_file_contents
            st.session_state['trigger_results'] = True
            st.experimental_rerun()  # Immediately move to results page

def results_page():
    st.title("📦 Packing Checker Results (Step 2: Allocation)")
    with st.expander("ℹ️ Results Table Explanation / Legend (click to expand)"):
        st.markdown("""
        - **Each row** represents a single line in your orders.csv (even if you have duplicate UPCs).
        - **ALLOCATED QTY**: How many units of that order line were packed, based on what was left after earlier rows used available units for that UPC.
        - **ALLOCATED BOXES**: Which box numbers supplied the quantity for this row, and how much from each.  
            - *Example*: `1(2), 2(1)` means: **2 from box 1**, **1 from box 2** for this order line.
        - **NOTE**: Action required (to invoice, missing stock, over-packed, already invoiced, etc.)
        - The allocation is **row by row**: once stock for a UPC is used up by an earlier row, it is no longer available to later rows.
        ---
        - Scroll down for **Scanned Summaries**:
            - Total scanned per UPC (ignores order allocation)
            - Items scanned that are NOT on the order, with breakdown by box
            - Total scanned summary per box (all UPCs)
        """)

    orders_file = st.session_state.get('orders_file', None)
    box_file_contents = st.session_state.get('box_file_contents', {})

    if not (orders_file and box_file_contents):
        st.warning("Please upload your files on the first page.")
        return

    orders = pd.read_csv(orders_file, dtype=str)
    orders.columns = [c.strip() for c in orders.columns]
    def colkey(s): return s.strip().replace(" ", "").replace("_", "").upper()
    upc_col = None
    for col in orders.columns:
        if colkey(col) in ["UPCCODE", "UPC"]:
            upc_col = col
            break
    if not upc_col:
        st.error("Your orders.csv must contain a column for UPC (like 'UPC CODE', 'UPC_CODE', or 'UPC').")
        return
    for c in ["TOTAL", "RESERVED", "CONFIRMED", "BALANCE"]:
        orders[c] = orders[c].astype(int)

    def normalize_upc(upc): return str(upc).lstrip('0').strip()
    boxes = {}
    for filename, content in box_file_contents.items():
        box_no = filename.replace('BOX NO', '').replace('.TXT','').replace('.txt','').strip()
        for line in content.strip().splitlines():
            if ',' in line:
                code, qty = line.strip().split(',', 1)
                code_norm = normalize_upc(code)
                qty = int(qty.strip())
                if code_norm not in boxes:
                    boxes[code_norm] = {}
                boxes[code_norm][box_no] = boxes[code_norm].get(box_no, 0) + qty

    boxes_remaining = {upc: box_qtys.copy() for upc, box_qtys in boxes.items()}
    data = []

    # Track all scanned (regardless of allocation) for summaries
    scanned_totals = {}   # upc -> total qty scanned
    scanned_by_box = {}   # box_no -> dict(upc -> qty)
    for upc, box_dict in boxes.items():
        scanned_totals[upc] = sum(box_dict.values())
        for box_no, qty in box_dict.items():
            if box_no not in scanned_by_box:
                scanned_by_box[box_no] = {}
            scanned_by_box[box_no][upc] = qty

    for idx, row in orders.iterrows():
        order_no = row.get('ORDER NO', '')
        upc_raw = row[upc_col]
        code = normalize_upc(upc_raw)
        style = row.get('STYLE', '')
        total = row['TOTAL']
        reserved = row['RESERVED']
        confirmed = row['CONFIRMED']
        balance = row['BALANCE']

        allocation = []
        qty_needed = reserved
        scanned_total = 0

        if code in boxes_remaining:
            for box_no in sorted(boxes_remaining[code], key=lambda x: int(x) if x.isdigit() else x):
                box_qty = boxes_remaining[code][box_no]
                if box_qty > 0 and qty_needed > 0:
                    allocate_qty = min(qty_needed, box_qty)
                    allocation.append(f"{box_no}({allocate_qty})")
                    qty_needed -= allocate_qty
                    scanned_total += allocate_qty
                    boxes_remaining[code][box_no] -= allocate_qty
                if qty_needed == 0:
                    break

        missing = ""
        if scanned_total == reserved and reserved > 0:
            note = "To invoice"
        elif scanned_total <= confirmed and confirmed > 0:
            note = "Already invoiced"
        elif scanned_total < reserved and reserved > 0:
            note = f"To unreserve and invoice (missing: {reserved - scanned_total})"
            missing = str(reserved - scanned_total)
        elif scanned_total > total:
            note = "Check: Over-packed"
        elif scanned_total == 0 and balance > 0:
            note = f"Not found (missing: {balance})"
            missing = str(balance)
        else:
            note = ""

        data.append({
            'ORDER NO': order_no,
            'UPC CODE': code,
            'STYLE': style,
            'TOTAL': total,
            'RESERVED': reserved,
            'CONFIRMED': confirmed,
            'BALANCE': balance,
            'ALLOCATED QTY': scanned_total,
            'ALLOCATED BOXES': ", ".join(allocation),
            'NOTE': note
        })

    df = pd.DataFrame(data)
    st.subheader("Main Results Table (Per Order Line)")
    st.dataframe(df, use_container_width=True)
    csv = df.to_csv(index=False).encode()
    st.download_button("Download results as CSV", data=csv, file_name='check_results.csv', mime='text/csv')

    # --- 1. Total scanned per UPC ---
    st.subheader("Summary: Total Scanned Per UPC")
    upc_summary = []
    for upc, qty in scanned_totals.items():
        in_orders = any(normalize_upc(str(u)) == upc for u in orders[upc_col])
        upc_summary.append({
            "UPC CODE": upc,
            "SCANNED QTY": qty,
            "ON ORDER?": "Yes" if in_orders else "No"
        })
    df_upc = pd.DataFrame(upc_summary).sort_values(by="UPC CODE")
    st.dataframe(df_upc, use_container_width=True)

    # --- 2. Scanned items not on order (and which boxes) ---
    st.subheader("Items Scanned But Not In Orders (With Box Numbers)")
    ordered_upcs = set(normalize_upc(str(u)) for u in orders[upc_col])
    not_on_order = []
    for upc in scanned_totals:
        if upc not in ordered_upcs:
            box_breakdown = []
            for box_no, upc_dict in scanned_by_box.items():
                if upc in upc_dict:
                    box_breakdown.append(f"{box_no}({upc_dict[upc]})")
            not_on_order.append({
                "UPC CODE": upc,
                "SCANNED QTY": scanned_totals[upc],
                "BOX BREAKDOWN": ", ".join(box_breakdown)
            })
    if not_on_order:
        df_not_on_order = pd.DataFrame(not_on_order).sort_values(by="UPC CODE")
        st.dataframe(df_not_on_order, use_container_width=True)
        csv_not_on_order = df_not_on_order.to_csv(index=False).encode()
        st.download_button("Download 'Not On Order' Items CSV", data=csv_not_on_order, file_name='scanned_not_on_order.csv', mime='text/csv')
    else:
        st.write("✅ All scanned items are linked to orders.")

    # --- 3. Total scanned summary per box ---
    st.subheader("Summary: Total Scanned Per Box")
    per_box_table = []
    for box_no in sorted(scanned_by_box.keys(), key=lambda x: int(x) if x.isdigit() else x):
        upc_dict = scanned_by_box[box_no]
        total_qty = sum(upc_dict.values())
        upc_breakdown = "; ".join([f"{upc}({qty})" for upc, qty in sorted(upc_dict.items())])
        per_box_table.append({
            "BOX NO": box_no,
            "TOTAL ITEMS": total_qty,
            "UPC BREAKDOWN": upc_breakdown
        })
    df_box = pd.DataFrame(per_box_table)
    st.dataframe(df_box, use_container_width=True)

    st.info("""
    - Each 'ALLOCATED QTY' value is limited by what's available in scanned boxes and by each order's RESERVED quantity.
    - If your scanned total is higher than allocated, it means you scanned more than needed for orders.
    - You can download the list of scanned items that are NOT on any order, including which boxes they're in.
    """)

def main():
    if "trigger_results" not in st.session_state:
        st.session_state["trigger_results"] = False

    if not st.session_state["trigger_results"]:
        upload_page()
    else:
        results_page()
        if st.button("⬅️ Back to Uploads"):
            st.session_state["trigger_results"] = False
            # Clear uploaded files
            for key in ['orders_file', 'box_file_contents']:
                if key in st.session_state:
                    del st.session_state[key]
            st.experimental_rerun()

if __name__ == "__main__":
    main()
