import streamlit as st
import pandas as pd
import requests

st.set_page_config(page_title="Packing Checker Advanced", layout="wide")

# --- Page 1: Upload/Input ---
def upload_page():
    st.title("📦 Order Packing Checker (Step 1: Upload Files)")
    st.write("""
    Upload your `orders.csv` (with one order line per row), then either:
    - Paste one or more GitHub "raw" TXT file URLs for your box scans, **OR**
    - Upload your box scan TXT files directly.
    """)
    st.info("""
    Each row in your orders.csv will be checked and allocated **individually**.
    Duplicate UPCs are supported, and each will be assigned to available boxes, in order, until all scanned stock is used.
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
            # Store uploads in session state for page 2
            st.session_state['orders_file'] = orders_file
            st.session_state['box_file_contents'] = box_file_contents
            st.session_state['trigger_results'] = True

# --- Page 2: Results ---
def results_page():
    st.title("📦 Packing Checker Results (Step 2: Allocation)")

    # --- Legend / Explanation ---
    with st.expander("ℹ️ Results Table Explanation / Legend (click to expand)"):
        st.markdown("""
        - **Each row** represents a single line in your orders.csv (even if you have duplicate UPCs).
        - **ALLOCATED QTY**: How many units of that order line were packed, based on what was left after earlier rows used available units for that UPC.
        - **ALLOCATED BOXES**: Which box numbers supplied the quantity for this row, and how much from each.  
            - *Example*: `1(2), 2(1)` means: **2 from box 1**, **1 from box 2** for this order line.
        - **NOTE**: Action required (to invoice, missing stock, over-packed, already invoiced, etc.)
        - The allocation is **row by row**: once stock for a UPC is used up by an earlier row, it is no longer available to later rows.
        """)

    # --- Load previously uploaded data ---
    orders_file = st.session_state.get('orders_file', None)
    box_file_contents = st.session_state.get('box_file_contents', {})

    if not (orders_file and box_file_contents):
        st.warning("Please upload your files on the first page.")
        return

    # --- Load orders.csv ---
    orders = pd.read_csv(orders_file, dtype=str)
    orders.columns = [c.strip() for c in orders.columns]
    # Flexible UPC col detection
    def colkey(s): return s.strip().replace(" ", "").replace("_", "").upper()
    upc_col = None
    for col in orders.columns:
        if colkey(col) in ["UPCCODE", "UPC"]:
            upc_col = col
            break
    if not upc_col:
        st.error("Your orders.csv must contain a column for UPC (like 'UPC CODE', 'UPC_CODE', or 'UPC').")
        return
    # Convert to numeric
    for c in ["TOTAL", "RESERVED", "CONFIRMED", "BALANCE"]:
        orders[c] = orders[c].astype(int)

    # --- Parse boxes ---
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

    # --- Allocation Logic (per-row, consuming available stock as we go) ---
    boxes_remaining = {upc: box_qtys.copy() for upc, box_qtys in boxes.items()}
    data = []
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
            note = f"Waiting for box upload (missing: {reserved - scanned_total})"
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
    st.dataframe(df, use_container_width=True)
    csv = df.to_csv(index=False).encode()
    st.download_button("Download results as CSV", data=csv, file_name='check_results.csv', mime='text/csv')

    st.info("""
    - You can click column headers to sort, or download the results as CSV.
    - If you want to re-run, just go back to the upload page and submit new files.
    """)

# --- Main multipage logic ---
def main():
    if "trigger_results" not in st.session_state:
        st.session_state["trigger_results"] = False

    if not st.session_state["trigger_results"]:
        upload_page()
    else:
        results_page()
        if st.button("⬅️ Back to Uploads"):
            st.session_state["trigger_results"] = False

if __name__ == "__main__":
    main()
