# 🛰️ TauSync Protocol Specification (v1.0)

**Project Name:** TauSync  
**Description:** Cross-Platform Smart Connectivity Protocol (Windows <-> Android)  
**Status:** Design Phase (Contractual)

---

## 1. המטרה (Objective)
הגדרה של "חוזה" משותף המאפשר תקשורת מאובטחת וחכמה בין אפליקציית Windows (ב-C#) לאפליקציית Android (ב-Java), תוך הפרדה מוחלטת בין הלוגיקה למימוש החומרה.

---

## 2. מודל הנתונים: `TransferRequest`
כל מידע שעובר בפרוטוקול TauSync ייארז בתוך אובייקט (בפורמט JSON) עם המבנה הבא:

| שדה (Field) | סוג (Type) | תיאור |
| :--- | :--- | :--- |
| `MagicBytes` | `uint32` | תמיד `0x54415553` ("TAUS" ב-ASCII). |
| `Version` | `int` | גרסת הפרוטוקול הנוכחית (תמיד 1). |
| `Payload` | `byte[]` | המידע הגולמי (הקובץ/הודעה) **אחרי הצפנה**. |
| `Priority` | `int` | רמת דחיפות: `0` (Low/BT), `1` (High/WiFi). |
| `IsCompressed` | `bool` | האם ה-Payload עבר דחיסת GZip. |
| `CryptoIV` | `byte[]` | ה-Initialization Vector ששימש להצפנת ה-Payload. |

---

## 3. ממשקים (Interfaces) - "החוזה"

### 📡 ITransport (שכבת הקישוריות)
הצינור דרכו עוברים הבתים. כל צד (Win/Droid) חייב לממש אותו עבור WiFi ו-Bluetooth.
- `void Connect(String targetId)`: יצירת חיבור ראשוני.
- `void SendRaw(byte[] data)`: שליחת חבילה בינארית.
- `bool IsConnected()`: בדיקת סטטוס חיבור.

### 🔐 ISecureChannel (שכבת האבטחה)
אחראי על הטיפול ב-Crypto לפני שהחבילה נשלחת.
- `byte[] Encrypt(byte[] plaintext)`: הצפנה ב-AES-GCM.
- `byte[] Decrypt(byte[] ciphertext)`: פענוח ואימות.

### 🧠 IConnectionManager (שכבת הניהול)
המוח שמחליט באיזה `ITransport` להשתמש.
- `void SmartSend(TransferRequest req)`: לוגיקת בחירת מדיום ושליחה.
- `void HandleIncoming(byte[] rawData)`: קבלה ועיבוד של חבילה נכנסת.

---

## 4. לוגיקת מעבר מדיום (Smart Handover)
1. **Bluetooth Mode (Low Power):** ברירת מחדל לחיפוש (Discovery) והודעות קטנות (< 1MB).
2. **WiFi Direct Mode (High Speed):** יופעל אוטומטית אם `Priority == 1` או שגודל ה-Payload חורג מ-1MB.

---

## 5. הערות פיתוח
- **סנכרון:** כל שינוי ב-Interface ב-C# מחייב עדכון מקביל ב-Java.
- **אבטחה:** ה-`CryptoIV` חייב להיות ייחודי (Random) לכל שליחה.