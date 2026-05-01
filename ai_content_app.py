
import time  # <--- Added for waiting
from google import genai
from google.genai import types
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
import os
import re
import streamlit as st
import xmlrpc.client
import ssl

gemini_model = 'gemini-2.5-flash-lite' 

# --- YOUR DETAILS SECURED ---
URL = st.secrets["ODOO_URL"]
DB = st.secrets["ODOO_DB"]            
USER = st.secrets["ODOO_USER"]
PASS = st.secrets["ODOO_PASS"]
API = st.secrets["GEMINI_API_KEY"]

unverified_context = ssl._create_unverified_context()
ai_client = genai.Client(api_key=API)

# Set up the title of your web app
st.title("Odoo Product Fetcher 📦")
st.write("Let's make sure we can talk to your Odoo database.")

# --- 1. SET UP STREAMLIT MEMORY (SESSION STATE) ---
# This ensures we don't lose our connection when we click a dropdown.
if 'connected' not in st.session_state:
    st.session_state.connected = False
    st.session_state.uid = None
    st.session_state.url = None
    st.session_state.db = None
    st.session_state.password = None

# --- 2. The Connect Button ---
if st.button("Connect to Odoo"):
    # Check if the user filled out all fields before trying to connect
    if URL and DB and USER and PASS:
        with st.spinner("Attempting to connect..."):
            try:
                # --- 3. CONNECT TO ODOO ---
                common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common', context=unverified_context)
                uid = common.authenticate(DB, USER, PASS, {})

                if uid:
                    # SUCCESS! Save the details to the session state
                    st.session_state.connected = True
                    st.session_state.uid = uid
                    st.session_state.url = URL
                    st.session_state.db = DB
                    st.session_state.password = PASS
                    
                    # Refresh the app immediately to hide login and show categories
                    st.rerun() 
                else:
                    st.error("Authentication failed. Please check your credentials.")
            except Exception as e:
                st.error(f"Could not connect. Error details: {e}")

            except Exception as e:
                 # This catches network errors, wrong URLs, etc.
                st.error(f"Could not connect to the server. Error details: {e}")
    else:
        st.warning("Please fill in all the credential fields first.")


# --- 3. THE MAIN APP (Shows only AFTER successful connection) ---
if st.session_state.connected:
    st.success("✅ Connected to Odoo successfully!")
    
    # A handy disconnect button to log out
    if st.button("Disconnect"):
        st.session_state.connected = False
        st.rerun()

    st.divider() # A nice horizontal line for visual separation
    st.subheader("Browse & Search Products")

    with st.spinner("Fetching categories from Odoo..."):
        try:
            # Connect to the 'object' endpoint to read data
            models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object', context=unverified_context)
            
            # Fetch all categories
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

                # 1. Select Category
                selected_category_name = st.selectbox("1. Select a Category:", category_names)
                selected_category_id = category_dict[selected_category_name]

                # 2. Search Bar for Products
                search_query = st.text_input(f"2. Search products in '{selected_category_name}':", placeholder="e.g., machine")

                # ADDITION 1: Create a memory slot for the search results right here
                if 'search_results' not in st.session_state:
                    st.session_state.search_results = None

                # 3. Search Button
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
                            # ADDITION 2: Save the fetched products into memory!
                            st.session_state.search_results = products
                    else:
                        st.info("Please enter a word to search for.")

                # ADDITION 3: Move the table code OUTSIDE the button block, and read from memory
                if st.session_state.search_results is not None:
                    
                    if len(st.session_state.search_results) > 0:
                        st.success(f"Found {len(st.session_state.search_results)} products!")
                        
                        # Show the table using the memory state
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
                            
                            # 1. --- PRIMARY SELECTION: WHAT TO GENERATE ---
                            st.write("### 🎯 Choose Content Type")
                            content_type = st.radio(
                                "What would you like to generate?",
                                options=["🛒 Webstore Description (Amazon-Style)", "📱 Social Media Marketing Post"],
                                horizontal=True
                            )

                            # Variables to hold user choices
                            SELECTED_MODE = None

                            # 2. --- DYNAMIC UI BASED ON SELECTION ---
                            if content_type == "📱 Social Media Marketing Post":
                                marketing_modes = {
                                    "1. الهمزة (العرض المغري والمباشر)": 1,
                                    "2. المشكلة والحل (الواقعي والمألوف)": 2,
                                    "3. البرهان والثقة (طمأنة المشتري)": 3,
                                    "4. التريند والفكاهة (التسويق الساخر)": 4,
                                    "5. الاستخدامات المتعددة (القيمة مقابل السعر)": 5
                                }
                                selected_mode_name = st.selectbox("Select Marketing Mode:", list(marketing_modes.keys()))
                                SELECTED_MODE = marketing_modes[selected_mode_name]
                            
                            elif content_type == "🛒 Webstore Description (Amazon-Style)":
                                st.caption("This will generate an SEO-optimized, Amazon-style description with a title, bullet points, and a detailed paragraph in Arabic/English.")
                                # You can add more options here later (like Language selection)

                            # 3. --- THE GENERATE BUTTON ---
                            st.divider()
                            
                            # إنشاء مفتاح ذاكرة فريد لهذا المنتج بالذات
                            session_text_key = f"generated_text_{selected_product['id']}"

                            if st.button(f"✨ Generate {content_type.split(' ')[1]}", use_container_width=True):
                                with st.spinner(f"Generating content for {selected_product['name']}..."):
                                    
                                    p_name = selected_product['name']
                                    p_price = selected_product['list_price']
                                    
                                    # 4. --- PREPARE THE PROMPT ---
                                    if content_type == "📱 Social Media Marketing Post":
                                        base_instruction = "أنت مسوق إلكتروني محترف تستهدف السوق الجزائري. اذكر دائماً أن التوصيل متوفر لـ 58 ولاية والدفع عند الاستلام."
                                        if SELECTED_MODE == 1: prompt_text = f"{base_instruction}\nاكتب إعلاناً قصيراً ومباشراً لمنتج {p_name} بسعر {p_price} دج. ركز على أن الكمية محدودة جداً وأنها فرصة لا تعوض."        
                                        elif SELECTED_MODE == 2: prompt_text = f"{base_instruction}\nاكتب منشوراً تسويقياً بلهجة جزائرية مفهومة يطرح مشكلة شائعة، وقدم {p_name} كحل عملي."
                                        elif SELECTED_MODE == 3: prompt_text = f"{base_instruction}\nاكتب منشوراً إعلانياً لترويج {p_name} لبناء الثقة وكسر حاجز الخوف من الاحتيال. استخدم عبارات تطمئن المشتري."
                                        elif SELECTED_MODE == 4: prompt_text = f"{base_instruction}\nاكتب منشوراً فيسبوك فكاهياً لترويج {p_name} واربطه بمواقف طريفة من الحياة اليومية في الجزائر."
                                        elif SELECTED_MODE == 5: prompt_text = f"{base_instruction}\nاكتب منشوراً تسويقياً يشرح كيف يمكن لمنتج {p_name} أن يوفر المال والجهد باستخدامات متعددة."
                                    
                                    elif content_type == "🛒 Webstore Description (Amazon-Style)":
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
                                        4. DO NOT write any introductory or concluding sentences (e.g., do not say "Here is the description" or "Sure!").
                                        5. Output ONLY the requested format with the bullet points, nothing else.
                                        """

                                    # 5. --- CALL GEMINI ---
                                    max_retries = 3
                                    import time 
                                    
                                    for attempt in range(max_retries):
                                        try:
                                            response = ai_client.models.generate_content(
                                                model=gemini_model,
                                                contents=[prompt_text]
                                            )
                                            # حفظ النص المُولد في ذاكرة التطبيق
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

                            # 6. --- REVIEW, EDIT, AND SAVE TO ODOO ---
                            # نتحقق مما إذا كان هناك نص مُولد مسبقاً لهذا المنتج في الذاكرة
                            if session_text_key in st.session_state:
                                st.write("### 📝 Review & Edit")
                                
                                # st.text_area سيأخذ قيمته الابتدائية من الذاكرة، وأي تعديل تقوم به سيتم حفظه في متغير edited_text
                                edited_text = st.text_area(
                                    "You can edit the text below before saving it to Odoo:", 
                                    value=st.session_state[session_text_key], 
                                    height=350
                                )
                                
                                # زر الإرسال إلى Odoo (نستخدم لون بارز primary)
                                if st.button("💾 Save Description to Odoo", type="primary", use_container_width=True):
                                    with st.spinner("Uploading to Odoo..."):
                                        try:
                                            # 1. أولاً: المصادقة للحصول على رقم المستخدم (uid)
                                            common = xmlrpc.client.ServerProxy('{}/xmlrpc/2/common'.format(URL), context=unverified_context)
                                            uid = common.authenticate(DB, USER, PASS, {})
                                            
                                            # إذا تمت المصادقة بنجاح وتم إرجاع رقم
                                            if uid:
                                                # 2. ثانياً: إعداد الاتصال بقاعدة البيانات
                                                models = xmlrpc.client.ServerProxy('{}/xmlrpc/2/object'.format(URL), context=unverified_context)
                                                
                                                # Convert standard line breaks to HTML line breaks
                                                formatted_for_web = edited_text.replace('\n', '<br>')
                                                
                                                update_data = {
                                                    'website_description': formatted_for_web 
                                                }
                                                
                                                # 3. أمر التحديث: لاحظ أننا نستخدم uid الآن بدلاً من USER
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

            else:
                st.warning("No categories found in this database.")

        except Exception as e:
            st.error(f"Failed to fetch data from Odoo. Error details: {e}")
# Set up the title of your web app
st.title("Odoo Product Fetcher 📦")
st.write("Let's make sure we can talk to your Odoo database.")

# --- 1. SET UP STREAMLIT MEMORY (SESSION STATE) ---
# This ensures we don't lose our connection when we click a dropdown.
if 'connected' not in st.session_state:
    st.session_state.connected = False
    st.session_state.uid = None
    st.session_state.url = None
    st.session_state.db = None
    st.session_state.password = None

# --- 2. The Connect Button ---
if st.button("Connect to Odoo"):
    # Check if the user filled out all fields before trying to connect
    if URL and DB and USER and PASS:
        with st.spinner("Attempting to connect..."):
            try:
                # --- 3. CONNECT TO ODOO ---
                common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common', context=unverified_context)
                uid = common.authenticate(DB, USER, PASS, {})

                if uid:
                    # SUCCESS! Save the details to the session state
                    st.session_state.connected = True
                    st.session_state.uid = uid
                    st.session_state.url = URL
                    st.session_state.db = DB
                    st.session_state.password = PASS
                    
                    # Refresh the app immediately to hide login and show categories
                    st.rerun() 
                else:
                    st.error("Authentication failed. Please check your credentials.")
            except Exception as e:
                st.error(f"Could not connect. Error details: {e}")

            except Exception as e:
                 # This catches network errors, wrong URLs, etc.
                st.error(f"Could not connect to the server. Error details: {e}")
    else:
        st.warning("Please fill in all the credential fields first.")


# --- 3. THE MAIN APP (Shows only AFTER successful connection) ---
if st.session_state.connected:
    st.success("✅ Connected to Odoo successfully!")
    
    # A handy disconnect button to log out
    if st.button("Disconnect"):
        st.session_state.connected = False
        st.rerun()

    st.divider() # A nice horizontal line for visual separation
    st.subheader("Browse & Search Products")

    with st.spinner("Fetching categories from Odoo..."):
        try:
            # Connect to the 'object' endpoint to read data
            models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object', context=unverified_context)
            
            # Fetch all categories
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

                # 1. Select Category
                selected_category_name = st.selectbox("1. Select a Category:", category_names)
                selected_category_id = category_dict[selected_category_name]

                # 2. Search Bar for Products
                search_query = st.text_input(f"2. Search products in '{selected_category_name}':", placeholder="e.g., machine")

                # ADDITION 1: Create a memory slot for the search results right here
                if 'search_results' not in st.session_state:
                    st.session_state.search_results = None

                # 3. Search Button
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
                            # ADDITION 2: Save the fetched products into memory!
                            st.session_state.search_results = products
                    else:
                        st.info("Please enter a word to search for.")

                # ADDITION 3: Move the table code OUTSIDE the button block, and read from memory
                if st.session_state.search_results is not None:
                    
                    if len(st.session_state.search_results) > 0:
                        st.success(f"Found {len(st.session_state.search_results)} products!")
                        
                        # Show the table using the memory state
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
                            
                            # --- ADD THE MARKETING MODE DROPDOWN ---
                            # We create a dictionary to map the nice Arabic text to your mode numbers
                            marketing_modes = {
                                "1. الهمزة (العرض المغري والمباشر)": 1,
                                "2. المشكلة والحل (الواقعي والمألوف)": 2,
                                "3. البرهان والثقة (طمأنة المشتري)": 3,
                                "4. التريند والفكاهة (التسويق الساخر)": 4,
                                "5. الاستخدامات المتعددة (القيمة مقابل السعر)": 5
                            }
                            selected_mode_name = st.selectbox("Select Marketing Mode:", list(marketing_modes.keys()))
                            SELECTED_MODE = marketing_modes[selected_mode_name]

                            # --- THE GENERATE BUTTON ---
                            if st.button("Generate Description"):
                                with st.spinner(f"Generating description for {selected_product['name']}..."):
                                    
                                    # Set up your variables based on the Odoo data
                                    p_name = selected_product['name']
                                    p_price = selected_product['list_price']
                                    
                                    # Prepare the AI Prompt
                                    base_instruction = "أنت مسوق إلكتروني محترف تستهدف السوق الجزائري. اذكر دائماً أن التوصيل متوفر لـ 58 ولاية والدفع عند الاستلام."

                                    if SELECTED_MODE == 1:
                                        prompt_text = f"{base_instruction}\nاكتب إعلاناً قصيراً ومباشراً لمنتج {p_name} بسعر {p_price} دج. ركز على أن الكمية محدودة جداً وأنها فرصة لا تعوض."        
                                    elif SELECTED_MODE == 2:
                                        prompt_text = f"{base_instruction}\nاكتب منشوراً تسويقياً بلهجة جزائرية مفهومة (دارجة بيضاء) يطرح مشكلة شائعة يعاني منها الناس، وقدم منتج {p_name} بسعر {p_price} دج كحل عملي وسريع لهذه المشكلة."
                                    elif SELECTED_MODE == 3:
                                        prompt_text = f"{base_instruction}\nاكتب منشوراً إعلانياً (Post) لترويج منتج {p_name} بسعر {p_price} دج للسوق الجزائري. الهدف الأساسي للمنشور هو كسر حاجز الخوف من الاحتيال أو رداءة الجودة وبناء ثقة تامة مع الزبون. استخدم لغة تسويقية مطمئنة وقريبة للمشتري الجزائري، ووظف عبارات تبني الأمان مثل: 'السلعة كيما في التصويرة'، 'ضمان الاستبدال'، و'حقك محفوظ'. من الضروري جداً التأكيد بشكل قوي وصريح في المنشور على أن الدفع يكون فقط بعد الاستلام، وفتح العلبة، والتحقق من المنتج شخصياً."
                                    elif SELECTED_MODE == 4:
                                        prompt_text = f"{base_instruction}\nاكتب منشوراً فيسبوك فكاهياً لترويج منتج {p_name} بسعر {p_price} دج للجمهور الجزائري، واربطه بمواقف طريفة من الحياة اليومية في الجزائر لجلب التفاعل والمشاركات."
                                    elif SELECTED_MODE == 5:
                                        prompt_text = f"{base_instruction}\nاكتب منشوراً تسويقياً يستهدف العائلات في الجزائر، اشرح فيه كيف يمكن لمنتج {p_name} بسعر {p_price} دج أن يوفر عليهم المال والجهد من خلال استخدامه في مجالات أو طرق مختلفة."
                                    else:
                                        prompt_text = f"{base_instruction}\nاكتب إعلاناً تسويقياً لمنتج {p_name} بسعر {p_price} دج."

                                    # Call Gemini with Wait & Retry Logic
                                    max_retries = 3
                                    ai_text = ""
                                    
                                    for attempt in range(max_retries):
                                        try:
                                            # NOTE: Ensure `ai_client` and `gemini_model` are defined at the top of your script!
                                            response = ai_client.models.generate_content(
                                                model=gemini_model,
                                                contents=[prompt_text]
                                            )
                                            ai_text = response.text
                                            break # Success! Break the loop
                                            
                                        except Exception as e:
                                            if "429" in str(e):
                                                # st.toast shows a small pop-up notification at the bottom of the screen
                                                st.toast(f"⚠️ Limit hit. Waiting 30 seconds before retry {attempt+1}/{max_retries}...")
                                                time.sleep(30)
                                            else:
                                                st.error(f"Failed to generate text: {e}")
                                                break

                                    # Display the final text in a copyable text area!
                                    if ai_text:
                                        st.success("✨ Generation complete!")
                                        # text_area makes a nice box where users can easily click and copy
                                        st.text_area("Copy your post from here:", value=ai_text, height=350)

                    else:
                        st.warning("No products found matching that search term in this category.")

            else:
                st.warning("No categories found in this database.")

        except Exception as e:
            st.error(f"Failed to fetch data from Odoo. Error details: {e}")
