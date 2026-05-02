
import streamlit as st
import xmlrpc.client
import ssl
import base64
import io
from rembg import remove, new_session
from PIL import Image, ImageDraw, ImageFilter
import time  # <--- Added for waiting
from google import genai
from google.genai import types
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
import os
import re

gemini_model = 'gemini-2.5-flash-lite' 

# --- YOUR DETAILS SECURED ---
URL = st.secrets["ODOO_URL"]
DB = st.secrets["ODOO_DB"]            
USER = st.secrets["ODOO_USER"]
PASS = st.secrets["ODOO_PASS"]
API = st.secrets["GEMINI_API_KEY"]

unverified_context = ssl._create_unverified_context()
ai_client = genai.Client(api_key=API)

# ==========================================
# ⚙️ IMAGE PROCESSING FUNCTION (In-Memory)
# ==========================================
def create_premium_amazon_listing(input_bytes, product_scale=0.85):
    """Takes image bytes, removes BG, adds studio lighting, and returns new image bytes."""
    TARGET_SIZE = (1080, 1080)
    
    # --- NEW: Tell rembg to use the lightweight, low-memory model ---
    my_session = new_session("u2netp")
    
    # 1. Extract Product using the lightweight session
    output_bytes = remove(input_bytes, session=my_session)
    product = Image.open(io.BytesIO(output_bytes)).convert("RGBA")

    # 2. Resize Product
    bw, bh = product.size
    max_allowed_width = TARGET_SIZE[0] * product_scale
    max_allowed_height = TARGET_SIZE[1] * product_scale
    
    scale_factor = min(max_allowed_width / bw, max_allowed_height / bh)
    new_w = int(bw * scale_factor)
    new_h = int(bh * scale_factor)
    
    final_product = product.resize((new_w, new_h), Image.Resampling.LANCZOS)

    # 3. Create the "Studio Spotlight" Background
    bg = Image.new('RGB', TARGET_SIZE, (240, 240, 242))
    glow_layer = Image.new('RGBA', TARGET_SIZE, (255, 255, 255, 0))
    draw = ImageDraw.Draw(glow_layer)
    
    margin = int(1080 * (1 - product_scale) / 2) 
    draw.ellipse((margin, margin, TARGET_SIZE[0]-margin, TARGET_SIZE[1]-margin), fill=(255, 255, 255, 255))
    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=180))
    bg.paste(glow_layer, (0, 0), glow_layer)

    # 4. Create Soft Contact Shadow
    shadow_canvas = Image.new("RGBA", (new_w, new_h), (0,0,0,0))
    solid_black = Image.new("RGBA", (new_w, new_h), "BLACK")
    shadow_canvas.paste(solid_black, (0,0), mask=final_product.split()[3])
    
    soft_shadow = shadow_canvas.filter(ImageFilter.GaussianBlur(radius=8))
    shadow_mask = soft_shadow.split()[3].point(lambda p: p * 0.3)

    # 5. Composite Everything Together
    composite = Image.new("RGBA", TARGET_SIZE, (0,0,0,0))
    composite.paste(bg, (0,0))
    
    px = (TARGET_SIZE[0] - new_w) // 2
    py = (TARGET_SIZE[1] - new_h) // 2
    
    composite.paste(soft_shadow, (px + 5, py + 10), mask=shadow_mask)
    composite.paste(final_product, (px, py), mask=final_product)
    
    final_listing = composite.convert("RGB")
    
    # Save to a byte buffer instead of a file
    output_buffer = io.BytesIO()
    final_listing.save(output_buffer, format="JPEG", quality=95)
    return output_buffer.getvalue()

# ==========================================
# 🚀 STREAMLIT APP
# ==========================================

unverified_context = ssl._create_unverified_context()
ai_client = genai.Client(api_key=GEMINI_API_KEY) 

# Set up the title of your web app
st.title("Odoo Product Fetcher 📦")
st.write("Let's make sure we can talk to your Odoo database.")

# --- 1. SET UP STREAMLIT MEMORY (SESSION STATE) ---
if 'connected' not in st.session_state:
    st.session_state.connected = False
    st.session_state.uid = None
    st.session_state.url = None
    st.session_state.db = None
    st.session_state.password = None

# Initialize memory for the image processor
if 'processed_image_bytes' not in st.session_state:
    st.session_state.processed_image_bytes = None
if 'current_file_id' not in st.session_state:
    st.session_state.current_file_id = None

# --- 2. The Connect Button ---
if st.button("Connect to Odoo"):
    if URL and DB and USER and PASS:
        with st.spinner("Attempting to connect..."):
            try:
                common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common', context=unverified_context)
                uid = common.authenticate(DB, USER, PASS, {})

                if uid:
                    st.session_state.connected = True
                    st.session_state.uid = uid
                    st.session_state.url = URL
                    st.session_state.db = DB
                    st.session_state.password = PASS
                    st.rerun() 
                else:
                    st.error("Authentication failed. Please check your credentials.")
            except Exception as e:
                st.error(f"Could not connect to the server. Error details: {e}")
    else:
        st.warning("Please fill in all the credential fields first.")

# --- 3. THE MAIN APP (Shows only AFTER successful connection) ---
if st.session_state.connected:
    st.success("✅ Connected to Odoo successfully!")
    
    if st.button("Disconnect"):
        st.session_state.connected = False
        st.rerun()

    st.divider() 
    st.subheader("Browse & Search Products")

    with st.spinner("Fetching categories from Odoo..."):
        try:
            models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object', context=unverified_context)
            
            categories = models.execute_kw(
                st.session_state.db, 
                st.session_state.uid, 
                st.session_state.password,
                'product.category', 
                'search_read',
                [[]], 
                {'fields': ['id', 'name']}
            )

            if categories:
                category_dict = {cat['name']: cat['id'] for cat in categories}
                category_names = list(category_dict.keys())

                selected_category_name = st.selectbox("1. Select a Category:", category_names)
                selected_category_id = category_dict[selected_category_name]

                search_query = st.text_input(f"2. Search products in '{selected_category_name}':", placeholder="e.g., machine")

                if 'search_results' not in st.session_state:
                    st.session_state.search_results = None

                if st.button("Search Products"):
                    if search_query:
                        with st.spinner("Searching Odoo..."):
                            domain = [
                                ['categ_id', '=', selected_category_id],
                                ['name', 'ilike', search_query]
                            ]
                            products = models.execute_kw(
                                st.session_state.db, 
                                st.session_state.uid, 
                                st.session_state.password,
                                'product.template', 
                                'search_read',
                                [domain], 
                                {'fields': ['id', 'name', 'list_price', 'qty_available'], 'limit': 50} 
                            )
                            st.session_state.search_results = products
                    else:
                        st.info("Please enter a word to search for.")

                if st.session_state.search_results is not None:
                    if len(st.session_state.search_results) > 0:
                        st.success(f"Found {len(st.session_state.search_results)} products!")
                        
                        event = st.dataframe(
                            st.session_state.search_results, 
                            use_container_width=True,
                            on_select="rerun",
                            selection_mode="single-row"
                        ) 
                        
                        selected_rows = event.selection.rows
                        
                        if len(selected_rows) > 0:
                            selected_index = selected_rows[0]
                            selected_product = st.session_state.search_results[selected_index]
                            
                            st.info(f"Currently Selected: **{selected_product['name']}** (Price: {selected_product['list_price']})")
                            
                            st.write("### 🎯 Choose Action")
                            content_type = st.radio(
                                "What would you like to do?",
                                options=[
                                    "🛒 Webstore Description", 
                                    "📱 Social Media Post", 
                                    "🖼️ Upload Picture to Odoo"
                                ],
                                horizontal=True
                            )

                            SELECTED_MODE = None

                            if content_type == "📱 Social Media Post":
                                marketing_modes = {
                                    "1. الهمزة (العرض المغري والمباشر)": 1,
                                    "2. المشكلة والحل (الواقعي والمألوف)": 2,
                                    "3. البرهان والثقة (طمأنة المشتري)": 3,
                                    "4. التريند والفكاهة (التسويق الساخر)": 4,
                                    "5. الاستخدامات المتعددة (القيمة مقابل السعر)": 5
                                }
                                selected_mode_name = st.selectbox("Select Marketing Mode:", list(marketing_modes.keys()))
                                SELECTED_MODE = marketing_modes[selected_mode_name]
                            
                            elif content_type == "🛒 Webstore Description":
                                st.caption("This will generate an SEO-optimized, Amazon-style description.")

                            # =========================================================
                            # --- 🖼️ IMAGE PROCESSING & UPLOADING BLOCK ---
                            # =========================================================
                            elif content_type == "🖼️ Upload Picture to Odoo":
                                st.caption("Upload a new image, generate an Amazon-style listing, and send to Odoo.")
                                
                                image_upload_type = st.radio(
                                    "Where should this image go?",
                                    options=["➕ Add as an Extra Image (Keep the old one)", "🔄 Replace Main Image"],
                                    horizontal=True
                                )
                                
                                uploaded_image = st.file_uploader("Choose an image...", type=["jpg", "jpeg", "png"])
                                
                                if uploaded_image is not None:
                                    # Reset the generated image if a new file is uploaded
                                    if uploaded_image.file_id != st.session_state.current_file_id:
                                        st.session_state.current_file_id = uploaded_image.file_id
                                        st.session_state.processed_image_bytes = None

                                    image_bytes = uploaded_image.read()
                                    scale_val = st.slider("Product Scale (Size in canvas)", 0.50, 0.95, 0.85)
                                    
                                    # 1. Show Original vs Generated Side-by-Side
                                    col1, col2 = st.columns(2)
                                    
                                    with col1:
                                        st.write("**Original Image:**")
                                        st.image(image_bytes, use_column_width=True)
                                        
                                        # Generation Button
                                        if st.button("✨ Generate Picture", use_container_width=True):
                                            with st.spinner("Applying Studio Effects & Removing Background..."):
                                                processed = create_premium_amazon_listing(image_bytes, product_scale=scale_val)
                                                st.session_state.processed_image_bytes = processed
                                                st.rerun() # Refresh to show the image in col2

                                    with col2:
                                        st.write("**Generated Image:**")
                                        if st.session_state.processed_image_bytes is not None:
                                            st.image(st.session_state.processed_image_bytes, use_column_width=True)
                                        else:
                                            st.info("Click 'Generate Picture' to see the preview here.")

                                    # 2. Show Upload Button ONLY if image has been generated
                                    if st.session_state.processed_image_bytes is not None:
                                        st.divider()
                                        if st.button("📤 Upload Generated Image to Odoo", type="primary", use_container_width=True):
                                            with st.spinner("Uploading to Odoo..."):
                                                try:
                                                    # Convert the PROCESSED image to Base64
                                                    image_base64 = base64.b64encode(st.session_state.processed_image_bytes).decode('utf-8')
                                                    
                                                    common = xmlrpc.client.ServerProxy('{}/xmlrpc/2/common'.format(URL), context=unverified_context)
                                                    uid = common.authenticate(DB, USER, PASS, {})
                                                    
                                                    if uid:
                                                        models = xmlrpc.client.ServerProxy('{}/xmlrpc/2/object'.format(URL), context=unverified_context)
                                                        
                                                        if image_upload_type == "🔄 Replace Main Image":
                                                            update_data = {'image_1920': image_base64}
                                                            result = models.execute_kw(
                                                                DB, uid, PASS, 
                                                                'product.template', 'write', 
                                                                [[selected_product['id']], update_data]
                                                            )
                                                        else:
                                                            create_data = {
                                                                'name': f"{selected_product['name']} - Image",
                                                                'product_tmpl_id': selected_product['id'], 
                                                                'image_1920': image_base64
                                                            }
                                                            result = models.execute_kw(
                                                                DB, uid, PASS, 
                                                                'product.image', 'create', 
                                                                [create_data]
                                                            )
                                                        
                                                        if result:
                                                            st.success(f"✅ Image successfully uploaded to '{selected_product['name']}'!")
                                                            st.balloons()
                                                        else:
                                                            st.error("❌ Failed to update image. Check your permissions.")
                                                    else:
                                                        st.error("❌ Odoo Authentication failed.")
                                                except Exception as e:
                                                    st.error(f"⚠️ Odoo Connection Error: {e}")

                            # =========================================================
                            # --- TEXT GENERATION BLOCK ---
                            # =========================================================
                            if content_type in ["🛒 Webstore Description", "📱 Social Media Post"]:
                                st.divider()
                                session_text_key = f"generated_text_{selected_product['id']}"

                                if st.button(f"✨ Generate Content", use_container_width=True):
                                    with st.spinner(f"Generating content for {selected_product['name']}..."):
                                        p_name = selected_product['name']
                                        p_price = selected_product['list_price']
                                        
                                        if content_type == "📱 Social Media Post":
                                            base_instruction = "أنت مسوق إلكتروني محترف تستهدف السوق الجزائري. اذكر دائماً أن التوصيل متوفر لـ 58 ولاية والدفع عند الاستلام."
                                            if SELECTED_MODE == 1: prompt_text = f"{base_instruction}\nاكتب إعلاناً قصيراً ومباشراً لمنتج {p_name} بسعر {p_price} دج. ركز على أن الكمية محدودة جداً وأنها فرصة لا تعوض."        
                                            elif SELECTED_MODE == 2: prompt_text = f"{base_instruction}\nاكتب منشوراً تسويقياً بلهجة جزائرية مفهومة يطرح مشكلة شائعة، وقدم {p_name} كحل عملي."
                                            elif SELECTED_MODE == 3: prompt_text = f"{base_instruction}\nاكتب منشوراً إعلانياً لترويج {p_name} لبناء الثقة وكسر حاجز الخوف من الاحتيال. استخدم عبارات تطمئن المشتري."
                                            elif SELECTED_MODE == 4: prompt_text = f"{base_instruction}\nاكتب منشوراً فيسبوك فكاهياً لترويج {p_name} واربطه بمواقف طريفة من الحياة اليومية في الجزائر."
                                            elif SELECTED_MODE == 5: prompt_text = f"{base_instruction}\nاكتب منشوراً تسويقياً يشرح كيف يمكن لمنتج {p_name} أن يوفر المال والجهد باستخدامات متعددة."
                                        
                                        elif content_type == "🛒 Webstore Description":
                                            p_category = selected_product.get('categ_id', [0, 'General'])[1] if isinstance(selected_product.get('categ_id'), list) else 'General'
                                            prompt_text = f"""
                                            Act as an expert E-commerce copywriter. 
                                            Product Information:
                                            - Product Name: {p_name}
                                            - Category: {p_category}
                                            Task: Write exactly 5 compelling Bullet Points highlighting the key features and benefits of this product. 
                                            You must provide the exact same 5 points first in Arabic, and then translated to French.
                                            Strict Format to follow exactly:
                                            [Bullet point 1]
                                            [Bullet point 2]
                                            [Bullet point 3]
                                            [Bullet point 4]
                                            [Bullet point 5]
                                            
                                            [Bullet point 1]
                                            [Bullet point 2]
                                            [Bullet point 3]
                                            [Bullet point 4]
                                            [Bullet point 5]
                                            Strict Rules:
                                            1. Use emojis at the beginning of each bullet point in both languages.
                                            2. DO NOT mention any prices.
                                            3. DO NOT write a product title.
                                            4. DO NOT write any introductory or concluding sentences.
                                            5. Output ONLY the requested format with the bullet points, nothing else.
                                            """

                                        max_retries = 3
                                        for attempt in range(max_retries):
                                            try:
                                                response = ai_client.models.generate_content(
                                                    model=gemini_model,
                                                    contents=[prompt_text]
                                                )
                                                st.session_state[session_text_key] = response.text
                                                st.success("✨ Generation complete!")
                                                break
                                                
                                            except Exception as e:
                                                if "429" in str(e):
                                                    st.toast(f"⚠️ Limit hit. Waiting 30 seconds...")
                                                    time.sleep(30)
                                                else:
                                                    st.error(f"Failed to generate text: {e}")
                                                    break

                                if session_text_key in st.session_state:
                                    st.write("### 📝 Review & Edit")
                                    
                                    edited_text = st.text_area(
                                        "You can edit the text below before saving it to Odoo:", 
                                        value=st.session_state[session_text_key], 
                                        height=350
                                    )
                                    
                                    if st.button("💾 Save Description to Odoo", type="primary", use_container_width=True):
                                        with st.spinner("Uploading to Odoo..."):
                                            try:
                                                common = xmlrpc.client.ServerProxy('{}/xmlrpc/2/common'.format(URL), context=unverified_context)
                                                uid = common.authenticate(DB, USER, PASS, {})
                                                
                                                if uid:
                                                    models = xmlrpc.client.ServerProxy('{}/xmlrpc/2/object'.format(URL), context=unverified_context)
                                                    formatted_for_web = edited_text.replace('\n', '<br>')
                                                    
                                                    update_data = {'website_description': formatted_for_web}
                                                    result = models.execute_kw(
                                                        DB, uid, PASS, 
                                                        'product.template', 'write', 
                                                        [[selected_product['id']], update_data]
                                                    )
                                                    
                                                    if result:
                                                        st.success(f"✅ Successfully updated the description for '{selected_product['name']}' in Odoo!")
                                                    else:
                                                        st.error("❌ Failed to update Odoo. Check your permissions.")
                                                else:
                                                    st.error("❌ Odoo Authentication failed. Please check your Email and Password in the secrets.")
                                                    
                                            except Exception as e:
                                                st.error(f"⚠️ Odoo Connection Error: {e}")

                    else:
                        st.warning("No products found matching that search term in this category.")

        except Exception as e:
            st.error(f"Failed to fetch data from Odoo. Error details: {e}")
