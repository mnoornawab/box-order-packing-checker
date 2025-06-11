import streamlit as st
import pandas as pd

st.set_page_config(page_title="Packing Checker", layout="wide")
st.title("📦 Order Packing Checker (Advanced)")

st.write("""
Upload your `orders.csv` and all your scanned box files (as `.txt`).  
This app checks your scanned box contents against orders and gives actionable status for each item.
""")

# --- File Uploads ---
orders_file = st.file_uploader("Upload orders.csv", type=["csv"])
box_files = st.file_uploader("Upload box txt files (multiple allowed)", type=["txt"], accept_multiple_files=True)

def normalize_upc(upc):
    upc = str(upc).lstrip('0').strip()
    return upc

if orders_file and box_files:
    # --- Read Orders ---
    orders = pd.read_csv(orders_file, dtype=str)
    # Normalize column names for safety
    orders.columns = [c.strip().upper() for c in orders.columns]
    # Try to find the correct UPC column
upc_col = None
for col in orders.columns:
    if col.strip().replace(" ", "_").upper() in ["UPC_CODE", "UPC"]:
        upc_col = col
        break

if not upc_col:
    st.error("Your orders.csv must contain a column for UPC (like 'UPC CODE' or 'UPC_CODE').")
    st.stop()

orders['UPC_CODE_NORM'] = orders[upc_col].apply(normalize_upc)

    orders['TOTAL'] = orders['TOTAL'].astype(int)
    orders['RESERVED'] = orders['RESERVED'].astype(int)
    orders['CONFIRMED'] = orders['CONFIRMED'].astype(int)
    orders['BALANCE'] = orders['BALANCE'].astype(int)

    # For matching and output
    upc_to_row = orders.set_index('UPC_CODE_NORM').to_dict('index')

    # --- Read Boxes ---
    boxes = {}
    for uploaded_file in box_files:
        box_no = uploaded_file.name.replace('BOX NO', '').replace('.TXT','').replace('.txt','').strip()
        for line in uploaded_file:
            decoded = line.decode('utf-8').strip()
            if ',' in decoded:
                code, qty = decoded.split(',')
                code_norm = normalize_upc(code)
                qty = int(qty.strip())
                if code_norm not in boxes:
                    boxes[code_norm] = {}
                boxes[code_norm][box_no] = boxes[code_norm].get(box_no, 0) + qty

    # --- Process Results ---
    all_codes = set(list(orders['UPC_CODE_NORM']) + list(boxes.keys()))
    data = []
    for code in sorted(all_codes):
        order = upc_to_row.get(code, None)
        scanned_by_box = boxes.get(code, {})
        scanned_total = sum(scanned_by_box.values())
        box_numbers = ', '.join(sorted(scanned_by_box.keys(), key=lambda x: int(x) if x.isdigit() else x))
        missing = ""

        if order:
            total = order['TOTAL']
            reserved = order['RESERVED']
            confirmed = order['CONFIRMED']
            balance = order['BALANCE']
            style = order['STYLE']
            # Status logic
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
        else:
            # Not in orders
            total = ''
            reserved = ''
            confirmed = ''
            balance = ''
            style = ''
            note = f"Not on order, Remove from {box_numbers}"

        data.append({
            'UPC CODE': code,
            'STYLE': style,
            'TOTAL': total,
            'RESERVED': reserved,
            'CONFIRMED': confirmed,
            'BALANCE': balance,
            'SCANNED QTY': scanned_total,
            'BOX NUMBERS': box_numbers,
            'NOTE': note
        })

    df = pd.DataFrame(data)
    st.dataframe(df, use_container_width=True)
    csv = df.to_csv(index=False).encode()
    st.download_button("Download results as CSV", data=csv, file_name='check_results.csv', mime='text/csv')

st.info("""
Upload your orders.csv and all your box files (as .txt).  
Results will be shown and can be downloaded as CSV.
""")
