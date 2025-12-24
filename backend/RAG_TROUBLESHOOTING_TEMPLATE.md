# RAG Troubleshooting Response Template

## Thai Language Support Response

### When RAG Retrieves Incorrect Context (Hallucination)

**Template:**
```
ขออภัยในความไม่สะดวกครับ/ค่ะ 🙏

ดูเหมือนว่าระบบ RAG อาจดึงข้อมูลบริบทที่ไม่ตรงกับคำถามของคุณ ทำให้คำตอบไม่ถูกต้อง

**วิธีแก้ไข:**
1. **กดปิด RAG Mode** (ปุ่ม toggle ในส่วน Database Connection)
2. คัดลอกคำถามเดิมของคุณ
3. วางและส่งคำถามใหม่อีกครั้ง

เมื่อปิด RAG แล้ว ระบบจะใช้ schema ทั้งหมดในการสร้าง SQL โดยตรง ซึ่งจะให้ผลลัพธ์ที่แม่นยำกว่าครับ/ค่ะ

หากยังพบปัญหา กรุณาลองเพิ่มรายละเอียดในคำถาม เช่น ระบุชื่อตารางหรือคอลัมน์ที่ต้องการให้ชัดเจนยิ่งขึ้น
```

### English Version

**Template:**
```
We apologize for the inconvenience. 🙏

It appears the RAG system may have retrieved irrelevant context, resulting in an incorrect answer.

**How to fix:**
1. **Disable RAG Mode** (toggle switch in Database Connection section)
2. Copy your original question
3. Paste and send it again

With RAG disabled, the system will use the full schema to generate SQL directly, which should provide more accurate results.

If the issue persists, try adding more details to your question, such as specific table or column names.
```

## Implementation in Frontend

### Add to App.vue (Error Handling)

```javascript
// When SQL generation fails or returns unexpected results
const showRAGTroubleshootingTip = () => {
  const tipMessage = {
    role: 'assistant',
    content: `ขออภัยในความไม่สะดวกครับ/ค่ะ 🙏

ดูเหมือนว่าระบบ RAG อาจดึงข้อมูลบริบทที่ไม่ตรงกับคำถามของคุณ

**วิธีแก้ไข:**
1. **กดปิด RAG Mode** (ปุ่ม toggle ในส่วน Database Connection)
2. คัดลอกคำถามเดิมของคุณ
3. วางและส่งคำถามใหม่อีกครั้ง

เมื่อปิด RAG แล้ว ระบบจะใช้ schema ทั้งหมดในการสร้าง SQL โดยตรง`,
    isSql: false
  }
  
  messages.value.push(tipMessage)
}
```

## Backend Response Enhancement

### Add to main.py (RAG endpoint)

```python
# When RAG retrieval confidence is low
if similarity_score < 0.5:  # Low confidence threshold
    return ChatResponse(
        sql="""-- ⚠️ คำเตือน: ระบบตรวจพบว่าตารางที่เกี่ยวข้องอาจไม่ตรงกับคำถาม
-- แนะนำให้ปิด RAG Mode และลองใหม่อีกครั้ง
-- 
-- Warning: Low confidence in table retrieval
-- Suggest disabling RAG Mode and trying again
"""
    )
```

## User Guide Addition

### Quick Troubleshooting Guide

**ปัญหา: SQL ที่ได้ไม่ตรงกับคำถาม**

**สาเหตุ:**
- RAG Mode อาจเลือกตารางที่ไม่เกี่ยวข้อง
- คำถามคลุมเครือเกินไป
- ชื่อตารางในคำถามไม่ตรงกับฐานข้อมูล

**วิธีแก้:**
1. ✅ **ปิด RAG Mode** → ใช้ schema ทั้งหมด
2. ✅ **เพิ่มรายละเอียด** → ระบุชื่อตารางชัดเจน
3. ✅ **ลองใหม่** → คัดลอกคำถามเดิมและส่งอีกครั้ง

**ตัวอย่าง:**
- ❌ "แสดงข้อมูลทั้งหมด" (คลุมเครือ)
- ✅ "แสดงข้อมูลทั้งหมดจากตาราง product" (ชัดเจน)

---

## When to Show This Message

**Trigger Conditions:**
1. User reports incorrect results
2. Low similarity scores in RAG retrieval (< 0.5)
3. SQL validation fails multiple times
4. User explicitly asks for help

**Auto-detection (Optional):**
```python
def should_show_rag_tip(similarity_scores, user_feedback=None):
    """Determine if RAG troubleshooting tip should be shown"""
    
    # Low confidence in retrieval
    if max(similarity_scores) < 0.5:
        return True
    
    # User feedback indicates problem
    if user_feedback and "wrong" in user_feedback.lower():
        return True
    
    # Large gap between top scores (uncertain retrieval)
    if len(similarity_scores) >= 2:
        if similarity_scores[0] - similarity_scores[1] < 0.1:
            return True
    
    return False
```

## Best Practices

1. **Be Proactive**: Show tip when confidence is low
2. **Be Clear**: Explain what RAG does in simple terms
3. **Be Helpful**: Provide step-by-step instructions
4. **Be Bilingual**: Support both Thai and English
5. **Be Encouraging**: Reassure user that disabling RAG is okay

---

**Note**: This template helps users understand when and why to disable RAG mode, improving their experience and reducing frustration with incorrect results.
