import streamlit as st
import pandas as pd
import requests

# ---------- STYLING ----------
st.set_page_config(page_title="Packing Checker Advanced", layout="wide")
st.markdown("""
<style>
body {background-color: #f8fafc;}
[data-testid="stHeader"] {background-color: #0e1117;}
h1, h2, h3, h4 {color: #1a237e;}
.stButton>button {
    background: #004d40 !important;
    color: white !important;
    border-radius: 8px;
    padding: 0.4em 1.2em;
    margin: 6px 0;
    font-weight: 600;
}
thead tr th {background: #ede7f6;}
tbody tr {background: #fafafa;}
</style>
""", unsafe_allow_html=True)

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
    st.subheader("Box Summary")

    # Build UPC->STYLE mapping
    upc_to_style = {}
    for idx, row in orders.iterrows():
        upc_to_style[normalize_upc(row[upc_col])] = row.get("STYLE", "")

    all_box_numbers = sorted(
        set(int(box_no) for upc in boxes for box_no in boxes[upc])
    )

    box_option = st.radio("Show", ["Single Box", "Multiple Boxes"])
    if box_option == "Single Box":
        box_sel = st.selectbox("Select Box Number", all_box_numbers, index=0)
        box_key = str(box_sel)
        items = []
        seq = 1
        total = 0
        for upc, box_dict in boxes.items():
            qty = box_dict.get(box_key, 0)
            if qty > 0:
                style = upc_to_style.get(upc, upc)
                items.append({"Seq No.": seq, "Style Code": style, "Qty": qty})
                total += qty
                seq += 1
        st.markdown(f"**Box No - {box_sel}**")
        st.markdown(f"**Total items in the box:** {total}")
        if items:
            df_items = pd.DataFrame(items)
            st.table(df_items)
            csv_items = df_items.to_csv(index=False).encode()
            st.download_button("Download Box Table as CSV", data=csv_items, file_name=f'box_{box_sel}_items.csv', mime='text/csv')
        else:
            st.info("No items in this box.")

    else:  # Multiple Boxes
        box_multi = st.multiselect("Select Box Numbers", all_box_numbers, default=all_box_numbers)
        all_items = []
        total = 0
        seq = 1
        for box_sel in box_multi:
            box_key = str(box_sel)
            for upc, box_dict in boxes.items():
                qty = box_dict.get(box_key, 0)
                if qty > 0:
                    style = upc_to_style.get(upc, upc)
                    all_items.append({"Seq No.": seq, "Box No": box_key, "Style Code": style, "Qty": qty})
                    total += qty
                    seq += 1
        st.markdown(f"**Boxes: {', '.join(map(str, box_multi))}**")
        st.markdown(f"**Total items in selected boxes:** {total}")
        if all_items:
            df_items = pd.DataFrame(all_items)
            st.table(df_items)
            csv_items = df_items.to_csv(index=False).encode()
            st.download_button("Download Boxes Table as CSV", data=csv_items, file_name='multi_box_items.csv', mime='text/csv')
        else:
            st.info("No items in selected boxes.")

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
    st.subheader("Order Status: Completion and Invoicing Readiness")

    scanned_totals = {}
    upc_boxes = {}
    for upc, box_dict in boxes.items():
        scanned_totals[upc] = sum(box_dict.values())
        upc_boxes[upc] = [box_no for box_no, qty in box_dict.items() if qty > 0]

    orders_to_check = orders[orders['RESERVED'] > 0]
    order_numbers = sorted(orders_to_check['ORDER NO'].unique())

    if not order_numbers:
        st.info("No pending orders with reserved quantities.")
        return

    order_sel = st.selectbox("Select Order Number", order_numbers)
    order_rows = orders[orders['ORDER NO'] == order_sel]

    items = []
    complete = True
    for idx, row in order_rows.iterrows():
        upc = normalize_upc(row[upc_col])
        style = row.get("STYLE", "")
        needed = row['RESERVED']
        found = scanned_totals.get(upc, 0)
        boxes_found = ", ".join(sorted(upc_boxes.get(upc, []), key=lambda x: int(x) if x.isdigit() else x))
        # Status logic
        if needed > 0:
            if found == needed:
                status = "Ready to Invoice"
            elif found == 0:
                status = "Not Found in Box"
                complete = False
            elif 0 < found < needed:
                status = f"Missing: {needed - found}"
                complete = False
            elif found > needed:
                status = f"Over-packed (found: {found}, reserved: {needed})"
            else:
                status = ""
        else:
            status = "Not Available in Stock"
            complete = False
        items.append({
            "UPC CODE": upc,
            "Style Code": style,
            "Qty Needed": needed,
            "Qty Scanned": found,
            "Box Numbers": boxes_found,
            "Status": status
        })

    st.markdown(f"**Order No - {order_sel}**")
    st.markdown(f"**Ready for invoicing:** {'COMPLETE' if complete else 'INCOMPLETE'}")
    df_items = pd.DataFrame(items)
    st.table(df_items)
    csv_items = df_items.to_csv(index=False).encode()
    st.download_button("Download Order Items Table as CSV", data=csv_items, file_name=f'order_{order_sel}_items.csv', mime='text/csv')

def main():
    if st.session_state.get("back_to_uploads", False):
        st.session_state.clear()
        st.session_state["trigger_results"] = False
        st.session_state["back_to_uploads"] = False
        st.stop()

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
        try:
            orders, upc_col = parse_orders(orders_file)
        except pd.errors.EmptyDataError:
            st.error("Your orders.csv file appears empty or invalid. Please re-upload.")
            st.session_state["back_to_uploads"] = True
            st.stop()
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
            st.session_state["back_to_uploads"] = True
            st.experimental_rerun()

if __name__ == "__main__":
    main()
