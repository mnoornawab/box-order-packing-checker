import streamlit as st
import pandas as pd
import requests

st.set_page_config(page_title="Packing Checker Advanced", layout="wide")

def normalize_upc(upc):
    return str(upc).lstrip('0').strip()

@st.cache_data(show_spinner=False)
def parse_orders(orders_file):
    orders = pd.read_csv(orders_file, dtype=str)
    orders.columns = [c.strip() for c in orders.columns]
    def colkey(s): return s.strip().replace(" ", "").replace("_", "").upper()
    upc_col = None
    for col in orders.columns:
        if colkey(col) in ["UPCCODE", "UPC"]:
            upc_col = col
            break
    for c in ["TOTAL", "RESERVED", "CONFIRMED", "BALANCE"]:
        orders[c] = orders[c].astype(int)
    return orders, upc_col

@st.cache_data(show_spinner=False)
def parse_boxes(box_file_contents):
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
    return boxes

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

def main_results_page(orders, upc_col, boxes):
    st.subheader("Main Allocation Table (Per Order Line)")
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
    st.dataframe(df, use_container_width=True)
    csv = df.to_csv(index=False).encode()
    st.download_button("Download results as CSV", data=csv, file_name='check_results.csv', mime='text/csv')

def box_summary_page(orders, upc_col, boxes):
    st.subheader("Total Scanned Per Box (By Style Code, Horizontal)")

    # Build UPC->STYLE mapping for quick lookup
    upc_to_style = {}
    for idx, row in orders.iterrows():
        upc_to_style[normalize_upc(row[upc_col])] = row.get("STYLE", "")

    # Collect all style codes present
    style_set = set()
    scanned_by_box = {}   # box_no -> dict(upc -> qty)
    for upc, box_dict in boxes.items():
        style = upc_to_style.get(upc, upc)
        style_set.add(style)
        for box_no, qty in box_dict.items():
            if box_no not in scanned_by_box:
                scanned_by_box[box_no] = {}
            scanned_by_box[box_no][style] = scanned_by_box[box_no].get(style, 0) + qty

    all_styles = sorted(list(style_set))
    rows = []
    for box_no in sorted(scanned_by_box.keys(), key=lambda x: int(x) if x.isdigit() else x):
        row = {"BOX NO": box_no, "TOTAL ITEMS": sum(scanned_by_box[box_no].values())}
        for style in all_styles:
            row[style] = scanned_by_box[box_no].get(style, 0)
        rows.append(row)

    df_box = pd.DataFrame(rows)
    st.dataframe(df_box, use_container_width=True)
    csv_box = df_box.to_csv(index=False).encode()
    st.download_button("Download Box Summary as CSV", data=csv_box, file_name='box_summary.csv', mime='text/csv')

def items_not_on_order_page(orders, upc_col, boxes):
    st.subheader("Items Scanned But Not On Order (With Box Numbers, By UPC CODE)")
    ordered_upcs = set(normalize_upc(str(u)) for u in orders[upc_col])
    scanned_totals = {}
    scanned_by_box = {}
    for upc, box_dict in boxes.items():
        scanned_totals[upc] = sum(box_dict.values())
        for box_no, qty in box_dict.items():
            if box_no not in scanned_by_box:
                scanned_by_box[box_no] = {}
            scanned_by_box[box_no][upc] = qty
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

def order_status_page(orders, upc_col, boxes):
    st.subheader("Order Status: Completion and Invoicing Readiness (Horizontal)")

    # UPC->STYLE for column headers
    upc_to_style = {}
    for idx, row in orders.iterrows():
        upc_to_style[normalize_upc(row[upc_col])] = row.get("STYLE", "")

    # Total scanned by UPC
    scanned_totals = {}
    for upc, box_dict in boxes.items():
        scanned_totals[upc] = sum(box_dict.values())

    # Collect all style codes in orders (for column order)
    style_set = set()
    style_to_upc = {}
    for idx, row in orders.iterrows():
        style = row.get('STYLE', '')
        upc = normalize_upc(row[upc_col])
        style_set.add(style)
        style_to_upc[style] = upc

    all_styles = sorted(list(style_set))

    # Group by order
    order_grouped = orders.groupby('ORDER NO')
    rows = []
    for order_no, order_rows in order_grouped:
        order_complete = True
        row = {"ORDER NO": order_no, "STATUS": ""}
        for style in all_styles:
            row[style] = ""
        for idx, orow in order_rows.iterrows():
            code = normalize_upc(orow[upc_col])
            style = orow.get('STYLE', '')
            needed = orow['RESERVED']
            available = scanned_totals.get(code, 0)
            is_complete = available >= needed and needed > 0
            if not is_complete:
                order_complete = False
            checkmark = "✅" if is_complete else "❌"
            row[style] = f"{needed}/{available} {checkmark}"
        row["STATUS"] = "COMPLETE FOR INVOICING" if order_complete else "INCOMPLETE"
        rows.append(row)

    df_status = pd.DataFrame(rows)
    st.dataframe(df_status, use_container_width=True)
    csv_status = df_status.to_csv(index=False).encode()
    st.download_button("Download Order Status as CSV", data=csv_status, file_name='order_status_summary.csv', mime='text/csv')
    
def main():
    if "trigger_results" not in st.session_state:
        st.session_state["trigger_results"] = False

    if not st.session_state["trigger_results"]:
        upload_page()
    else:
        orders_file = st.session_state.get('orders_file', None)
        box_file_contents = st.session_state.get('box_file_contents', {})
        if not (orders_file and box_file_contents):
            st.warning("Please upload your files on the first page.")
            return
        orders, upc_col = parse_orders(orders_file)
        boxes = parse_boxes(box_file_contents)
        st.markdown("## 📊 Reports & Summaries")
        tab1, tab2, tab3, tab4 = st.tabs(
            ["Main Allocation Table", "Box Summary", "Items Not On Order", "Order Status"]
        )
        with tab1:
            main_results_page(orders, upc_col, boxes)
        with tab2:
            box_summary_page(orders, upc_col, boxes)
        with tab3:
            items_not_on_order_page(orders, upc_col, boxes)
        with tab4:
            order_status_page(orders, upc_col, boxes)
        if st.button("⬅️ Back to Uploads"):
            st.session_state["trigger_results"] = False
            for key in ['orders_file', 'box_file_contents']:
                if key in st.session_state:
                    del st.session_state[key]
            st.stop()

if __name__ == "__main__":
    main()
