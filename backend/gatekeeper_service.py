#!/usr/bin/env python3
"""
SQL Query Gatekeeper Service
=============================

This service acts as an intelligent filter/classifier for user input before
sending queries to the SQL generation system. It categorizes input into:

1. CHIT_CHAT - Greetings, small talk, non-questions
2. OUT_OF_SCOPE - Questions about data not in the database schema
3. VALID_QUERY - Questions that can be answered with available data

Author: Senior Backend & AI Engineer
Date: 2025-12-15
"""

import re
from typing import Dict, List, Literal
from pydantic import BaseModel
import ollama


class GatekeeperResponse(BaseModel):
    """Response from the gatekeeper classification."""
    type: Literal["CHIT_CHAT", "OUT_OF_SCOPE", "SCHEMA_QUESTION", "VALID_QUERY"]
    reply: str = ""
    query: str = ""


class SQLGatekeeperService:
    """
    Intelligent gatekeeper that filters user input before SQL generation.
    
    Uses LLM to classify queries into:
    - CHIT_CHAT: Greetings, small talk
    - OUT_OF_SCOPE: Questions about data not in schema
    - VALID_QUERY: Valid questions that can be answered
    """
    
    def __init__(
        self,
        ollama_model: str = "gemma:7b",
        ollama_base_url: str = "http://localhost:11434",
        verbose: bool = False
    ):
        """
        Initialize the gatekeeper service.
        
        Args:
            ollama_model: LLM model for classification
            ollama_base_url: Ollama API base URL
            verbose: Enable verbose logging
        """
        self.ollama_model = ollama_model
        self.ollama_base_url = ollama_base_url
        self.verbose = verbose
        
        # Define database schema context
        self.schema_context = self._build_schema_context()
    
    def _log(self, message: str):
        """Internal logging helper."""
        if self.verbose:
            print(message)
    
    def get_rag_troubleshooting_message(self, language: str = "th") -> str:
        """
        Generate helpful troubleshooting message when RAG retrieval fails.
        
        Args:
            language: "th" for Thai, "en" for English
            
        Returns:
            Formatted troubleshooting message
        """
        if language == "th":
            return """ขออภัยในความไม่สะดวกครับ/ค่ะ 🙏

ดูเหมือนว่าระบบ RAG อาจดึงข้อมูลบริบทที่ไม่ตรงกับคำถามของคุณ ทำให้คำตอบไม่ถูกต้อง

**วิธีแก้ไข:**
1. **กดปิด RAG Mode** (ปุ่ม toggle ในส่วน Database Connection)
2. คัดลอกคำถามเดิมของคุณ
3. วางและส่งคำถามใหม่อีกครั้ง

เมื่อปิด RAG แล้ว ระบบจะใช้ schema ทั้งหมดในการสร้าง SQL โดยตรง ซึ่งจะให้ผลลัพธ์ที่แม่นยำกว่าครับ/ค่ะ

หากยังพบปัญหา กรุณาลองเพิ่มรายละเอียดในคำถาม เช่น ระบุชื่อตารางหรือคอลัมน์ที่ต้องการให้ชัดเจนยิ่งขึ้น"""
        else:  # English
            return """We apologize for the inconvenience. 🙏

It appears the RAG system may have retrieved irrelevant context, resulting in an incorrect answer.

**How to fix:**
1. **Disable RAG Mode** (toggle switch in Database Connection section)
2. Copy your original question
3. Paste and send it again

With RAG disabled, the system will use the full schema to generate SQL directly, which should provide more accurate results.

If the issue persists, try adding more details to your question, such as specific table or column names."""
    
    def should_show_rag_tip(self, similarity_scores: list, max_score: float = None) -> bool:
        """
        Determine if RAG troubleshooting tip should be shown based on confidence.
        
        Args:
            similarity_scores: List of similarity scores from RAG retrieval
            max_score: Optional maximum score (if already calculated)
            
        Returns:
            True if tip should be shown
        """
        if not similarity_scores:
            return False
        
        # Get max score if not provided
        if max_score is None:
            max_score = max(similarity_scores)
        
        # Low confidence threshold
        if max_score < 0.5:
            return True
        
        # Large gap between top scores (uncertain retrieval)
        if len(similarity_scores) >= 2:
            sorted_scores = sorted(similarity_scores, reverse=True)
            if sorted_scores[0] - sorted_scores[1] < 0.1:
                return True
        
        return False
    
    def _build_schema_context(self) -> str:
        """
        Build a concise schema context for the gatekeeper.
        
        Returns:
            String describing available tables and their purpose
        """
        schema = """
Database Schema (Pharmaceutical/Medical Supply System):

CORE TABLES:
- product: Medical products, medicines, supplies (columns: product_code, product_name, generic_name, standard_cost, stock_min, stock_max, barcode, etc.)
- stock: Current inventory levels by product, branch, lot (columns: productId, branchId, remaining, lot_number, exp_date, mfg_date, etc.)
- supplier: Suppliers and distributors (columns: name, code, address, contact info, etc.)
- branch: Store/warehouse locations (columns: name, code, address)

PURCHASING:
- purchase_order: Purchase orders to suppliers (columns: code, po_date, total, status, etc.)
- purchase_order_item: PO line items (columns: product, quantity, price, etc.)
- goods_receipt: Incoming inventory receipts (columns: code, receive_date, gr_total, tax, etc.)
- goods_receipt_details: GR line items with lot numbers (columns: product, lot_number, exp_date, cost_unit, etc.)

INVENTORY MANAGEMENT:
- stock_transfer_slip: Inter-branch transfers (columns: code, transfer_date, from_branch, to_branch, status)
- stock_transfer_slip_details: Transfer line items (columns: product, quantity_ordered, quantity_sent)
- stock_history: Historical stock movements (columns: product_id, branch_id, remaining, status, timestamp)

PRICING & PRODUCTS:
- product_price: Product pricing by unit (columns: product, price, unit)
- product_unit: Unit conversions (columns: product, unit_name, conversion_rate)
- product_group: Product categories (columns: name, code)

EMPLOYEES & OPERATIONS:
- user: System users/employees (columns: username, name, role, branch)
- attendance: Employee attendance records (columns: user, date, check_in, check_out)
- leave_request: Employee leave requests (columns: user, leave_type, start_date, end_date, status)
- working_schedule: Employee schedules (columns: user, date, shift)

FINANCIAL:
- payment_goods_receipt: Payments for goods receipts (columns: payment_date, payment_amount, payment_method)

This is a PHARMACEUTICAL/MEDICAL SUPPLY inventory management system.
Users can ask about: products, stock levels, suppliers, purchases, transfers, pricing, employees, attendance, leaves.
Users CANNOT ask about: unrelated topics like weather, sports, general knowledge, food, entertainment, etc.
"""
        return schema.strip()
    
    def _is_chit_chat(self, user_input: str) -> bool:
        """
        Quick pattern-based check for common chit-chat.
        
        Args:
            user_input: User's input text
            
        Returns:
            True if input is likely chit-chat
        """
        # English chit-chat patterns
        chit_chat_patterns = [
            r'^(hi|hello|hey|greetings|good morning|good afternoon|good evening)',
            r'^(how are you|what\'s up|sup|how\'s it going)',
            r'^(thank you|thanks|thx|ty)',
            r'^(bye|goodbye|see you|cya|farewell)',
            r'^(test|testing|check)',
            r'^(ok|okay|yes|no|sure|alright)$',
        ]
        
        # Thai chit-chat patterns
        thai_patterns = [
            # Greetings
            r'(สวัสดี|หวัดดี|ดีครับ|ดีค่ะ)',
            r'(ว่าไง|เป็นไง|ไงบ้าง)',
            r'(อรุณสวัสดิ์|สวัสดีตอนเช้า)',
            r'(ราตรีสวัสดิ์|สวัสดีตอนเย็น)',
            
            # How are you
            r'(สบายดีไหม|สบายดีมั้ย|เป็นอย่างไรบ้าง)',
            r'(ทำอะไรอยู่|กำลังทำอะไร)',
            
            # Thank you
            r'(ขอบคุณ|ขอบใจ|แซงกิ้ว|แซงคิว)',
            r'(ขอบพระคุณ)',
            
            # Goodbye
            r'(ลาก่อน|บาย|บ๊ายบาย)',
            r'(ไปก่อน|ไปละ)',
            r'(แล้วพบกันใหม่)',
            
            # Polite responses
            r'^(ครับ|ค่ะ|จ้ะ|จ๊ะ)$',
            r'^(ได้|โอเค|โอเค|ok)$',
            
            # Test/Check
            r'(ทดสอบ|เช็ค|ลอง)',
            
            # Common questions (non-database related)
            r'(ชื่ออะไร|คุณชื่อ)',
            r'(ทำงานอะไร|อาชีพ)',
        ]
        
        input_lower = user_input.lower().strip()
        
        # Check English patterns
        for pattern in chit_chat_patterns:
            if re.match(pattern, input_lower):
                return True
        
        # Check Thai patterns (case-sensitive for Thai)
        for pattern in thai_patterns:
            if re.search(pattern, user_input):
                return True
        
        return False
    
    def _is_schema_question(self, user_input: str) -> bool:
        """
        Check if user is asking about database structure/schema.
        
        Args:
            user_input: User's input text
            
        Returns:
            True if input is asking about schema/structure
        """
        # English schema question patterns
        schema_patterns = [
            r'(what tables|which tables|list tables|show tables|all tables)',
            r'(table.*structure|database.*structure|schema.*structure)',
            r'(what columns|which columns|list columns|show columns)',
            r'(table.*relationship|how.*tables.*related|tables.*connected)',
            r'(describe.*table|explain.*table|table.*definition)',
            r'(what.*in.*database|what.*database.*contain)',
            r'(show.*schema|display.*schema|get.*schema)',
            r'(database.*design|data.*model)',
        ]
    
        # Thai schema question patterns
        thai_schema_patterns = [
            r'(ตารางอะไรบ้าง|มีตารางอะไร|แสดงตาราง)',
            r'(โครงสร้างตาราง|โครงสร้างฐานข้อมูล)',
            r'(คอลัมน์อะไรบ้าง|มีคอลัมน์อะไร)',
            r'(ตารางเชื่อมโยง|ความสัมพันธ์ตาราง)',
            r'(อธิบายตาราง|บอกเกี่ยวกับตาราง)',
            r'(ฐานข้อมูลมีอะไร|ข้อมูลอะไรบ้าง)',
        ]
        
        input_lower = user_input.lower()
        
        # Check English patterns
        for pattern in schema_patterns:
            if re.search(pattern, input_lower):
                return True
        
        # Check Thai patterns
        for pattern in thai_schema_patterns:
            if re.search(pattern, user_input):
                return True
        
        return False
    
    def _is_negative_feedback(self, user_input: str) -> bool:
        """
        Check if user is reporting incorrect data or negative feedback.
        
        Args:
            user_input: User's input text
            
        Returns:
            True if input is negative feedback/error report
        """
        # English negative feedback patterns
        negative_patterns = [
            r'(incorrect|wrong|false|bad|error|mistake|fail)',
            r'(not right|not correct|not working)',
            r'(garbage data|hallucination|dummy value)',
            r'(data.*wrong|result.*wrong)',
            r'(doesn\'t make sense|nonsense)',
        ]
    
        # Thai negative feedback patterns
        thai_negative_patterns = [
            r'(ข้อมูลไม่ถูก|ข้อมูลผิด|ผลลัพธ์ผิด)',
            r'(ไม่ถูกต้อง|ไม่ใช่|มั่ว)',
            r'(ผิด|เพี้ยน|ไม่ได้เรื่อง)',
            r'(ทำงานไม่ถูก|ตอบไม่ถูก)',
            r'(มีปัญหา|เออเร่อ)',
            r'(ข้อมูล.*ไม่ตรง|ไม่เจอ)',
            r'(ไม่จริง|โกหก)',
        ]
        
        input_lower = user_input.lower()
        
        # Check English patterns
        for pattern in negative_patterns:
            if re.search(pattern, input_lower):
                return True
        
        # Check Thai patterns
        for pattern in thai_negative_patterns:
            if re.search(pattern, user_input):
                return True
        
        return False
    
    def _build_schema_description(self, db_url: str = None) -> str:
        """
        Build a natural language description of the database schema.
        
        Args:
            db_url: Database connection string (optional)
            
        Returns:
            Human-readable schema description
        """
        if not db_url:
            # Return generic message if no database URL provided
            return """
📊 **Database Schema Information**

To see the actual database schema, please provide a database connection string.

The system supports:
- **SQLite**: sqlite:///path/to/database.db
- **PostgreSQL**: postgresql://user:password@host:port/dbname
- **MySQL**: mysql://user:password@host:port/dbname
- **SQL Server**: mssql+pyodbc://user:password@host/dbname

Once connected, I can show you:
• All available tables
• Column names and types
• Table relationships
• Primary and foreign keys
"""
        
        # Extract schema dynamically from database
        try:
            from sqlalchemy import create_engine, inspect
            
            engine = create_engine(db_url)
            inspector = inspect(engine)
            
            # Get all table names
            table_names = inspector.get_table_names()
            
            if not table_names:
                return "-- No tables found in the database."
            
            # Build dynamic schema description
            description = f"""
📊 **Database Schema Overview**

**Database:** {db_url.split('://')[0].upper()}
**Total Tables:** {len(table_names)}

"""
            
            # Group tables by category (if possible to detect)
            for table_name in sorted(table_names):
                columns = inspector.get_columns(table_name)
                pk_constraint = inspector.get_pk_constraint(table_name)
                fk_constraints = inspector.get_foreign_keys(table_name)
                
                description += f"\n**{table_name}**\n"
                description += f"  • Columns ({len(columns)}): "
                description += ", ".join([f"`{col['name']}`" for col in columns[:5]])
                if len(columns) > 5:
                    description += f", ... ({len(columns) - 5} more)"
                description += "\n"
                
                # Add primary key info
                if pk_constraint and pk_constraint.get('constrained_columns'):
                    pk_cols = ", ".join(pk_constraint['constrained_columns'])
                    description += f"  • Primary Key: {pk_cols}\n"
                
                # Add foreign key info
                if fk_constraints:
                    description += f"  • Foreign Keys: "
                    fk_info = []
                    for fk in fk_constraints[:3]:  # Show first 3 FKs
                        ref_table = fk.get('referred_table', 'unknown')
                        fk_info.append(f"{ref_table}")
                    description += ", ".join(fk_info)
                    if len(fk_constraints) > 3:
                        description += f" (+{len(fk_constraints) - 3} more)"
                    description += "\n"
            
            description += """
\n**Tip:** You can now ask questions about the data in these tables!
Examples:
- "Show all records from [table_name]"
- "Count records in [table_name]"
- "Find [column] where [condition]"
"""
            
            engine.dispose()
            return description.strip()
            
        except Exception as e:
            return f"""
-- Error extracting schema: {str(e)}

Please check:
1. Database connection string is correct
2. Database is accessible
3. You have read permissions
"""
    
    def classify_query(self, user_input: str, db_url: str = None) -> GatekeeperResponse:
        """
        Classify user input into CHIT_CHAT, OUT_OF_SCOPE, SCHEMA_QUESTION, or VALID_QUERY.
        
        Args:
            user_input: User's natural language input
            db_url: Optional database connection string for schema extraction
            
        Returns:
            GatekeeperResponse with classification and appropriate reply
        """
        self._log(f"\n🛡️  Gatekeeper analyzing: '{user_input}'")
        
        # Quick check for chit-chat patterns
        if self._is_chit_chat(user_input):
            self._log("   → Classified as CHIT_CHAT (pattern match)")
            return GatekeeperResponse(
                type="CHIT_CHAT",
                reply="สวัสดีครับ/ค่ะ! ผมเป็นผู้ช่วย SQL สำหรับระบบคลังสินค้าเวชภัณฑ์ มีอะไรให้ช่วยเกี่ยวกับข้อมูลสินค้า สต็อก ซัพพลายเออร์ หรือใบสั่งซื้อไหมครับ/ค่ะ? | Hello! I'm your SQL Assistant for the pharmaceutical inventory system. How can I help you with product data, stock levels, suppliers, or purchase orders?"
            )
        
        # Check for schema/structure questions
        if self._is_schema_question(user_input):
            self._log("   → Classified as SCHEMA_QUESTION (pattern match)")
            return GatekeeperResponse(
                type="SCHEMA_QUESTION",
                reply=self._build_schema_description(db_url)  # Pass db_url here
            )
            
        # Check for negative feedback / incorrect data reports
        if self._is_negative_feedback(user_input):
            self._log("   → Classified as NEGATIVE_FEEDBACK (pattern match)")
            # Determine language based on input
            lang = "th" if any(c for c in user_input if '\u0e00' <= c <= '\u0e7f') else "en"
            return GatekeeperResponse(
                type="CHIT_CHAT",  # Treat as chit-chat type but with specific troubleshooting content
                reply=self.get_rag_troubleshooting_message(lang)
            )
        
        # Use LLM for more complex classification
        prompt = f"""You are an intelligent SQL Assistant Gatekeeper. Classify the user input based on the database schema.

{self.schema_context}

Analyze this user input and determine if it's:
1. CHIT_CHAT - Greeting, small talk, or not a real question
2. OUT_OF_SCOPE - Asks for data NOT in the schema above
3. VALID_QUERY - Asks for data that EXISTS in the schema

User Input: "{user_input}"

Respond with ONLY ONE of these formats (JSON):

If CHIT_CHAT:
{{"type": "CHIT_CHAT", "reply": "Greetings! I am your SQL Assistant. How can I help you with the pharmaceutical inventory database?"}}

If OUT_OF_SCOPE:
{{"type": "OUT_OF_SCOPE", "reply": "Sorry, I cannot find information about [Topic] in the database. I only have access to pharmaceutical products, stock, suppliers, purchases, and employee data."}}

If VALID_QUERY:
{{"type": "VALID_QUERY", "query": "{user_input}"}}

Response (JSON only):"""
        
        try:
            # Call LLM for classification
            response = ollama.generate(
                model=self.ollama_model,
                prompt=prompt,
                options={
                    "temperature": 0.1,  # Low temperature for consistent classification
                    "num_predict": 200,
                }
            )
            
            response_text = response['response'].strip()
            self._log(f"   LLM response: {response_text}")
            
            # Parse JSON response
            import json
            
            # Extract JSON from response (handle markdown code blocks)
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()
            
            # Remove any leading/trailing text
            if "{" in response_text:
                start = response_text.index("{")
                end = response_text.rindex("}") + 1
                response_text = response_text[start:end]
            
            result = json.loads(response_text)
            
            # Validate and create response
            classification_type = result.get("type", "VALID_QUERY")
            
            if classification_type == "CHIT_CHAT":
                self._log("   → Classified as CHIT_CHAT")
                return GatekeeperResponse(
                    type="CHIT_CHAT",
                    reply=result.get("reply", "Hello! How can I help you?")
                )
            elif classification_type == "OUT_OF_SCOPE":
                self._log("   → Classified as OUT_OF_SCOPE")
                return GatekeeperResponse(
                    type="OUT_OF_SCOPE",
                    reply=result.get("reply", "Sorry, that information is not available in the database.")
                )
            else:
                self._log("   → Classified as VALID_QUERY")
                return GatekeeperResponse(
                    type="VALID_QUERY",
                    query=result.get("query", user_input)
                )
        
        except Exception as e:
            self._log(f"   ⚠️  Classification error: {str(e)}")
            # Default to VALID_QUERY if classification fails
            return GatekeeperResponse(
                type="VALID_QUERY",
                query=user_input
            )
    
    def should_process_query(self, user_input: str) -> tuple[bool, str]:
        """
        Convenience method to check if query should be processed.
        
        Args:
            user_input: User's input
            
        Returns:
            Tuple of (should_process, message)
            - should_process: True if VALID_QUERY, False otherwise
            - message: Reply message for CHIT_CHAT or OUT_OF_SCOPE
        """
        result = self.classify_query(user_input)
        
        if result.type == "VALID_QUERY":
            return True, ""
        else:
            return False, result.reply


# Convenience function
def classify_user_input(
    user_input: str,
    verbose: bool = False
) -> GatekeeperResponse:
    """
    Quick function to classify user input.
    
    Args:
        user_input: User's question/input
        verbose: Enable logging
        
    Returns:
        GatekeeperResponse with classification
    """
    gatekeeper = SQLGatekeeperService(verbose=verbose)
    return gatekeeper.classify_query(user_input)
