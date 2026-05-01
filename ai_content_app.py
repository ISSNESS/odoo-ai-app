
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
api_key=st.secrets["GEMINI_API_KEY"]

unverified_context = ssl._create_unverified_context()
ai_client = genai.Client(api_key) # تأكد من أن مفتاح API معرف مسبقاً


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
