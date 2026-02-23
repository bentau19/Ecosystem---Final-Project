# איך להפעיל את TauSync

## דרישות

### Windows (Python):
```bash
pip install -r requirements.txt
```

### Android:
- הוסף את התלויות ב-`build.gradle.kts` (Gson)
- בנה את האפליקציה

## הפעלה

### שלב 1: הפעל את האפליקציה ב-Android
1. פתח את האפליקציה ב-Android
2. לחץ על "Start Server"
3. שים לב ל-IP address שמוצג

### שלב 2: הפעל את ה-Python client ב-Windows

#### שליחת הודעה:
```bash
python tausync_client.py <android_ip> "Hello from Python!"
```

#### קבלת הודעות:
```bash
python tausync_client.py <android_ip>
```

## דוגמה מלאה

1. **Android**: הפעל את האפליקציה ולחץ "Start Server"
   - שים לב ל-IP (לדוגמה: 192.168.1.100)

2. **Windows**: הרץ:
   ```bash
   python tausync_client.py 192.168.1.100 "Hello Android!"
   ```

3. ההודעה תופיע באפליקציית Android

## הערות חשובות

- שני המכשירים חייבים להיות באותה רשת WiFi
- Port ברירת מחדל: 8888
- Shared key נוצר אוטומטית (בגרסה זו - לא מאובטח)
- בייצור, יש להחליף shared key בצורה מאובטחת
